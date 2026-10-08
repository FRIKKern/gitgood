import {test, expect} from '@playwright/test'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {mkdtemp, writeFile, readFile, mkdir} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join, resolve} from 'node:path'
import {createHash, randomBytes} from 'node:crypto'
const execute = promisify(execFile)
const upstream = process.env.GITGOOD_TEST_API_URL ?? 'http://127.0.0.1:47841'
const git = process.env.GITGOOD_GIT ?? 'git'
async function session(username: string) {
  const result = await fetch(upstream + '/api/session', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({username, password: 'synthetic-password'})})
  expect(result.status).toBe(200)
  return {authorization: 'Bearer ' + /gitgood_session=([^;]+)/.exec(result.headers.getSetCookie()[0])![1], 'content-type': 'application/json'}
}
test('private tag release preserves identity and assets through lost replies, correction and withdrawal', async ({page, browser}, info) => {
  test.setTimeout(120_000)
  const root = await mkdtemp(join(tmpdir(), 'gitgood-release-')), source = join(root, 'source')
  await mkdir(source)
  const env = {...process.env, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: process.platform === 'win32' ? 'NUL' : '/dev/null'}
  const command = (args: string[]) => execute(git, args, {cwd: source, env, timeout: 20000})
  await command(['init', '--template=', '--object-format=sha1', '--initial-branch=main'])
  const commit = async (text: string) => {
    await writeFile(join(source, 'README.md'), text)
    await command(['add', '--', '.'])
    await command(['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', text])
    return (await command(['rev-parse', 'HEAD'])).stdout.trim()
  }
  const first = await commit('Actual initial release change')
  const target = await commit('Actual second release change')
  await command(['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'tag', '-a', 'v1', '-m', 'Version one', target])
  const tagObject = (await command(['rev-parse', 'refs/tags/v1'])).stdout.trim()
  const main = await commit('Main work after release tag')
  await command(['tag', 'v2', main])
  const bundle = join(root, 'source.bundle')
  await command(['bundle', 'create', bundle, '--branches', '--tags'])
  const bundled = await readFile(bundle)
  const owner = await session('owner'), reader = await session('reader'), outsider = await session('outsider')
  const name = 'release-' + Date.now()
  const created = await fetch(upstream + '/api/repos', {method: 'POST', headers: {...owner, 'idempotency-key': name}, body: JSON.stringify({team: 'team', name})})
  expect(created.status).toBe(201)
  const base = upstream + '/api/repos/team/' + name
  const intake = await fetch(base + '/imports', {method: 'POST', headers: {...owner, 'idempotency-key': 'release-import'}, body: JSON.stringify({source_name: 'source.bundle', source_bytes: bundled.length, source_sha256: createHash('sha256').update(bundled).digest('hex')})})
  expect(intake.status).toBe(202)
  const operation = (await intake.json()).operation
  expect((await fetch(base + '/imports/' + operation.id + '/source', {method: 'PUT', headers: {...owner, 'content-type': 'application/octet-stream'}, body: bundled})).status).toBe(202)
  await expect.poll(async () => (await (await fetch(base + '/operations/' + operation.id, {headers: owner})).json()).operation.state).toBe('applied')
  const invalid = await fetch(base + '/releases', {method: 'POST', headers: {...owner, 'idempotency-key': 'wrong-commit'}, body: JSON.stringify({tag: 'v1', commit_sha: main, title: 'Wrong release', notes: 'Must not become released'})})
  expect(invalid.status).toBe(409)
  for (const actor of [reader, outsider]) {
    const denial = await fetch(base + '/releases', {method: 'POST', headers: {...actor, 'idempotency-key': 'unauthorized-release'}, body: JSON.stringify({tag: 'v1', commit_sha: target, title: 'Unauthorized', notes: 'Private notes'})})
    expect([403, 404]).toContain(denial.status)
  }
  await page.goto('/')
  await page.getByLabel('Username').fill('owner')
  await page.getByLabel('Password').fill('synthetic-password')
  await page.getByRole('button', {name: 'Sign in', exact: true}).click()
  await expect(page.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
  await page.goto('/repos/team/' + name)
  const panel = page.getByRole('region', {name: 'Releases', exact: true})
  await panel.getByText('Create release draft', {exact: true}).click()
  await panel.getByLabel('Release tag').selectOption('v1')
  await panel.getByLabel('Release title', {exact: true}).fill('Private version one')
  const notes = 'Reviewed release notes <script>window.releaseExecuted=true</script>'
  await panel.getByLabel('Release notes', {exact: true}).fill(notes)
  let loseDraft = true
  await page.route('**/releases', async route => {
    if (route.request().method() === 'POST' && loseDraft) {loseDraft = false; expect((await route.fetch()).status()).toBe(200); await route.abort()}
    else await route.continue()
  })
  await panel.getByRole('button', {name: 'Save draft', exact: true}).click()
  await expect(panel.getByRole('alert')).toBeVisible()
  await panel.getByRole('button', {name: 'Retry same release operation'}).click()
  await expect(panel.getByRole('status')).toHaveText('Release draft')
  const id = /#release-([0-9a-f-]{36})/.exec(page.url())![1]
  const recordUrl = base + '/releases/' + id
  let record = (await (await fetch(recordUrl, {headers: owner})).json()).release
  expect(record.commit_sha).toBe(target)
  expect(record.tag_object).toBe(tagObject)
  expect(record.changes.commits.map((c: {sha: string}) => c.sha)).toEqual([target, first])
  expect(record.changes.commits.some((c: {sha: string}) => c.sha === main)).toBe(false)
  expect((await (await fetch(base + '/releases', {headers: owner})).json()).releases).toHaveLength(1)
  expect(await page.evaluate(() => 'releaseExecuted' in window)).toBe(false)
  const assetPath = join(root, 'private-package.bin'), assetBytes = randomBytes(1_310_720)
  await writeFile(assetPath, assetBytes)
  const reserved = await fetch(recordUrl + '/assets', {method: 'POST', headers: {...owner, 'idempotency-key': 'partial-asset'},
    body: JSON.stringify({name: 'private-package.bin', size: assetBytes.length, sha256: createHash('sha256').update(assetBytes).digest('hex')})})
  expect(reserved.status).toBe(200)
  const waitingAsset = (await reserved.json()).asset
  expect((await fetch(recordUrl + '/assets/' + waitingAsset.id + '/source', {method: 'PUT', headers: {...owner, 'content-type': 'application/octet-stream'}, body: assetBytes.subarray(0, 128)})).status).toBe(409)
  await page.reload()
  await expect(panel.getByRole('status')).toHaveText('Release draft')
  await panel.getByLabel('Release asset', {exact: true}).setInputFiles(assetPath)
  let loseAsset = true
  await page.route('**/assets/*/source', async route => {
    if (loseAsset) {loseAsset = false; expect((await route.fetch()).status()).toBe(200); await route.abort()}
    else await route.continue()
  })
  await panel.getByRole('button', {name: 'Attach asset', exact: true}).click()
  await expect(panel.getByRole('alert')).toBeVisible()
  await panel.getByRole('button', {name: 'Retry same asset', exact: true}).click()
  record = (await (await fetch(recordUrl, {headers: owner})).json()).release
  expect(record.assets).toHaveLength(1)
  expect(record.assets[0].state).toBe('ready')
  const asset = record.assets[0]
  const downloadUrl = recordUrl + '/assets/' + asset.id + '/download'
  expect((await fetch(downloadUrl, {headers: reader})).status).toBe(409)
  let losePublication = true
  await page.route('**/releases/*/actions', async route => {
    if (losePublication) {losePublication = false; expect((await route.fetch()).status()).toBe(200); await route.abort()}
    else await route.continue()
  })
  await panel.getByRole('button', {name: 'Publish reviewed release', exact: true}).click()
  await expect(panel.getByRole('alert')).toBeVisible()
  await panel.getByRole('button', {name: 'Retry same release operation'}).click()
  await expect(panel.getByRole('status')).toHaveText('Release published')
  await page.reload()
  await expect(panel.getByRole('status')).toHaveText('Release published')
  const [download] = await Promise.all([page.waitForEvent('download'), panel.getByRole('link', {name: 'private-package.bin', exact: true}).click()])
  expect(download.suggestedFilename()).toBe('private-package.bin')
  const downloaded = await readFile((await download.path())!)
  expect(downloaded.equals(assetBytes)).toBe(true)
  const readable = await fetch(downloadUrl, {headers: reader})
  expect(readable.status).toBe(200)
  expect(readable.headers.get('cache-control')).toBe('no-store')
  expect(readable.headers.get('content-disposition')).toBe('attachment; filename="private-package.bin"')
  expect(createHash('sha256').update(Buffer.from(await readable.arrayBuffer())).digest('hex')).toBe(asset.sha256)
  expect((await fetch(downloadUrl, {headers: outsider})).status).toBe(404)
  const readerPage = await browser.newPage()
  await readerPage.goto('/')
  await readerPage.getByLabel('Username').fill('reader')
  await readerPage.getByLabel('Password').fill('synthetic-password')
  await readerPage.getByRole('button', {name: 'Sign in', exact: true}).click()
  await expect(readerPage.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
  await readerPage.goto('/repos/team/' + name + '#release-' + id)
  await expect(readerPage.getByRole('region', {name: 'Releases', exact: true}).getByRole('status')).toHaveText('Release published')
  await expect(readerPage.getByRole('button', {name: 'Publish reviewed release'})).toHaveCount(0)
  await readerPage.close()
  await panel.getByText('Correct or withdraw release', {exact: true}).click()
  await panel.getByLabel('Updated release notes').fill('Corrected claims about actual included changes')
  await panel.getByLabel('Correction or withdrawal reason').fill('Clarify the original notes')
  await panel.getByRole('button', {name: 'Record correction', exact: true}).click()
  await expect(panel.locator('.release-notes')).toHaveText('Corrected claims about actual included changes')
  await panel.getByText('Release history', {exact: true}).click()
  await expect(panel.locator('.review-event').filter({hasText: /^publish ·/})).toContainText(notes)
  await expect(panel.locator('.review-event').filter({hasText: /^correct ·/})).toContainText('Clarify the original notes')
  const publicationHistory = await (await fetch(recordUrl, {headers: owner})).json()
  expect(publicationHistory.events.filter((e: {kind: string}) => e.kind === 'publish')).toHaveLength(1)
  const candidate = (await execute(git, ['rev-parse', 'HEAD'], {cwd: resolve('../..'), timeout: 15000})).stdout.trim()
  const trackedState = (await execute(git, ['status', '--porcelain'], {cwd: resolve('../..'), timeout: 15000})).stdout
  const receipt = {candidate, trackedWorktreeClean: trackedState === '',
    requirement: createHash('sha256').update(await readFile(resolve('../../docs/journeys/J12.md'))).digest('hex'),
    producer: 'Codex automated browser/client fixture', actors: ['owner', 'reader', 'outsider'],
    repository: name, release_id: id, commit_sha: target, tag_object: tagObject, main_sha: main,
    changes: [target, first], asset: {id: asset.id, name: asset.name, size: asset.size, sha256: asset.sha256},
    checks: ['lost draft reply retry singular', 'lost asset reply retry singular', 'lost publication reply retry singular',
      'private attachment downloads exact bytes through BFF', 'reader/outsider and invalid commit rejected',
      'correction retained original notes and actors', 'withdrawal retained claims and denied downloads'], recordedAt: new Date().toISOString()}
  await panel.screenshot({path: info.outputPath('release.png')})
  await page.setViewportSize({width: 390, height: 844})
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await panel.screenshot({path: info.outputPath('release-mobile.png')})
  await panel.getByLabel('Correction or withdrawal reason').fill('Withdraw mistaken publication')
  await panel.getByRole('button', {name: 'Withdraw release', exact: true}).click()
  await expect(panel.getByRole('status')).toHaveText('Release withdrawn')
  expect((await fetch(downloadUrl, {headers: reader})).status).toBe(409)
  const withdrawn = await (await fetch(recordUrl, {headers: owner})).json()
  expect(withdrawn.release.commit_sha).toBe(target)
  expect(withdrawn.events.some((e: {kind: string; reason: string}) => e.kind === 'withdraw' && e.reason === 'Withdraw mistaken publication')).toBe(true)
  // Leave a second published release for the copied-installation restart check.
  const persisted = await fetch(base + '/releases', {method: 'POST', headers: {...owner, 'idempotency-key': 'persistent-release'},
    body: JSON.stringify({tag: 'v2', commit_sha: main, base_sha: target, title: 'Persistent version two', notes: 'Includes only the next actual commit'})})
  expect(persisted.status).toBe(200)
  const persistent = (await persisted.json()).release
  const persistentBytes = Buffer.from('Persistent checksummed release asset')
  const persistentIntent = await fetch(base + '/releases/' + persistent.id + '/assets', {method: 'POST', headers: {...owner, 'idempotency-key': 'persistent-asset'},
    body: JSON.stringify({name: 'persistent.bin', size: persistentBytes.length, sha256: createHash('sha256').update(persistentBytes).digest('hex')})})
  expect(persistentIntent.status).toBe(200)
  const persistentAsset = (await persistentIntent.json()).asset
  expect((await fetch(base + '/releases/' + persistent.id + '/assets/' + persistentAsset.id + '/source', {method: 'PUT', headers: {...owner, 'content-type': 'application/octet-stream'}, body: persistentBytes})).status).toBe(200)
  const readyRelease = (await (await fetch(base + '/releases/' + persistent.id, {headers: owner})).json()).release
  const published = await fetch(base + '/releases/' + persistent.id + '/actions', {method: 'POST', headers: {...owner, 'idempotency-key': 'persistent-publication'},
    body: JSON.stringify({kind: 'publish', version: readyRelease.version, notes_digest: readyRelease.notes_digest})})
  expect(published.status).toBe(200)
  const publishedRelease = (await published.json()).release
  expect(publishedRelease.changes.commits.map((c: {sha: string}) => c.sha)).toEqual([main])
  const text = JSON.stringify({...receipt, withdrawnState: withdrawn.release.state,
    published: {id: publishedRelease.id, commit_sha: main, tag: 'v2', tag_object: main,
      asset: publishedRelease.assets.find((a: {id: string}) => a.id === persistentAsset.id)}}, null, 2) + '\n'
  await writeFile(info.outputPath('release-receipt.json'), text)
  await writeFile(resolve(process.env.GITGOOD_TEST_PRODUCTION === 'true' ? 'test-results-production' : 'test-results', 'release-receipt.json'), text)
})
