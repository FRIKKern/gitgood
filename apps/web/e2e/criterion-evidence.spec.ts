import {test, expect} from '@playwright/test'
import {fixtureSession as session} from './fixture-session'
import {appliedImport} from './fixture-operation'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {mkdtemp, writeFile, readFile, mkdir} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join, resolve} from 'node:path'
import {createHash} from 'node:crypto'
const execute = promisify(execFile)
const upstream = process.env.GITGOOD_TEST_API_URL ?? 'http://127.0.0.1:48081'
const control = process.env.GITGOOD_TEST_SOURCE_CONTROL
const hash = (bytes: string | Buffer) => createHash('sha256').update(bytes).digest('hex')

test('criterion evidence binds real Git and source revisions, retains history and protects artifacts', async ({page}, info) => {
  test.setTimeout(240_000)
  if (!control) throw new Error('Evidence journey requires the owned source fixture')
  const owner = await session('owner'), reader = await session('reader'), outsider = await session('outsider')
  const root = await mkdtemp(join(tmpdir(), 'gitgood-criterion-evidence-')), source = join(root, 'source')
  await mkdir(source)
  const env = {...process.env, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: process.platform === 'win32' ? 'NUL' : '/dev/null'}
  const command = (args: string[]) => execute(process.env.GITGOOD_GIT ?? 'git', args, {cwd: source, env, timeout: 20000})
  await command(['init', '--template=', '--object-format=sha1', '--initial-branch=main'])
  await writeFile(join(source, 'README.md'), 'Evidence base\n')
  await command(['add', '--', '.'])
  await command(['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Evidence base'])
  await command(['switch', '-c', 'criterion-work'])
  await writeFile(join(source, 'README.md'), 'Evidence implementation\n')
  await command(['add', '--', '.'])
  await command(['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Evidence implementation'])
  const bundle = join(root, 'fixture.bundle')
  await command(['bundle', 'create', bundle, '--branches'])
  const bytes = await readFile(bundle), name = 'criterion-evidence-' + Date.now()
  const creation = await fetch(upstream + '/api/repos', {method: 'POST', headers: {...owner, 'idempotency-key': name}, body: JSON.stringify({team: 'team', name})})
  expect(creation.status).toBe(201)
  const repositoryId = (await creation.json()).id, base = upstream + '/api/repos/team/' + name
  const intake = await fetch(base + '/imports', {method: 'POST', headers: {...owner, 'idempotency-key': name + '-import'}, body: JSON.stringify({source_name: 'fixture.bundle', source_bytes: bytes.length, source_sha256: hash(bytes)})})
  expect(intake.status).toBe(202)
  const operation = (await intake.json()).operation
  expect((await fetch(base + '/imports/' + operation.id + '/source', {method: 'PUT', headers: {...owner, 'content-type': 'application/octet-stream'}, body: bytes})).status).toBe(202)
  await appliedImport(base, operation.id, owner)
  const pullResponse = await fetch(base + '/pulls', {method: 'POST', headers: {...owner, 'idempotency-key': name + '-pull'}, body: JSON.stringify({source: 'criterion-work', title: 'Verify criterion evidence'})})
  expect(pullResponse.status).toBe(200)
  const pull = await pullResponse.json(), links = base + '/pulls/' + pull.id + '/links'
  const connect = async (headers: {[key: string]: string}, token: string, key: string) => {
    const current = await (await fetch(upstream + '/api/connections/barkpark', {headers})).json()
    const response = await fetch(upstream + '/api/connections/barkpark', {method: 'POST', headers: {...headers, 'idempotency-key': key},
      body: JSON.stringify({token, workspace: 'fixture-workspace', project: 'default', dataset: 'production', expected_generation: current.generation})})
    expect(response.status).toBe(200)
    return await response.json()
  }
  const connection = await connect(owner, 'synthetic-fixture-credential', name + '-connect')
  const linked = await fetch(links, {method: 'POST', headers: {...owner, 'idempotency-key': name + '-link'},
    body: JSON.stringify({type: 'task', document_id: name + '-task', connection_generation: connection.generation})})
  expect(linked.status).toBe(200)
  const link = await linked.json(), endpoint = links + '/' + link.id + '/evidence'
  const query = '?connection_generation=' + connection.generation
  const initial = await (await fetch(endpoint + query, {headers: owner})).json()
  expect(initial.criteria.map((item: {state: string}) => item.state)).toEqual(['absent', 'absent'])
  await page.goto('/')
  await page.getByLabel('Username', {exact: true}).fill('owner')
  await page.getByLabel('Password', {exact: true}).fill('synthetic-password')
  await page.getByRole('button', {name: 'Sign in', exact: true}).click()
  await expect(page.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
  await page.goto('/repos/team/' + name + '/pulls/' + pull.id)
  await page.getByRole('button', {name: 'Open source context', exact: true}).click()
  const panel = page.getByRole('region', {name: 'Criterion evidence', exact: true})
  await expect(panel.getByText('Absent · no evidence').first()).toBeVisible()
  await panel.getByText('Attach evidence or reassess a result', {exact: true}).click()
  await panel.getByRole('combobox', {name: 'Producer outcome', exact: true}).selectOption('passed')
  await panel.getByLabel('Producer label', {exact: true}).fill('synthetic-browser-verifier')
  await panel.getByLabel('Reproduction commands · one per line', {exact: true}).fill('synthetic verifier --restore')
  await panel.getByRole('textbox', {name: 'Environment as a JSON object', exact: true}).fill('{"runtime":"copied native release","fixture":"synthetic HTTPS source"}')
  const artifact = Buffer.from('Reproducible browser evidence fixture\n')
  await panel.getByLabel('UTF-8 artifact · up to 64 KiB', {exact: true}).setInputFiles({name: 'browser-proof.txt', mimeType: 'text/plain', buffer: artifact})
  const requests: {key: string; body: any}[] = []
  const applications: {path: string; body: any}[] = []
  let loseReply = true, malformedReceipt = true
  await page.route('**/links/' + link.id + '/evidence/intents', async route => {
    if (route.request().method() === 'POST') {
      const preparation = route.request().postDataJSON()
      requests.push({key: route.request().headers()['idempotency-key'], body: JSON.parse(preparation.body)})
    }
    await route.continue()
  })
  await page.route('**/links/' + link.id + '/evidence/intents/*/retry', async route => {
    if (route.request().method() === 'POST') {
      applications.push({path: new URL(route.request().url()).pathname, body: route.request().postDataJSON()})
      if (loseReply) {loseReply = false; expect((await route.fetch()).status()).toBe(200); await route.abort(); return}
      if (malformedReceipt) {
        malformedReceipt = false
        const confirmed = await route.fetch()
        expect(confirmed.status()).toBe(200)
        await route.fulfill({response: confirmed, body: JSON.stringify({...(await confirmed.json()), id: 'invalid-receipt'})})
        return
      }
    }
    await route.continue()
  })
  await panel.getByRole('button', {name: 'Attach immutable result', exact: true}).click()
  await expect(panel.getByRole('status')).toContainText('could not be confirmed')
  const originalObservation = requests[0].body.manifest.observed_at
  await page.reload()
  await page.getByRole('button', {name: 'Open source context', exact: true}).click()
  await expect(panel.getByRole('button', {name: 'Retry original evidence request', exact: true})).toBeVisible()
  expect((await fetch(control + '/control/evidence-change', {method: 'POST',
    headers: {'content-type': 'application/json', authorization: 'Bearer synthetic-fixture-control'},
    body: JSON.stringify({revision: true, criterion: false})})).status).toBe(200)
  await page.waitForResponse(response => response.request().method() === 'GET' && new URL(response.url()).pathname === new URL(endpoint).pathname)
  await expect(panel.getByRole('list').first()).toContainText('Stale · reassessment needed', {timeout: 15000})
  await panel.getByText('Attach evidence or reassess a result', {exact: true}).click()
  const originalRetry = panel.getByRole('button', {name: 'Retry original evidence request', exact: true})
  if (await originalRetry.count()) await originalRetry.click()
  else await panel.getByRole('button', {name: 'Attach immutable result', exact: true}).click()
  await expect(panel.getByRole('status')).toContainText('could not be confirmed')
  await expect(panel.getByRole('button', {name: 'Attach immutable result', exact: true})).toBeDisabled()
  await page.goto('/')
  await page.goto('/repos/team/' + name + '/pulls/' + pull.id)
  await page.getByRole('button', {name: 'Open source context', exact: true}).click()
  await originalRetry.click()
  await expect(panel.getByRole('status')).toContainText('Request recorded')
  expect(requests).toHaveLength(1)
  expect(applications).toHaveLength(3)
  expect(applications[0].body).toEqual({})
  expect(applications[1]).toEqual(applications[0])
  expect(applications[2]).toEqual(applications[0])
  let view = await (await fetch(endpoint + query, {headers: owner})).json()
  expect(view.records).toHaveLength(1)
  expect(view.criteria[0].state).toBe('stale')
  const first = view.records[0]
  expect(first.manifest.observed_at).toBe(originalObservation)
  expect(first.source_revision).toBe(requests[0].body.source_revision)
  await panel.getByText('Evidence history (1)', {exact: true}).click()
  const [download, downloadResponse] = await Promise.all([
    page.waitForEvent('download', {timeout: 15000}),
    page.waitForResponse(response => response.request().method() === 'GET' && new URL(response.url()).pathname === new URL(endpoint + '/' + first.id + '/download').pathname),
    panel.getByRole('button', {name: 'Download protected artifact', exact: true}).click(),
  ])
  expect(downloadResponse.status()).toBe(200)
  expect(downloadResponse.headers()['x-gitgood-sha256']).toBe(hash(artifact))
  expect(downloadResponse.headers()['content-type']).toBe('application/octet-stream')
  const file = await download.path()
  expect(download.suggestedFilename()).toBe('browser-proof.txt')
  expect(hash(await readFile(file!))).toBe(hash(artifact))
  const post = async (outcome: string, key: string) => {
    const current = await (await fetch(endpoint + query, {headers: owner})).json()
    const response = await fetch(endpoint, {method: 'POST', headers: {...owner, 'idempotency-key': key},
      body: JSON.stringify({...requests[0].body, source_revision: current.source.revision, outcome})})
    expect(response.status).toBe(200)
    return await response.json()
  }
  await post('failed', name + '-failed')
  await expect(panel.getByRole('list').first()).toContainText('Failed', {timeout: 15000})
  await post('inconclusive', name + '-inconclusive')
  await expect(panel.getByRole('list').first()).toContainText('Inconclusive', {timeout: 15000})
  expect((await fetch(control + '/control/evidence-change', {method: 'POST', headers: {'content-type': 'application/json', authorization: 'Bearer synthetic-fixture-control'}, body: JSON.stringify({revision: true, criterion: false})})).status).toBe(200)
  await expect(panel.getByRole('list').first()).toContainText('Stale · reassessment needed', {timeout: 15000})
  view = await (await fetch(endpoint + query, {headers: owner})).json()
  const reassessedBody = {...requests[0].body, source_revision: view.source.revision}
  const reassessment = await fetch(endpoint, {method: 'POST', headers: {...owner, 'idempotency-key': name + '-reassessed'}, body: JSON.stringify(reassessedBody)})
  expect(reassessment.status).toBe(200)
  const reassessed = await reassessment.json()
  expect((await fetch(endpoint + '/' + reassessed.id + '/unavailable', {method: 'POST', headers: {...owner, 'idempotency-key': name + '-unavailable'}, body: JSON.stringify({reason: 'Synthetic artifact withdrawal'})})).status).toBe(200)
  await expect(panel.getByRole('list').first()).toContainText('Unavailable · artifact withdrawn', {timeout: 15000})
  expect((await fetch(endpoint + '/' + reassessed.id + '/download' + query, {headers: owner})).status).toBe(409)
  const prepared = await fetch(endpoint + '/intents', {method: 'POST',
    headers: {...owner, 'idempotency-key': name + '-concurrent-intent'},
    body: JSON.stringify({kind: 'attach', body: JSON.stringify({...reassessedBody, outcome: 'failed'})})})
  expect(prepared.status).toBe(200)
  const concurrentIntent = await prepared.json()
  const retrySaved = () => fetch(endpoint + '/intents/' + concurrentIntent.id + '/retry', {
    method: 'POST', headers: owner, body: '{}'})
  const concurrentReplies = await Promise.all([retrySaved(), retrySaved()])
  expect(concurrentReplies.map(response => response.status)).toEqual([200, 200])
  const concurrentReceipts = await Promise.all(concurrentReplies.map(response => response.json()))
  expect(concurrentReceipts[0]).toEqual(concurrentReceipts[1])
  expect(concurrentReceipts[0].intent_id).toBe(concurrentIntent.id)
  const retiredApplied = await fetch(endpoint + '/intents/' + concurrentIntent.id + '/retire', {
    method: 'POST', headers: owner, body: '{}'})
  expect(retiredApplied.status).toBe(200)
  expect(await retiredApplied.json()).toEqual(concurrentReceipts[0])
  const afterConcurrent = await (await fetch(endpoint + query, {headers: owner})).json()
  expect(afterConcurrent.records).toHaveLength(5)
  expect(afterConcurrent.records.filter((record: {id: string}) => record.id === concurrentReceipts[0].id)).toHaveLength(1)
  expect((await fetch(endpoint + '/' + concurrentReceipts[0].id + '/unavailable', {
    method: 'POST', headers: {...owner, 'idempotency-key': name + '-concurrent-unavailable'},
    body: JSON.stringify({reason: 'Concurrent fixture artifact withdrawn'})})).status).toBe(200)
  expect((await fetch(endpoint + '/intents/' + concurrentIntent.id + '/acknowledge', {
    method: 'POST', headers: owner, body: '{}'})).status).toBe(200)
  await expect(panel.getByRole('list').first()).toContainText('Unavailable · artifact withdrawn', {timeout: 15000})
  const readerConnection = await connect(reader, 'synthetic-outsider-credential', name + '-reader-denied')
  const denied = await (await fetch(endpoint + '?connection_generation=' + readerConnection.generation, {headers: reader})).json()
  expect(denied.source.source_state).toBe('denied')
  expect(denied.records).toEqual([])
  expect((await fetch(endpoint + '/' + first.id + '/download?connection_generation=' + readerConnection.generation, {headers: reader})).status).toBe(503)
  expect((await fetch(endpoint + query, {headers: outsider})).status).toBe(404)
  await page.setViewportSize({width: 390, height: 844})
  await page.screenshot({path: info.outputPath('criterion-evidence-mobile.png'), fullPage: true})
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  const receipt = {repository: name, repository_id: repositoryId, pull_id: pull.id, link, first_evidence: first,
    original_request: requests[0], opaque_retry_requests: applications, concurrent_intent: concurrentIntent,
    concurrent_receipt: concurrentReceipts[0], reassessed: reassessed.id, owner_connection_generation: connection.generation,
    artifact_sha256: hash(artifact), checks: ['real native imported Git commits', 'upstream met does not create evidence',
      'lost reply survives reload; malformed receipt survives navigation and component unmount; opaque retries retain exact encrypted original bytes and revision binding', 'checksum-verified private download',
      'new failed and inconclusive records override older pass', 'source revision makes result stale',
      'explicit reassessment retains history', 'unavailable artifact blocks current result and download',
      'two real HTTP retries create one result; retirement confirms its original receipt without erasing history',
      'viewer source denial hides provenance and bytes', 'native outsider denied', 'mobile width'],
    limitations: ['Synthetic source wire; live task and full J11 acceptance need separate proof.']}
  await writeFile(info.outputPath('criterion-evidence-receipt.json'), JSON.stringify(receipt, null, 2) + '\n')
  await writeFile(resolve(process.env.GITGOOD_TEST_PRODUCTION === 'true' ? 'test-results-production' : 'test-results', 'criterion-evidence-receipt.json'), JSON.stringify(receipt, null, 2) + '\n')
})
