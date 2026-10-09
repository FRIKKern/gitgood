import {test, expect} from '@playwright/test'
import {fixtureSession as session} from './fixture-session'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {mkdtemp, readFile, writeFile, mkdir} from 'node:fs/promises'
import {randomBytes, createHash} from 'node:crypto'
import {tmpdir} from 'node:os'
import {join, resolve} from 'node:path'
import {request as httpRequest} from 'node:http'
const run = promisify(execFile)
const upstream = process.env.GITGOOD_TEST_API_URL ?? 'http://127.0.0.1:47841'
const git = process.env.GITGOOD_GIT ?? 'git'

test('browser full bundle import survives lost replies, preserves history and tags, and rejects unsafe intake', async ({page}, info) => {
  test.setTimeout(120_000)
  const root = await mkdtemp(join(tmpdir(), 'gitgood-import-'))
  const source = join(root, 'source')
  await mkdir(source)
  const env = {...process.env, GIT_TERMINAL_PROMPT: '0', GIT_CONFIG_NOSYSTEM: '1',
    GIT_CONFIG_GLOBAL: process.platform === 'win32' ? 'NUL' : '/dev/null',
    ...(process.env.GITGOOD_TEST_CA ? {GIT_SSL_CAINFO: process.env.GITGOOD_TEST_CA} : {})}
  delete env.GIT_SSL_NO_VERIFY
  const command = (args: string[], cwd = source) => run(git, args, {cwd, env, timeout: 20000, maxBuffer: 2_097_152})
  await command(['init', '--template=', '--object-format=sha1', '--initial-branch=main'])
  await writeFile(join(source, 'README.md'), '# Imported private history\n<script>window.importedCodeRan=true</script>\n')
  const binary = randomBytes(1_310_720)
  await writeFile(join(source, 'binary.dat'), binary)
  await writeFile(join(source, '.gitmodules'), '[submodule "example"]\n path = example\n url = https://example.invalid/unavailable.git\n')
  await writeFile(join(source, 'large-pointer.dat'), 'version https://git-lfs.github.com/spec/v1\noid sha256:' + 'a'.repeat(64) + '\nsize 9999999\n')
  const commit = async (message: string) => {
    await command(['add', '--', '.'])
    await command(['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', message])
    return (await command(['rev-parse', 'HEAD'])).stdout.trim()
  }
  const initial = await commit('Original history')
  await writeFile(join(source, 'next.txt'), 'Second revision\n')
  const main = await commit('Second revision')
  await command(['switch', '-c', 'feature'])
  await writeFile(join(source, 'feature.txt'), 'Feature history\n')
  const feature = await commit('Feature revision')
  await command(['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'tag', '-a', 'v1', '-m', 'Imported tag', main])
  const tag = (await command(['rev-parse', 'refs/tags/v1'])).stdout.trim()
  const bundle = join(root, 'source.bundle')
  await command(['bundle', 'create', bundle, '--branches', '--tags'])
  const content = await readFile(bundle)
  expect(content.byteLength).toBeGreaterThan(1_048_576)
  const sourceSha = createHash('sha256').update(content).digest('hex')
  const sourceParams = {source_name: 'source.bundle', source_sha256: sourceSha, source_bytes: content.byteLength}
  const owner = await session('owner'), reader = await session('reader'), outsider = await session('outsider')
  const name = 'import-' + Date.now()
  const create = await fetch(upstream + '/api/repos', {method: 'POST', headers: {...owner, 'idempotency-key': name},
    body: JSON.stringify({team: 'team', name})})
  expect(create.status).toBe(201)
  const repository = await create.json()
  const api = upstream + '/api/repos/team/' + name
  for (const identity of [reader, outsider]) {
    const denied = await fetch(api + '/imports', {method: 'POST', headers: {...identity, 'idempotency-key': 'denied-import'},
      body: JSON.stringify(sourceParams)})
    expect([403, 404, 409]).toContain(denied.status)
  }
  const urlDenied = await fetch(api + '/imports', {method: 'POST', headers: {...owner, 'idempotency-key': 'url-import'},
    body: JSON.stringify({...sourceParams, source_url: 'http://127.0.0.1/private'})})
  expect(urlDenied.status).toBe(409)

  // Aborted upload leaves exactly the same waiting responsibility for a complete retry.
  const intake = await fetch(api + '/imports', {method: 'POST', headers: {...owner, 'idempotency-key': 'interrupted-intake'},
    body: JSON.stringify(sourceParams)})
  expect(intake.status).toBe(202)
  const waiting = (await intake.json()).operation
  await new Promise<void>((resolve, reject) => {
    const interrupted = httpRequest(api + '/imports/' + waiting.id + '/source', {method: 'PUT',
      headers: {...owner, 'content-type': 'application/octet-stream', 'content-length': String(content.byteLength)}}, response => {
        response.resume(); response.once('end', resolve)
      })
    interrupted.once('error', resolve)
    interrupted.write(content.subarray(0, 128), error => {if (error) reject(error); else interrupted.destroy()})
  })
  const partial = await fetch(api + '/imports/' + waiting.id + '/source', {method: 'PUT',
    headers: {...owner, 'content-type': 'application/octet-stream'}, body: content.subarray(0, 128)})
  expect(partial.status).toBe(409)
  const stillWaiting = await (await fetch(api + '/operations/' + waiting.id, {headers: owner})).json()
  expect(stillWaiting.operation.metadata.phase).toBe('waiting_source')

  await page.goto('/')
  await page.getByLabel('Username').fill('owner')
  await page.getByLabel('Password').fill('synthetic-password')
  await page.getByRole('button', {name: 'Sign in', exact: true}).click()
  await expect(page.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
  await page.goto('/repos/team/' + name)
  await expect(page.getByRole('heading', {name: 'Repository import'})).toBeVisible()
  await expect(page.getByText('LFS objects, submodule repositories', {exact: false})).toBeVisible()
  await page.getByLabel('Git bundle file').setInputFiles(bundle)
  let loseReply = true
  await page.route('**/imports/*/source', async route => {
    if (route.request().method() === 'PUT' && loseReply) {
      loseReply = false
      const persisted = await route.fetch()
      expect(persisted.status()).toBe(202)
      await route.abort()
    } else await route.continue()
  })
  await page.getByRole('button', {name: 'Import bundle', exact: true}).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('status').filter({hasText: 'Import applied'})).toBeVisible({timeout: 60000})
  await page.reload()
  await expect(page.getByRole('status').filter({hasText: 'Import applied'})).toBeVisible()
  await expect(page.getByRole('heading', {name: 'Commit history'})).toBeVisible()
  const operations = (await (await fetch(api + '/operations', {headers: owner})).json()).operations.filter((o: {kind: string}) => o.kind === 'import')
  expect(operations).toHaveLength(1)
  const operation = operations[0]
  expect(operation.id).toBe(waiting.id)
  expect(operation.state).toBe('applied')
  expect(operation.metadata.source_sha256).toBe(sourceSha)
  expect(operation.updates).toHaveLength(3)
  expect(operation.updates.map((u: {ref: string; new: string}) => [u.ref, u.new]).sort()).toEqual(
    [['refs/heads/feature', feature], ['refs/heads/main', main], ['refs/tags/v1', tag]].sort())
  const duplicate = await fetch(api + '/imports', {method: 'POST', headers: {...owner, 'idempotency-key': 'interrupted-intake'},
    body: JSON.stringify(sourceParams)})
  expect((await duplicate.json()).operation.id).toBe(waiting.id)
  const overwrite = await fetch(api + '/imports', {method: 'POST', headers: {...owner, 'idempotency-key': 'overwrite-import'},
    body: JSON.stringify(sourceParams)})
  expect(overwrite.status).toBe(409)

  await page.goto('/repos/team/' + name + '?sha=' + initial + '&path=README.md')
  await expect(page.locator('.source')).toContainText('<script>window.importedCodeRan=true</script>')
  expect(await page.evaluate(() => 'importedCodeRan' in window)).toBe(false)
  const credential = await (await fetch(api + '/credentials', {method: 'POST', headers: owner})).json()
  const clientEnv = {...env, GIT_CONFIG_COUNT: '2', GIT_CONFIG_KEY_0: 'credential.helper', GIT_CONFIG_VALUE_0: '',
    GIT_CONFIG_KEY_1: 'http.extraHeader', GIT_CONFIG_VALUE_1: 'Authorization: Basic ' + Buffer.from('owner:' + credential.token).toString('base64')}
  const clone = join(root, 'clone')
  await run(git, ['clone', repository.clone_url, clone], {env: clientEnv, timeout: 20000})
  expect(await readFile(join(clone, 'binary.dat'))).toEqual(binary)
  expect((await command(['for-each-ref', '--format=%(objectname)', 'refs/tags/v1'], clone)).stdout.trim()).toBe(tag)
  expect((await command(['rev-list', 'refs/remotes/origin/feature'], clone)).stdout.trim().split('\n')).toEqual([feature, main, initial])
  expect((await command(['fsck', '--full', '--strict'], clone)).stderr).not.toContain('error:')
  const remote = await run(git, ['ls-remote', repository.clone_url], {env: clientEnv, timeout: 20000})
  expect(remote.stdout).not.toContain('refs/gitgood/')
  await page.goto('/repos/team/' + name)
  await expect(page.getByRole('status').filter({hasText: 'Import applied'})).toBeVisible()
  await expect(page.getByRole('heading', {name: 'Commit history'})).toBeVisible()
  await page.getByText('Import record', {exact: true}).click()
  await page.screenshot({path: info.outputPath('import.png'), fullPage: true})
  await page.setViewportSize({width: 390, height: 844})
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({path: info.outputPath('import-mobile.png'), fullPage: true})
  await page.setViewportSize({width: 1280, height: 720})

  // Lost intent creation is replayed before uploading; it never creates a second import.
  const retryName = name + '-intent'
  const retryCreate = await fetch(upstream + '/api/repos', {method: 'POST', headers: {...owner, 'idempotency-key': retryName},
    body: JSON.stringify({team: 'team', name: retryName})})
  expect(retryCreate.status).toBe(201)
  await page.goto('/repos/team/' + retryName)
  let loseIntent = true
  await page.route('**/api/repos/team/' + retryName + '/imports', async route => {
    if (route.request().method() === 'POST' && loseIntent) {
      loseIntent = false
      const persisted = await route.fetch()
      expect(persisted.status()).toBe(202)
      await route.abort()
    } else await route.continue()
  })
  await page.getByLabel('Git bundle file').setInputFiles(bundle)
  await page.getByRole('button', {name: 'Import bundle', exact: true}).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('status').filter({hasText: 'Import waiting source'})).toBeVisible()
  await page.getByRole('button', {name: 'Retry import', exact: true}).click()
  await expect(page.getByRole('status').filter({hasText: 'Import applied'})).toBeVisible({timeout: 60000})
  const replayed = (await (await fetch(upstream + '/api/repos/team/' + retryName + '/operations?kind=import', {headers: owner})).json()).operations
  expect(replayed).toHaveLength(1)
  expect(replayed[0].state).toBe('applied')
  const result = {recordedAt: new Date().toISOString(), repository_id: repository.id, repository_name: name,
    lost_intent_operation_id: replayed[0].id,
    operation_id: operation.id, actor_id: operation.actor_id, credential_id: operation.credential_id,
    source_sha256: sourceSha, source_bytes: content.byteLength, updates: operation.updates,
    main, tag, feature, initial, unsupported: operation.metadata.warnings,
    checks: ['reader/outsider denied', 'URL import denied', 'disconnected and truncated intake preserves original operation', 'lost intent creation converges',
      'lost full-upload response converges', 'single import/repository responsibility',
      'exact branch and annotated tag objects', 'full historical commit chain', 'binary bytes preserved',
      'source code escaped', 'hidden marker absent from advertisement', 'nonempty import denied', 'strict fsck']}
  await writeFile(info.outputPath('import-receipt.json'), JSON.stringify(result, null, 2))
  const summary = resolve(process.env.GITGOOD_TEST_PRODUCTION === 'true' ? 'test-results-production' : 'test-results', 'import-receipt.json')
  await writeFile(summary, JSON.stringify(result, null, 2))
})
