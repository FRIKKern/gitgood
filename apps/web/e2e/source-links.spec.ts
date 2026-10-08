import {test, expect, type Page} from '@playwright/test'
import {fixtureSession as session} from './fixture-session'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {mkdtemp, writeFile, readFile, mkdir} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join, resolve} from 'node:path'
import {createHash} from 'node:crypto'
const execute = promisify(execFile)
const upstream = process.env.GITGOOD_TEST_API_URL ?? 'http://127.0.0.1:48081'
const control = process.env.GITGOOD_TEST_SOURCE_CONTROL
const git = process.env.GITGOOD_GIT ?? 'git'

async function signIn(page: Page, username: string) {
  await page.goto('/')
  await page.getByLabel('Username', {exact: true}).fill(username)
  await page.getByLabel('Password', {exact: true}).fill('synthetic-password')
  await page.getByRole('button', {name: 'Sign in', exact: true}).click()
  await expect(page.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
}

test('native links use each viewer source actor, recover from outage and discard old connection replies', async ({page}, info) => {
  test.setTimeout(180_000)
  if (!control) throw new Error('This journey requires the owned source HTTPS wire fixture')
  const root = await mkdtemp(join(tmpdir(), 'gitgood-linked-source-')), source = join(root, 'source')
  await mkdir(source)
  const env = {...process.env, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: process.platform === 'win32' ? 'NUL' : '/dev/null'}
  const command = (args: string[]) => execute(git, args, {cwd: source, env, timeout: 20000})
  await command(['init', '--template=', '--object-format=sha1', '--initial-branch=main'])
  await writeFile(join(source, 'README.md'), 'Native base for linked source fixture')
  await command(['add', '--', '.'])
  await command(['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Native base'])
  await command(['switch', '-c', 'linked-work'])
  await writeFile(join(source, 'README.md'), 'Native implementation for a source-owned specification')
  await command(['add', '--', '.'])
  await command(['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Implement source intention'])
  const feature = (await command(['rev-parse', 'HEAD'])).stdout.trim()
  await command(['switch', 'main'])
  const bundle = join(root, 'source.bundle')
  await command(['bundle', 'create', bundle, '--branches'])
  const bytes = await readFile(bundle)
  const owner = await session('owner'), reader = await session('reader'), outsider = await session('outsider')
  const name = 'linked-source-' + Date.now()
  const created = await fetch(upstream + '/api/repos', {method: 'POST', headers: {...owner, 'idempotency-key': name}, body: JSON.stringify({team: 'team', name})})
  expect(created.status).toBe(201)
  const repositoryId = (await created.json()).id
  const base = upstream + '/api/repos/team/' + name
  const intake = await fetch(base + '/imports', {method: 'POST', headers: {...owner, 'idempotency-key': 'link-fixture-import'},
    body: JSON.stringify({source_name: 'source.bundle', source_bytes: bytes.length, source_sha256: createHash('sha256').update(bytes).digest('hex')})})
  expect(intake.status).toBe(202)
  const operation = (await intake.json()).operation
  expect((await fetch(base + '/imports/' + operation.id + '/source', {method: 'PUT', headers: {...owner, 'content-type': 'application/octet-stream'}, body: bytes})).status).toBe(202)
  await expect.poll(async () => (await (await fetch(base + '/operations/' + operation.id, {headers: owner})).json()).operation.state).toBe('applied')
  const pullResponse = await fetch(base + '/pulls', {method: 'POST', headers: {...owner, 'idempotency-key': 'linked-source-change'},
    body: JSON.stringify({source: 'linked-work', title: 'Implement the linked specification', body: 'Source stays authoritative.'})})
  expect(pullResponse.status).toBe(200)
  const pull = await pullResponse.json()
  const endpoint = base + '/pulls/' + pull.id + '/links'
  const connect = async (headers: Record<string, string>, token: string, key: string) => {
    const current = await (await fetch(upstream + '/api/connections/barkpark', {headers})).json()
    const response = await fetch(upstream + '/api/connections/barkpark', {method: 'POST', headers: {...headers, 'idempotency-key': key},
      body: JSON.stringify({token, workspace: 'fixture-workspace', project: 'default', dataset: 'production', expected_generation: current.generation})})
    expect(response.status).toBe(200)
    return await response.json()
  }
  let ownerConnection = await connect(owner, 'synthetic-fixture-credential', name + '-owner-connect')
  const readerConnection = await connect(reader, 'synthetic-outsider-credential', name + '-reader-connect')
  expect(ownerConnection.source_identity.token_id).not.toBe(readerConnection.source_identity.token_id)
  await signIn(page, 'owner')
  await page.goto('/repos/team/' + name + '/pulls/' + pull.id)
  const panel = page.getByRole('region', {name: 'Linked Barkpark records', exact: true})
  await expect(page.locator('.code-panel pre')).toContainText('Native implementation for a source-owned specification')
  await expect(panel.getByText('No linked records.', {exact: true})).toBeVisible()
  await panel.getByLabel('Barkpark document ID', {exact: true}).fill('drafts.private-spec')
  const attachRequests: {key: string; body: Record<string, unknown>}[] = []
  let loseAttach = true
  await page.route('**/pulls/' + pull.id + '/links', async route => {
    if (route.request().method() === 'POST') {
      attachRequests.push({key: route.request().headers()['idempotency-key'], body: route.request().postDataJSON()})
      if (loseAttach) {loseAttach = false; expect((await route.fetch()).status()).toBe(200); await route.abort(); return}
    }
    await route.continue()
  })
  await panel.getByRole('button', {name: 'Attach source record', exact: true}).click()
  await expect(panel.getByRole('status')).toContainText('The link request could not be confirmed')
  await expect(panel.getByRole('article')).toHaveCount(1)
  await panel.getByRole('button', {name: 'Attach source record', exact: true}).click()
  await expect(panel.getByRole('status')).toContainText('Link request confirmed')
  expect(attachRequests).toHaveLength(2)
  expect(attachRequests[1]).toEqual(attachRequests[0])
  const first = (await (await fetch(endpoint, {headers: owner})).json()).links[0]
  const article = panel.getByRole('article')
  await article.getByRole('button', {name: 'Open source context', exact: true}).click()
  await expect(article.getByRole('heading', {name: 'Private source specification', exact: true})).toBeVisible()
  await expect(article.getByRole('link', {name: 'Open in Barkpark Studio', exact: true})).toHaveAttribute('href', /\/studio\/open\/paper\/drafts.private-spec$/)
  await page.screenshot({path: info.outputPath('linked-source-available.png'), fullPage: true})
  const sourceState = async (status: number) => {
    expect((await fetch(control + '/control/document-state', {method: 'POST',
      headers: {'content-type': 'application/json', authorization: 'Bearer synthetic-fixture-control'},
      body: JSON.stringify({status})})).status).toBe(200)
  }
  await sourceState(503)
  await expect(article.getByRole('alert')).toContainText('Barkpark context is unavailable', {timeout: 15000})
  await expect(article.getByRole('heading', {name: 'Private source specification', exact: true})).toHaveCount(0)
  await expect(page.getByRole('heading', {name: 'Implement the linked specification', exact: true})).toBeVisible()
  await expect(page.locator('.code-panel pre')).toContainText('Native implementation for a source-owned specification')
  await page.screenshot({path: info.outputPath('linked-source-unavailable.png'), fullPage: true})
  await sourceState(404)
  await article.getByRole('button', {name: 'Retry source context', exact: true}).click()
  await expect(article.getByRole('alert')).toContainText('may be missing or inaccessible')
  await sourceState(200)
  await article.getByRole('button', {name: 'Retry source context', exact: true}).click()
  await expect(article.getByRole('heading', {name: 'Private source specification', exact: true})).toBeVisible()

  let releaseHeld: (() => void) | undefined, heldDone: Promise<void> | undefined
  await page.route('**/links/' + first.id + '?connection_generation=*', async route => {
    const response = await route.fetch()
    expect(response.status()).toBe(200)
    await new Promise<void>(resolve => {releaseHeld = resolve})
    heldDone = route.fulfill({response}).catch(() => {})
    await heldDone
  })
  // Force a real source read, then hold its permitted response across disconnect.
  await page.reload()
  await panel.getByRole('button', {name: 'Open source context', exact: true}).click()
  await expect.poll(() => !!releaseHeld).toBe(true)
  const disconnected = await fetch(upstream + '/api/connections/barkpark/disconnect', {method: 'POST',
    headers: {...owner, 'idempotency-key': name + '-disconnect'},
    body: JSON.stringify({expected_generation: ownerConnection.generation})})
  expect(disconnected.status).toBe(200)
  await expect(panel.getByText('Source context requires your current Barkpark connection.', {exact: true})).toBeVisible({timeout: 15000})
  releaseHeld!(); releaseHeld = undefined
  await expect.poll(() => !!heldDone).toBe(true)
  await heldDone
  await page.unroute('**/links/' + first.id + '?connection_generation=*')
  await expect(panel.getByRole('heading', {name: 'Private source specification', exact: true})).toHaveCount(0)
  await page.screenshot({path: info.outputPath('linked-source-disconnected.png'), fullPage: true})

  await page.goto('/')
  await page.getByRole('button', {name: 'Sign out', exact: true}).click()
  await signIn(page, 'reader')
  await page.goto('/repos/team/' + name + '/pulls/' + pull.id)
  await panel.getByRole('button', {name: 'Open source context', exact: true}).click()
  await expect(panel.getByRole('alert')).toContainText('Barkpark refused source access for your connection')
  await expect(panel.getByRole('heading', {name: 'Private source specification', exact: true})).toHaveCount(0)
  await expect(panel.getByRole('link', {name: 'Open in Barkpark Studio', exact: true})).toHaveCount(0)
  await expect(panel.getByRole('button', {name: 'Remove linked record', exact: true})).toHaveCount(0)
  const readerRemove = await fetch(endpoint + '/' + first.id + '/remove', {method: 'POST',
    headers: {...reader, 'idempotency-key': name + '-reader-remove'}, body: JSON.stringify({generation: first.generation})})
  expect(readerRemove.status).toBe(403)
  for (const id of [first.id, crypto.randomUUID()]) {
    const refused = await fetch(endpoint + '/' + id, {headers: outsider})
    expect(refused.status).toBe(404)
    expect(await refused.json()).toEqual({error: 'source_link_not_found'})
  }
  await page.setViewportSize({width: 390, height: 844})
  await page.screenshot({path: info.outputPath('linked-source-denied-mobile.png'), fullPage: true})
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.setViewportSize({width: 1280, height: 900})
  await page.goto('/')
  await page.getByRole('button', {name: 'Sign out', exact: true}).click()
  ownerConnection = await connect(owner, 'synthetic-fixture-credential', name + '-owner-reconnect')
  await signIn(page, 'owner')
  await page.goto('/repos/team/' + name + '/pulls/' + pull.id)
  await panel.getByRole('button', {name: 'Remove linked record', exact: true}).click()
  await expect(panel.getByText('Linked record · removed', {exact: true})).toBeVisible()
  const historical = await fetch(endpoint, {method: 'POST', headers: {...owner, 'idempotency-key': attachRequests[0].key},
    body: JSON.stringify(attachRequests[0].body)})
  expect(historical.status).toBe(200)
  expect(await historical.json()).toEqual(first)
  expect((await (await fetch(endpoint, {headers: owner})).json()).links[0].state).toBe('removed')
  await panel.getByLabel('Barkpark document ID', {exact: true}).fill('drafts.private-spec')
  await panel.getByRole('button', {name: 'Attach source record', exact: true}).click()
  await expect(panel.getByRole('button', {name: 'Remove linked record', exact: true})).toBeVisible()
  const currentLinks = (await (await fetch(endpoint, {headers: owner})).json()).links
  expect(currentLinks).toHaveLength(1)
  expect(currentLinks[0].id).toBe(first.id)
  expect(currentLinks[0].generation).not.toBe(first.generation)
  const receipt = {repository: name, repository_id: repositoryId, pull_id: pull.id, feature_sha: feature,
    link: currentLinks[0], original_receipt: first, original_attach_request: attachRequests[0],
    owner_connection_generation: ownerConnection.generation, reader_connection_generation: readerConnection.generation,
    source_actors: [ownerConnection.source_identity.token_id, readerConnection.source_identity.token_id],
    source_fixture: 'Owned synthetic HTTPS wire with explicit issuer trust; normal backend TLS verification',
    checks: ['real Git import and native change', 'actual encrypted source connections with distinct actors',
      'lost attach reply reuses key and creates one link', 'source context and Studio URL require viewer access',
      'source outage clears title and preserves native change', 'missing is distinguished without claiming deletion',
      'outage recovery retains one native link', 'held old connection reply discarded after disconnect',
      'source denied reader sees no title or locator', 'reader cannot remove, foreign equals absent',
      'mobile width', 'removal then historical attach replay does not reactivate', 'fresh attach reactivates same identity'],
    limitations: ['Synthetic source wire; live deployed Barkpark navigation is a separate experiment.',
      'No reverse-pointer operation journal or complete J10 acceptance.']}
  await writeFile(info.outputPath('source-link-receipt.json'), JSON.stringify(receipt, null, 2) + '\n')
  await writeFile(resolve(process.env.GITGOOD_TEST_PRODUCTION === 'true' ? 'test-results-production' : 'test-results', 'source-link-receipt.json'), JSON.stringify(receipt, null, 2) + '\n')
})
