import {request as httpsRequest} from 'node:https'
import {createHash} from 'node:crypto'
import assert from 'node:assert/strict'

const hash = value => createHash('sha256').update(value).digest('hex')
export function summarizeSamples(samples) {
  const targetMs = 1500
  assert(Array.isArray(samples) && samples.length > 0 && samples.every(sample =>
    Number.isFinite(sample.duration_ms) && sample.duration_ms >= 0 && typeof sample.valid === 'boolean' &&
    Number.isSafeInteger(sample.status) && sample.status >= 0 && sample.status <= 599 &&
    (!sample.valid || sample.status === 200)))
  const sorted = samples.map(sample => sample.duration_ms).sort((left, right) => left - right)
  const percentile = fraction => sorted[Math.ceil(fraction * sorted.length) - 1]
  const failures = samples.filter(sample => !sample.valid).length
  const p95 = percentile(0.95)
  return {count: samples.length, failures, minimum_ms: sorted[0], median_ms: percentile(0.5),
    p95_ms: p95, maximum_ms: sorted.at(-1), target_ms: targetMs, passed: failures === 0 && p95 <= targetMs}
}

// Headers and response payloads stay in this process; the receipt retains timings and checked identities.
export async function observePilotReads({origin, certificate, readers, outsider, repository, fixture}) {
  const endpoint = new URL(origin)
  assert(endpoint.protocol === 'https:' && !endpoint.username && !endpoint.password && endpoint.pathname === '/' && !endpoint.search && !endpoint.hash)
  assert(readers.length === 8 && certificate && /^[a-z0-9-]+$/.test(repository))
  assert(/^[0-9a-f]{40}$/.test(fixture.main_sha) && /^[0-9a-f]{40}$/.test(fixture.work_sha))
  assert(fixture.profile === 'gitgood-pilot-v1' && fixture.sample_file?.path === 'directory-00/file-0000.txt')
  assert.equal(fixture.sample_file.bytes, 4096)
  assert(/^[0-9a-f]{64}$/.test(fixture.sample_file.sha256) && /^[0-9a-f]{64}$/.test(fixture.diff_sha256))
  assert(Number.isSafeInteger(fixture.diff_bytes) && fixture.diff_bytes > 0 && fixture.diff_bytes <= 262_144)
  function get(path, headers) {
    return new Promise((done, reject) => {
      const request = httpsRequest({hostname: '127.0.0.1', servername: endpoint.hostname, port: endpoint.port,
        path, method: 'GET', agent: false, ca: certificate, rejectUnauthorized: true,
        headers: {...headers, host: endpoint.host}}, response => {
        let size = 0; const chunks = []
        response.on('data', chunk => {
          size += chunk.length
          if (size > 2_097_152) request.destroy(new Error('response_bound'))
          else chunks.push(chunk)
        })
        response.once('error', reject)
        response.once('end', () => {
          try {done({status: response.statusCode, body: JSON.parse(Buffer.concat(chunks).toString('utf8'))})}
          catch {reject(new Error('response_json'))}
        })
      })
      request.once('error', reject)
      const deadline = setTimeout(() => request.destroy(new Error('request_deadline')), 10_000)
      request.once('close', () => clearTimeout(deadline))
      request.end()
    })
  }
  const identities = []
  for (const headers of readers) {
    const session = await get('/api/session', headers)
    assert.equal(session.status, 200)
    assert(Number.isSafeInteger(session.body.user?.id))
    assert(session.body.teams.some(team => team.team === 'team' && team.role === 'reader'))
    identities.push(session.body.user.id)
  }
  assert.equal(new Set(identities).size, 8, 'Concurrent readers must be different native actors')
  const base = '/api/repos/team/' + repository
  const routes = [
    {name: 'branches', path: base + '/branches', correct: body => {
      assert.deepEqual(body.branches.map(branch => [branch.name, branch.sha]).sort(),
        [['main', fixture.main_sha], ['pilot-work', fixture.work_sha]])
    }},
    {name: 'directory', path: base + '/snapshot?sha=' + fixture.main_sha + '&path=directory-00', correct: body => {
      assert.equal(body.kind, 'tree'); assert.equal(body.sha, fixture.main_sha)
      assert.deepEqual(body.entries.map(entry => entry.name).sort(), Array.from({length: 100}, (_, index) => 'file-' + String(index).padStart(4, '0') + '.txt'))
      assert(body.entries.every(entry => entry.kind === 'blob' && /^[0-9a-f]{40}$/.test(entry.sha)))
      assert.equal(body.history.length, 50)
    }},
    {name: 'file', path: base + '/snapshot?sha=' + fixture.main_sha + '&path=' + encodeURIComponent(fixture.sample_file.path), correct: body => {
      assert.equal(body.kind, 'text'); assert.equal(body.sha, fixture.main_sha)
      assert.equal(body.size, fixture.sample_file.bytes); assert.equal(hash(body.content), fixture.sample_file.sha256)
    }},
    {name: 'diff', path: base + '/diff?sha=' + fixture.work_sha + '&base=' + fixture.main_sha, correct: body => {
      assert.equal(body.sha, fixture.work_sha); assert.equal(body.base, fixture.main_sha)
      assert.equal(Buffer.byteLength(body.text), fixture.diff_bytes); assert.equal(hash(body.text), fixture.diff_sha256)
    }},
  ]
  const results = []
  for (const route of routes) {
    async function sample(index, actor = index % readers.length) {
      const started = performance.now()
      let status = 0, valid = false, failure = null
      try {
        const response = await get(route.path, readers[actor]); status = response.status
        if (status === 200) {route.correct(response.body); valid = true}
        else failure = 'http_' + status
      } catch {failure = status === 200 ? 'content_mismatch' : 'transport_or_response_failure'}
      return {index, actor_id: identities[actor], duration_ms: performance.now() - started, status, valid, failure}
    }
    const warmups = []
    for (let index = 0; index < 10; index++) warmups.push(await sample(index))
    const samples = new Array(100); let next = 0
    const denied = get(route.path, outsider).catch(() => ({status: 0, body: {error: 'transport_or_response_failure'}}))
    await Promise.all(Array.from({length: 8}, async (_, actor) => {
      while (next < samples.length) {const index = next++; samples[index] = await sample(index, actor)}
    }))
    const outsiderResponse = await denied
    const outsiderDenied = outsiderResponse.status === 404 && outsiderResponse.body.error === 'repository_not_found'
    const summary = summarizeSamples(samples)
    results.push({route: route.name, warmups, samples, summary, outsider_denied_during_load: outsiderDenied,
      passed: summary.passed && warmups.every(sample => sample.valid) && outsiderDenied})
  }
  return {profile: fixture.profile, phase: 'warm native routes through actual TLS', reader_actor_ids: identities,
    concurrency: 8, filesystem_cache: 'uncontrolled; recorded warmup, no host cache eviction',
    network: 'local TLS; 50 ms RTT browser profile remains unmeasured', routes: results,
    passed: results.every(result => result.passed),
    limitations: ['Only warm API read routes; cold/browser/write freshness/import/clone/resource targets remain separate.',
      'No capacity or complete M4 acceptance follows from this partial profile.']}
}
