import {mkdir, writeFile, readFile, stat} from 'node:fs/promises'
import {spawn, execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {createHash} from 'node:crypto'
import {join, resolve} from 'node:path'
import {pathToFileURL} from 'node:url'
import assert from 'node:assert/strict'

const execute = promisify(execFile)
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex')

// Own a new directory; never reset or remove an existing repository or fixture.
export async function createPilotFixture(directory) {
  const root = resolve(directory), repository = join(root, 'source.git'), bundle = join(root, 'pilot.bundle')
  await mkdir(root, {mode: 0o700})
  const env = {...process.env, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: process.platform === 'win32' ? 'NUL' : '/dev/null'}
  const git = process.env.GITGOOD_GIT ?? 'git'
  const command = args => execute(git, args, {env, cwd: root, timeout: 120_000, maxBuffer: 4 * 1024 * 1024, windowsHide: true})
  await command(['init', '--bare', '--template=', '--object-format=sha1', '--initial-branch=main', repository])
  const chunks = []; let blob = 0
  const name = index => 'directory-' + String(Math.floor(index / 100)).padStart(2, '0') + '/file-' + String(index).padStart(4, '0') + '.txt'
  const content = (index, revision) => Buffer.from(Array.from({length: 64}, (_, line) =>
    sha256('gitgood-pilot-v1:' + index + ':' + revision + ':' + line).slice(0, 63) + '\n').join(''))
  function commit(branch, index, parent, files) {
    const changes = files.map(file => {
      const bytes = content(file, index); assert.equal(bytes.length, 4096)
      const mark = ++blob
      chunks.push(Buffer.from('blob\nmark :' + mark + '\ndata ' + bytes.length + '\n'), bytes, Buffer.from('\n'))
      return 'M 100644 :' + mark + ' ' + name(file) + '\n'
    })
    const message = 'Synthetic pilot revision ' + index + '\n'
    chunks.push(Buffer.from('commit refs/heads/' + branch + '\nmark :' + (1_000_000 + index) +
      '\nauthor Pilot fixture <pilot@example.invalid> ' + (1_720_000_000 + index) + ' +0000' +
      '\ncommitter Pilot fixture <pilot@example.invalid> ' + (1_720_000_000 + index) + ' +0000' +
      '\ndata ' + Buffer.byteLength(message) + '\n' + message +
      (parent === null ? '' : 'from :' + (1_000_000 + parent) + '\n') + changes.join('') + '\n'))
  }
  commit('main', 0, null, Array.from({length: 2000}, (_, index) => index))
  for (let index = 1; index < 500; index++) commit('main', index, index - 1, [2 * (index - 1), 2 * (index - 1) + 1])
  for (let index = 500; index < 510; index++) commit('pilot-work', index, index - 1, [2 * (index - 500), 2 * (index - 500) + 1])
  chunks.push(Buffer.from('done\n'))
  const child = spawn(git, ['--git-dir', repository, 'fast-import', '--date-format=raw', '--done', '--quiet'],
    {cwd: root, env, windowsHide: true, timeout: 120_000, killSignal: 'SIGKILL', stdio: ['pipe', 'ignore', 'pipe']})
  let diagnostics = ''
  child.stderr.on('data', bytes => {diagnostics = (diagnostics + bytes.toString()).slice(-8192)})
  const completed = new Promise((done, reject) => {child.once('error', reject); child.once('close', code =>
    code === 0 ? done() : reject(new Error('Pilot fast-import refused: ' + diagnostics)))})
  child.stdin.on('error', () => {})
  child.stdin.end(Buffer.concat(chunks))
  await completed
  const bare = args => command(['--git-dir', repository, ...args])
  await bare(['fsck', '--full', '--strict'])
  const main = (await bare(['rev-parse', 'refs/heads/main'])).stdout.trim()
  const work = (await bare(['rev-parse', 'refs/heads/pilot-work'])).stdout.trim()
  assert.equal((await bare(['rev-list', '--count', main])).stdout.trim(), '500')
  assert.equal((await bare(['rev-list', '--count', work])).stdout.trim(), '510')
  const files = (await bare(['ls-tree', '-rl', main])).stdout.trim().split('\n')
  assert.equal(files.length, 2000)
  assert(files.every(row => /^100644 blob [0-9a-f]{40}\s+4096\t/.test(row)))
  assert.equal((await bare(['diff', '--name-only', main, work])).stdout.trim().split('\n').length, 20)
  const diff = (await bare(['diff', '--no-ext-diff', '--no-textconv', '--no-renames', main, work])).stdout
  assert(Buffer.byteLength(diff) <= 262_144)
  const sampleFile = Buffer.from((await bare(['show', main + ':' + name(0)])).stdout)
  assert.equal(sha256(sampleFile), sha256(content(0, 1)))
  await bare(['bundle', 'create', bundle, '--branches'])
  await bare(['bundle', 'verify', bundle])
  const bytes = await readFile(bundle)
  assert(bytes.length <= 33_554_432, 'Pilot fixture exceeds the existing import profile')
  const objects = (await bare(['count-objects', '-v'])).stdout.trim()
  const receipt = {schemaVersion: 1, profile: 'gitgood-pilot-v1', repository_format: 'sha1',
    git_version: (await command(['--version'])).stdout.trim(), main_sha: main, work_sha: work,
    files: 2000, file_bytes: 4096, directories: 20, main_commits: 500, work_commits: 510,
    changed_files: 20, diff_bytes: Buffer.byteLength(diff), diff_sha256: sha256(diff), logical_tree_bytes: 2000 * 4096,
    sample_file: {path: name(0), bytes: sampleFile.length, sha256: sha256(sampleFile)},
    bundle: {bytes: (await stat(bundle)).size, sha256: sha256(bytes)}, git_objects: objects,
    status: 'fixture identity checked; native import, latency and capacity remain unmeasured'}
  await writeFile(join(root, 'fixture-receipt.json'), JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx', mode: 0o600})
  return receipt
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  assert.equal(process.argv.length, 3, 'Provide one new owned fixture directory')
  console.log(JSON.stringify(await createPilotFixture(process.argv[2])))
}
