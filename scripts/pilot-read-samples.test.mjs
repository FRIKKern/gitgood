import test from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'node:https'
import {createHash} from 'node:crypto'
import {mkdtemp, readFile, rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join, resolve, sep} from 'node:path'
import {execFileSync} from 'node:child_process'
import {observePilotReads, summarizeSamples} from './pilot-read-samples.mjs'

const sha256 = value => createHash('sha256').update(value).digest('hex')
const sample = (duration_ms, valid = true, status = 200) => ({duration_ms, valid, status})

test('nearest-rank summaries retain failures and the predeclared target', () => {
  const inputs = Array.from({length: 100}, (_, index) => sample(index + 1))
  assert.deepEqual(summarizeSamples(inputs), {count: 100, failures: 0, minimum_ms: 1, median_ms: 50,
    p95_ms: 95, maximum_ms: 100, target_ms: 1500, passed: true})
  assert.equal(summarizeSamples([...inputs, sample(1, false, 503)]).passed, false)
  assert.equal(summarizeSamples([sample(1500)]).passed, true)
  assert.equal(summarizeSamples([sample(1500.001)]).passed, false)
  for (const malformed of [[], [sample(NaN)], [sample(-1)], [sample(1, 'yes')], [sample(1, true, 503)], [sample(1, false, -1)]]) {
    assert.throws(() => summarizeSamples(malformed))
  }
})

test('actual TLS harness retains wrong content, HTTP failures and outsider access during load', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'gitgood-pilot-sampler-'))
  let server
  try {
    const keyPath = join(directory, 'key.pem'), certPath = join(directory, 'certificate.pem')
    execFileSync(process.env.GITGOOD_OPENSSL ?? 'openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
      '-keyout', keyPath, '-out', certPath, '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'], {stdio: 'ignore'})
    const content = 'x'.repeat(4096), text = 'synthetic bounded diff\n'
    const fixture = {profile: 'gitgood-pilot-v1', main_sha: 'a'.repeat(40), work_sha: 'b'.repeat(40),
      sample_file: {path: 'directory-00/file-0000.txt', bytes: 4096, sha256: sha256(content)},
      diff_bytes: Buffer.byteLength(text), diff_sha256: sha256(text)}
    const counts = new Map()
    let duplicateActors = false
    server = createServer({key: await readFile(keyPath), cert: await readFile(certPath)}, (request, response) => {
      const actor = request.headers['x-synthetic-actor']
      const url = new URL(request.url, 'https://localhost')
      let status = 200, body
      if (url.pathname === '/api/session') {
        body = {user: {id: duplicateActors ? 1 : Number(actor)}, teams: [{team: 'team', role: 'reader'}]}
      } else {
        const route = url.pathname.endsWith('/branches') ? 'branches' : url.pathname.endsWith('/diff') ? 'diff' :
          url.searchParams.get('path')?.endsWith('.txt') ? 'file' : 'directory'
        if (actor === 'outsider') {
          status = route === 'file' ? 200 : 404
          body = route === 'file' ? {exposed: true} : {error: 'repository_not_found'}
        } else {
          const count = (counts.get(route) ?? 0) + 1; counts.set(route, count)
          if (route === 'branches') body = {branches: [{name: 'main', sha: fixture.main_sha}, {name: 'pilot-work', sha: fixture.work_sha}]}
          if (route === 'directory') body = {kind: 'tree', sha: fixture.main_sha, history: Array(50).fill({}),
            entries: Array.from({length: 100}, (_, index) => ({name: 'file-'+String(index).padStart(4, '0')+'.txt', kind: 'blob', sha: 'c'.repeat(40)}))}
          if (route === 'file') body = {kind: 'text', sha: fixture.main_sha, size: 4096, content: count === 11 ? 'wrong' : content}
          if (route === 'diff') body = {sha: fixture.work_sha, base: fixture.main_sha, text}
          if (route === 'branches' && count === 11) {status = 503; body = {error: 'synthetic_unavailable'}}
        }
      }
      response.writeHead(status, {'content-type': 'application/json'}).end(JSON.stringify(body))
    })
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
    const options = {origin: 'https://localhost:'+server.address().port, certificate: await readFile(certPath),
      readers: Array.from({length: 8}, (_, index) => ({'x-synthetic-actor': String(index + 1)})),
      outsider: {'x-synthetic-actor': 'outsider'}, repository: 'pilot', fixture}
    const receipt = await observePilotReads(options)
    assert.equal(receipt.passed, false)
    assert.equal(receipt.routes.length, 4)
    for (const route of receipt.routes) {
      assert.equal(route.samples.length, 100); assert.equal(route.warmups.length, 10)
      assert.equal(new Set(route.samples.map(item => item.actor_id)).size, 8)
      assert.equal(route.summary.count, 100)
    }
    assert.equal(receipt.routes[0].summary.failures, 1)
    assert.equal(receipt.routes[0].samples.filter(item => item.status === 503).length, 1)
    assert.equal(receipt.routes[1].summary.failures, 0)
    assert.equal(receipt.routes[2].summary.failures, 1)
    assert.equal(receipt.routes[2].outsider_denied_during_load, false)
    assert.equal(receipt.routes[3].summary.failures, 0)
    const serialized = JSON.stringify(receipt)
    assert(!serialized.includes('x-synthetic-actor') && !serialized.includes(content) && !serialized.includes('synthetic_unavailable'))
    duplicateActors = true
    await assert.rejects(observePilotReads(options), /different native actors/)
    assert.equal(counts.get('branches'), 110, 'Duplicate actors refuse before workload requests')
  } finally {
    if (server) await new Promise(resolve => server.close(resolve))
    assert(resolve(directory).startsWith(resolve(tmpdir())+sep) && directory.includes('gitgood-pilot-sampler-'))
    await rm(directory, {recursive: true, force: true})
  }
})
