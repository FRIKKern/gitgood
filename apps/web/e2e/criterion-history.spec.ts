import {test, expect} from '@playwright/test'
import {fixtureSession as session} from './fixture-session'
import {appliedImport} from './fixture-operation'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {mkdtemp, mkdir, writeFile, readFile} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join, resolve} from 'node:path'
import {createHash} from 'node:crypto'
const execute = promisify(execFile)
const upstream = process.env.GITGOOD_TEST_API_URL ?? 'http://127.0.0.1:47841'
const hash = (value: Buffer | string) => createHash('sha256').update(value).digest('hex')

test('evidence history pages preserve latest status, old artifacts and all availability reasons', async ({page}, info) => {
  test.setTimeout(240000)
  const owner = await session('owner'), outsider = await session('outsider')
  const root = await mkdtemp(join(tmpdir(), 'gitgood-history-')), source = join(root, 'source')
  await mkdir(source)
  const env = {...process.env, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: process.platform === 'win32' ? 'NUL' : '/dev/null'}
  const command = (args: string[]) => execute(process.env.GITGOOD_GIT ?? 'git', args, {cwd: source, env, timeout: 20000})
  await command(['init', '--template=', '--object-format=sha1', '--initial-branch=main'])
  await writeFile(join(source, 'README.md'), 'History base\n')
  await command(['add', '--', '.'])
  const author = ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid']
  await command([...author, 'commit', '-m', 'History base'])
  await command(['switch', '-c', 'history-work'])
  await writeFile(join(source, 'README.md'), 'History implementation\n')
  await command(['add', '--', '.']); await command([...author, 'commit', '-m', 'History implementation'])
  const bundle = join(root, 'history.bundle'); await command(['bundle', 'create', bundle, '--branches'])
  const bytes = await readFile(bundle), name = 'criterion-history-' + Date.now()
  const create = await fetch(upstream + '/api/repos', {method: 'POST', headers: {...owner, 'idempotency-key': name}, body: JSON.stringify({team: 'team', name})})
  expect(create.status).toBe(201)
  const repository = await create.json(), base = upstream + '/api/repos/team/' + name
  const intake = await fetch(base + '/imports', {method: 'POST', headers: {...owner, 'idempotency-key': name + '-import'}, body: JSON.stringify({source_name: 'history.bundle', source_bytes: bytes.length, source_sha256: hash(bytes)})})
  expect(intake.status).toBe(202)
  const operation = (await intake.json()).operation
  expect((await fetch(base + '/imports/' + operation.id + '/source', {method: 'PUT', headers: {...owner, 'content-type': 'application/octet-stream'}, body: bytes})).status).toBe(202)
  await appliedImport(base, operation.id, owner)
  const pullResponse = await fetch(base + '/pulls', {method: 'POST', headers: {...owner, 'idempotency-key': name + '-pull'}, body: JSON.stringify({source: 'history-work', title: 'Bounded evidence history'})})
  expect(pullResponse.status).toBe(200)
  const pull = await pullResponse.json()
  const current = await (await fetch(upstream + '/api/connections/barkpark', {headers: owner})).json()
  const connect = await fetch(upstream + '/api/connections/barkpark', {method: 'POST', headers: {...owner, 'idempotency-key': name + '-connect'}, body: JSON.stringify({token: 'synthetic-fixture-credential', workspace: 'fixture-workspace', project: 'default', dataset: 'production', expected_generation: current.generation})})
  expect(connect.status).toBe(200)
  const connection = await connect.json(), links = base + '/pulls/' + pull.id + '/links'
  const attached = await fetch(links, {method: 'POST', headers: {...owner, 'idempotency-key': name + '-link'}, body: JSON.stringify({type: 'task', document_id: name + '-task', connection_generation: connection.generation})})
  expect(attached.status).toBe(200)
  const link = await attached.json(), endpoint = links + '/' + link.id + '/evidence'
  const query = '?connection_generation=' + connection.generation
  const original = await (await fetch(endpoint + query, {headers: owner})).json()
  const artifact = 'Preserved older evidence artifact\n'
  const params = {connection_generation: connection.generation, link_generation: link.generation,
    source_revision: original.source.revision, source_sha: original.source_sha, target_sha: original.target_sha,
    criterion_index: 0, criterion_sha256: original.criteria[0].sha256, outcome: 'passed',
    manifest: {commands: ['synthetic verifier --history'], environment: {fixture: 'copied production'}, producer: 'history-fixture', observed_at: new Date().toISOString()},
    artifact: {name: 'history-proof.txt', content: artifact, sha256: hash(artifact)}}
  const ids: string[] = []
  for (let index = 0; index < 21; index++) {
    const response = await fetch(endpoint, {method: 'POST', headers: {...owner, 'idempotency-key': name + '-result-' + index},
      body: JSON.stringify({...params, outcome: index === 20 ? 'failed' : 'passed'})})
    expect(response.status).toBe(200); ids.push((await response.json()).id)
  }
  for (let index = 0; index < 26; index++) {
    const response = await fetch(endpoint + '/' + ids[20] + '/unavailable', {method: 'POST', headers: {...owner, 'idempotency-key': name + '-event-' + index}, body: JSON.stringify({reason: 'Fixture unavailable ' + index})})
    expect(response.status).toBe(200)
  }
  await page.goto('/')
  await page.getByLabel('Username', {exact: true}).fill('owner')
  await page.getByLabel('Password', {exact: true}).fill('synthetic-password')
  await page.getByRole('button', {name: 'Sign in', exact: true}).click()
  await expect(page.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
  await page.goto('/repos/team/' + name + '/pulls/' + pull.id)
  await page.getByRole('button', {name: 'Open source context', exact: true}).click()
  const panel = page.getByRole('region', {name: 'Criterion evidence', exact: true})
  await expect(panel.getByText('Unavailable · artifact withdrawn', {exact: true}).first()).toBeVisible()
  await panel.getByText('Evidence history (21)', {exact: true}).click()
  const records = panel.getByRole('article', {name: 'Evidence record', exact: true})
  await expect(records).toHaveCount(20)
  const latest = records.first(), events = latest.getByRole('region', {name: 'Artifact availability history', exact: true})
  // A section with its accessible name is a region; every stored reason can be reached.
  await expect(events.getByText(/Fixture unavailable 24 ·/)).toBeVisible()
  await expect(events.getByText(/Fixture unavailable 25 ·/)).toHaveCount(0)
  await events.getByRole('button', {name: 'Later availability events', exact: true}).click()
  await expect(events.getByText(/Fixture unavailable 25 ·/)).toBeVisible()
  await expect(events.getByText(/Fixture unavailable 0 ·/)).toHaveCount(0)
  await events.getByRole('button', {name: 'Earlier availability events', exact: true}).click()
  await expect(events.getByText(/Fixture unavailable 0 ·/)).toBeVisible()
  await panel.getByRole('button', {name: 'Older evidence', exact: true}).click()
  await expect(records).toHaveCount(1)
  await expect(records.first().getByRole('heading', {name: 'Criterion 1 · Passed · producer result', exact: true})).toBeVisible()
  await expect(panel.getByText('Unavailable · artifact withdrawn', {exact: true}).first()).toBeVisible()
  const [download] = await Promise.all([page.waitForEvent('download', {timeout: 15000}), records.first().getByRole('button', {name: 'Download protected artifact', exact: true}).click()])
  const path = await download.path(); expect(path).toBeTruthy(); expect(hash(await readFile(path!))).toBe(hash(artifact))
  await panel.getByRole('button', {name: 'Newer evidence', exact: true}).click()
  await expect(records).toHaveCount(20)
  const view = await (await fetch(endpoint + query, {headers: owner})).json()
  expect(view.history.total).toBe(21); expect(view.criteria[0].evidence_id).toBe(ids[20])
  expect(view.records[0].events_total).toBe(26)
  expect((await fetch(endpoint + '/' + ids[20] + '/events' + query, {headers: outsider})).status).toBe(404)
  const receipt = {repository_id: repository.id, repository_name: name, pull_id: pull.id, link_id: link.id,
    oldest_evidence_id: ids[0], latest_evidence_id: ids[20], records_total: 21, events_total: 26, artifact_sha256: hash(artifact),
    checks: ['real native Git and viewer-owned source criterion', '21 immutable results created through ordinary native API',
      '20-record first page and one-record older page', 'latest unavailable result governs while older pass is visible',
      'all 26 withdrawal reasons retained across event pages', 'earlier/newer page navigation',
      'older protected artifact retains exact bytes', 'native outsider cannot read event history'], recorded_at: new Date().toISOString()}
  await writeFile(info.outputPath('criterion-history-receipt.json'), JSON.stringify(receipt, null, 2) + '\n')
  await writeFile(resolve('test-results-production/criterion-history-receipt.json'), JSON.stringify(receipt, null, 2) + '\n')
})
