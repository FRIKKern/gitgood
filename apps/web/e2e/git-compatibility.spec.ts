import {test, expect} from '@playwright/test'
import {fixtureSession as session} from './fixture-session'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {mkdtemp, mkdir, writeFile, readFile} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join, resolve} from 'node:path'
import {createHash} from 'node:crypto'
const execute = promisify(execFile)
const upstream = process.env.GITGOOD_TEST_API_URL ?? 'http://127.0.0.1:47841'
const git = process.env.GITGOOD_GIT ?? 'git'
const windows = process.platform === 'win32'
const ssh = process.env.GITGOOD_SSH ?? (windows ? 'C:/Windows/System32/OpenSSH/ssh.exe' : 'ssh')
const keygen = process.env.GITGOOD_SSH_KEYGEN ?? (windows ? 'C:/Windows/System32/OpenSSH/ssh-keygen.exe' : 'ssh-keygen')
const quote = (value: string) => "'" + value.replaceAll("'", "'\\''") + "'"
const hash = (value: string | Buffer) => createHash('sha256').update(value).digest('hex')

test('real native Git compatibility preserves ancestry, gitlinks and signed objects with explicit unsupported profiles', async ({}, info) => {
  test.setTimeout(240000)
  const root = await mkdtemp(join(tmpdir(), 'gitgood-git-compatibility-')), owner = await session('owner')
  const prefix = 'compatibility-' + Date.now(), certificate = process.env.GITGOOD_TEST_CA
  if (!certificate) throw new Error('Compatibility verification requires copied-production normal TLS trust')
  const create = async (name: string) => {
    const response = await fetch(upstream + '/api/repos', {method: 'POST', headers: {...owner, 'idempotency-key': name}, body: JSON.stringify({team: 'team', name})})
    expect(response.status).toBe(201)
    const repository = await response.json()
    const credential = await fetch(upstream + '/api/repos/team/' + name + '/credentials', {method: 'POST', headers: owner})
    expect(credential.status).toBe(200)
    return {repository, token: (await credential.json()).token}
  }
  const parent = await create(prefix), child = await create(prefix + '-child')
  const environment = (token: string): NodeJS.ProcessEnv => {
    const env = {...process.env, GIT_TERMINAL_PROMPT: '0', GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: windows ? 'NUL' : '/dev/null',
      GIT_CONFIG_COUNT: '2', GIT_CONFIG_KEY_0: 'credential.helper', GIT_CONFIG_VALUE_0: '',
      GIT_CONFIG_KEY_1: 'http.extraHeader', GIT_CONFIG_VALUE_1: 'Authorization: Basic ' + Buffer.from('owner:' + token).toString('base64'),
      GIT_SSL_CAINFO: certificate}
    delete env.GIT_SSL_NO_VERIFY
    for (const field of ['GIT_TRACE', 'GIT_TRACE_CURL', 'GIT_CURL_VERBOSE', 'GIT_TRACE_PACKFILE']) delete env[field]
    return env
  }
  const command = (args: string[], cwd = root, env = environment(parent.token)) => execute(git, args, {cwd, env, timeout: 25000, maxBuffer: 1048576})
  const author = ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid']
  const childWork = join(root, 'child'); await mkdir(childWork)
  await command(['clone', child.repository.clone_url, '.'], childWork, environment(child.token))
  await writeFile(join(childWork, 'child.txt'), 'Separate private submodule repository\n')
  await command(['add', '--', '.'], childWork, environment(child.token))
  await command([...author, 'commit', '-m', 'Child'], childWork, environment(child.token))
  await command(['push', 'origin', 'HEAD:main'], childWork, environment(child.token))
  const childSha = (await command(['rev-parse', 'HEAD'], childWork)).stdout.trim()
  const source = join(root, 'source'); await mkdir(source)
  await command(['clone', parent.repository.clone_url, '.'], source)
  const pointer = 'version https://git-lfs.github.com/spec/v1\noid sha256:' + hash('external media is not hosted') + '\nsize 1234\n'
  await writeFile(join(source, 'external.lfs'), pointer)
  await writeFile(join(source, '.gitattributes'), '*.lfs filter=lfs diff=lfs merge=lfs -text\n')
  await writeFile(join(source, '.gitmodules'), '[submodule "child"]\n\tpath = vendor/child\n\turl = ' + child.repository.clone_url + '\n')
  await command(['add', '--', '.'], source)
  await command(['update-index', '--add', '--cacheinfo', '160000,' + childSha + ',vendor/child'], source)
  for (let index = 0; index < 9; index++) {
    await writeFile(join(source, 'history.txt'), 'History ' + index + '\n')
    await command(['add', '--', 'history.txt'], source)
    await command([...author, 'commit', '-m', 'History ' + index], source)
  }
  const signingKey = join(root, 'signer')
  await execute(keygen, ['-q', '-t', 'ed25519', '-N', '', '-f', signingKey])
  const signing = [...author, '-c', 'gpg.format=ssh', '-c', 'gpg.ssh.program=' + keygen, '-c', 'user.signingkey=' + signingKey]
  await writeFile(join(source, 'signed.txt'), 'Signed content\n')
  await command(['add', '--', 'signed.txt'], source)
  await command([...signing, 'commit', '-S', '-m', 'Signed fixture'], source)
  await command([...signing, 'tag', '-s', 'signed-v1', '-m', 'Signed tag fixture'], source)
  const head = (await command(['rev-parse', 'HEAD'], source)).stdout.trim()
  const tag = (await command(['rev-parse', 'refs/tags/signed-v1'], source)).stdout.trim()
  const commitBytes = (await command(['cat-file', 'commit', head], source)).stdout
  const tagBytes = (await command(['cat-file', 'tag', tag], source)).stdout
  await command(['push', 'origin', 'HEAD:main', 'refs/tags/signed-v1'], source)
  const allowed = join(root, 'allowed-signers')
  await writeFile(allowed, 'fixture@example.invalid ' + await readFile(signingKey + '.pub', 'utf8'))
  const verify = ['-c', 'gpg.format=ssh', '-c', 'gpg.ssh.program=' + keygen, '-c', 'gpg.ssh.allowedSignersFile=' + allowed]
  const protocols = []
  for (const version of [0, 1, 2]) {
    const checkout = join(root, 'protocol-' + version), trace = join(root, 'protocol-' + version + '.packet')
    await command(['-c', 'protocol.version=' + version, 'clone', '--no-checkout', parent.repository.clone_url, checkout], root, {...environment(parent.token), GIT_TRACE_PACKET: trace})
    expect((await command(['rev-parse', 'HEAD'], checkout)).stdout.trim()).toBe(head)
    expect(hash((await command(['cat-file', 'commit', head], checkout)).stdout)).toBe(hash(commitBytes))
    expect(hash((await command(['cat-file', 'tag', tag], checkout)).stdout)).toBe(hash(tagBytes))
    await command([...verify, 'verify-commit', head], checkout)
    await command([...verify, 'verify-tag', 'signed-v1'], checkout)
    if (version === 2) expect(await readFile(trace, 'utf8')).toContain('version 2')
    protocols.push({requested_version: version, commit_sha256: hash(commitBytes), tag_sha256: hash(tagBytes)})
  }
  const shallow = join(root, 'shallow')
  await command(['clone', '--depth=1', '--single-branch', '--branch=main', parent.repository.clone_url, shallow])
  expect((await command(['rev-list', '--count', 'HEAD'], shallow)).stdout.trim()).toBe('1')
  await command(['fetch', '--deepen=3', 'origin', 'main'], shallow)
  expect((await command(['rev-list', '--count', 'HEAD'], shallow)).stdout.trim()).toBe('4')
  await command(['fetch', '--unshallow', 'origin', 'main'], shallow)
  expect((await command(['rev-list', '--count', 'HEAD'], shallow)).stdout.trim()).toBe('10')
  await expect(command(['submodule', 'update', '--init', '--', 'vendor/child'], shallow)).rejects.toThrow()
  await command(['submodule', 'update', '--init', '--', 'vendor/child'], shallow, environment(child.token))
  expect(await readFile(join(shallow, 'vendor/child/child.txt'), 'utf8')).toBe('Separate private submodule repository\n')
  const gitlink = await fetch(upstream + '/api/repos/team/' + prefix + '/snapshot?sha=' + head + '&path=vendor%2Fchild', {headers: owner})
  expect(gitlink.status).toBe(200); expect(await gitlink.json()).toMatchObject({kind: 'submodule', object: childSha})
  expect((await command(['show', head + ':external.lfs'], shallow)).stdout).toBe(pointer)
  const partial = join(root, 'partial-fallback')
  const filtered = await command(['clone', '--filter=blob:none', '--no-checkout', parent.repository.clone_url, partial])
  expect(filtered.stderr).toContain('filtering not recognized by server')
  expect((await command(['rev-list', '--objects', '--missing=print', '--all'], partial)).stdout).not.toMatch(/^\?/m)
  const lfs = await fetch(parent.repository.clone_url + '/info/lfs/objects/batch', {method: 'POST', headers: {...owner, 'content-type': 'application/json'}, body: JSON.stringify({operation: 'download', objects: [{oid: hash('external media is not hosted'), size: 1234}]})})
  expect(lfs.status).toBe(404)
  const sha256 = join(root, 'sha256'); await mkdir(sha256)
  await command(['init', '--template=', '--object-format=sha256', '--initial-branch=main'], sha256)
  await writeFile(join(sha256, 'README.txt'), 'Incompatible repository format\n')
  await command(['add', '--', '.'], sha256); await command([...author, 'commit', '-m', 'SHA256'], sha256)
  await expect(command(['push', parent.repository.clone_url, 'HEAD:sha256-work'], sha256)).rejects.toThrow()
  expect((await command(['ls-remote', parent.repository.clone_url, 'refs/heads/main'])).stdout).toContain(head)
  expect((await command(['ls-remote', parent.repository.clone_url, 'refs/heads/sha256-work'])).stdout.trim()).toBe('')
  const registered = await fetch(upstream + '/api/ssh-keys', {method: 'POST', headers: {...owner, 'idempotency-key': prefix + '-ssh'}, body: JSON.stringify({label: 'Compatibility fixture', public_key: await readFile(signingKey + '.pub', 'utf8')})})
  expect(registered.status).toBe(201)
  const transport = (await (await fetch(upstream + '/api/ssh-keys', {headers: owner})).json()).transport
  const known = join(root, 'known-hosts')
  await writeFile(known, '[' + transport.host + ']:' + transport.port + ' ' + transport.public_key + '\n')
  const sshEnv = {...environment(parent.token), GIT_SSH_VARIANT: 'ssh', GIT_SSH_COMMAND: [ssh, '-F', windows ? 'NUL' : '/dev/null', '-i', signingKey, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + known].map(quote).join(' ')}
  const sshShallow = join(root, 'ssh-shallow')
  await command(['clone', '--depth=1', '--single-branch', '--branch=main', parent.repository.ssh_clone_url, sshShallow], root, sshEnv)
  expect((await command(['rev-list', '--count', 'HEAD'], sshShallow, sshEnv)).stdout.trim()).toBe('1')
  await command(['fetch', '--deepen=3', 'origin', 'main'], sshShallow, sshEnv)
  expect((await command(['rev-list', '--count', 'HEAD'], sshShallow, sshEnv)).stdout.trim()).toBe('4')
  expect((await command(['rev-parse', 'HEAD'], sshShallow, sshEnv)).stdout.trim()).toBe(head)
  const receipt = {repositories: {parent: prefix, child: prefix + '-child'}, source_sha: head, tag_sha: tag, child_sha: childSha,
    git_version: (await command(['--version'])).stdout.trim(), protocols, recorded_at: new Date().toISOString(),
    checks: ['HTTPS protocol 0/1/2 exact objects', 'independent SSH-signature commit/tag verification', 'HTTPS shallow/deepen/unshallow ancestry',
      'gitlink and submodule source retained', 'parent credential cannot fetch separate child repository', 'independent child credential fetch succeeds',
      'native gitlink browse identifies child SHA', 'LFS pointer retained with batch hosting absent', 'partial clone explicitly falls back to full objects',
      'SHA256 push refused with existing SHA1 refs unchanged', 'strict known-host SSH shallow/deepen ancestry'],
    limitations: ['Pinned real Git clients and synthetic small repositories only; no LFS media hosting, native signer trust, filtered-object service or measured capacity.']}
  await writeFile(info.outputPath('git-compatibility-receipt.json'), JSON.stringify(receipt, null, 2) + '\n')
  await writeFile(resolve('test-results-production/git-compatibility-receipt.json'), JSON.stringify(receipt, null, 2) + '\n')
})
