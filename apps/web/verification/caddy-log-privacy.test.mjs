import {test} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'node:http'
import {request} from 'node:https'
import {spawn, execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {mkdtemp, mkdir, writeFile, readFile, chmod} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join, dirname} from 'node:path'
import {randomBytes} from 'node:crypto'
import {reserveEdgePort} from '../../../scripts/verification-edge-port.mjs'

test('actual Caddy errors omit private headers while edge routing and diagnostics remain usable', {timeout: 20000}, async () => {
  assert(process.env.GITGOOD_CADDY, 'Pinned Caddy binary is required for this verification')
  const execute = promisify(execFile), root = await mkdtemp(join(tmpdir(), 'gitgood-edge-privacy-'))
  const version = (await execute(process.env.GITGOOD_CADDY, ['version'], {timeout: 5000, windowsHide: true})).stdout.trim()
  assert(version.startsWith('v2.11.7 '), 'Edge privacy proof requires the pinned Caddy 2.11.7 runtime')
  if (process.platform !== 'win32') await chmod(root, 0o700)
  const secret = randomBytes(32).toString('base64'), canary = randomBytes(24).toString('hex')
  const observed = []
  const upstream = createServer((incoming, response) => {
    observed.push({path: incoming.url, key: incoming.headers['x-gitgood-edge-key'], client: incoming.headers['x-gitgood-edge-client']})
    if (incoming.url === '/api/fixture-failure') {incoming.socket.destroy(); return}
    if (incoming.url === '/api/fixture-cancel') {
      response.writeHead(200, {'content-type': 'application/octet-stream', 'x-private-fixture': canary})
      response.write(Buffer.alloc(131072, 'x'))
      const interval = setInterval(() => response.write(Buffer.alloc(8192, 'x')), 25)
      response.once('close', () => clearInterval(interval))
      return
    }
    response.writeHead(200, {'content-type': 'application/json', 'x-private-fixture': canary})
    response.end(JSON.stringify({fixture: true}))
  })
  let edge, output = ''
  try {
    await new Promise((resolve, reject) => {upstream.once('error', reject); upstream.listen(0, '127.0.0.1', resolve)})
    const upstreamPort = upstream.address().port, port = await reserveEdgePort()
    const cert = join(root, 'certificate.pem'), key = join(root, 'private-key.pem')
    await execute(process.env.GITGOOD_OPENSSL ?? 'openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-sha256', '-nodes',
      '-keyout', key, '-out', cert, '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
    {timeout: 10000, windowsHide: true})
    const quote = path => '"' + path.replaceAll('\\', '/') + '"'
    let config = (await readFile(new URL('../../../docs/deployment/Caddyfile.example', import.meta.url), 'utf8')).replaceAll('\r\n', '\n')
    config = config.replaceAll('gitgood.example.invalid', 'https://localhost:' + port)
      .replaceAll('127.0.0.1:47841', '127.0.0.1:' + upstreamPort).replaceAll('127.0.0.1:47840', '127.0.0.1:' + upstreamPort)
      .replace('https://localhost:' + port + ' {', 'https://localhost:' + port + ' {\n  bind 127.0.0.1\n  tls ' + quote(cert) + ' ' + quote(key))
    config = config.includes('persist_config off') ? config.replace('persist_config off', 'persist_config off\n  admin off\n  auto_https off') :
      '{\n  admin off\n  auto_https off\n  persist_config off\n}\n' + config
    const configPath = join(root, 'Caddyfile'); await writeFile(configPath, config, {mode: 0o600})
    edge = spawn(process.env.GITGOOD_CADDY, ['run', '--config', configPath, '--adapter', 'caddyfile'], {
      windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], env: {...process.env, GITGOOD_PROXY_KEY: secret,
        XDG_DATA_HOME: join(root, 'data'), XDG_CONFIG_HOME: join(root, 'config'), APPDATA: join(root, 'appdata')}})
    edge.stdout.on('data', chunk => {output += chunk}); edge.stderr.on('data', chunk => {output += chunk})
    const ca = await readFile(cert)
    const get = (path, cancel = false) => new Promise((resolve, reject) => {
      const operation = request({hostname: '127.0.0.1', servername: 'localhost', port, path, ca, rejectUnauthorized: true,
        headers: {host: 'localhost:' + port, authorization: 'Bearer ' + canary, cookie: 'fixture=' + canary, 'x-fixture-private': canary,
          'x-gitgood-edge-key': 'caller-forgery', 'x-gitgood-edge-client': '203.0.113.1'}}, response => {
        if (cancel) response.once('data', () => {response.destroy(); resolve(response.statusCode)})
        else response.resume()
        response.on('end', () => resolve(response.statusCode))
      })
      operation.on('error', reject); operation.setTimeout(2000, () => operation.destroy(new Error('Owned edge request deadline'))); operation.end()
    })
    let ready = false
    for (let attempt = 0; attempt < 80; attempt++) {
      if (edge.exitCode !== null) throw new Error('Owned Caddy exited before verification; private diagnostic root: ' + root)
      try {ready = await get('/api/fixture-ready') === 200; if (ready) break} catch {}
      await new Promise(resolve => setTimeout(resolve, 50))
    }
    assert(ready, 'Owned TLS Caddy must become ready')
    const normal = observed.find(value => value.path === '/api/fixture-ready')
    assert(normal, 'Expected upstream route; observed paths: ' + JSON.stringify(observed.map(value => value.path)))
    assert(normal.key === secret && normal.client === '127.0.0.1', 'Edge overwrites caller assertions with its actual private identity')
    assert.equal(await get('/git/team/project.git/info/refs'), 200)
    const git = observed.find(value => value.path === '/git/team/project.git/info/refs')
    assert(git.key === undefined && git.client === undefined, 'Direct Git route strips edge assertions')
    assert.equal(await get('/internal/probe'), 404)
    assert(!observed.some(value => value.path === '/internal/probe'), 'Internal route never reaches an upstream')
    assert.equal(await get('/api/fixture-failure'), 502)
    let entry
    for (let attempt = 0; attempt < 40; attempt++) {
      const entries = output.split(/\r?\n/).filter(Boolean).flatMap(line => {try {return [JSON.parse(line)]} catch {return []}})
      entry = entries.find(value => value.logger === 'http.log.error' && value.request?.uri === '/api/fixture-failure')
      if (entry) break
      await new Promise(resolve => setTimeout(resolve, 25))
    }
    assert(entry && entry.status === 502, 'An actual upstream failure retains its route, status and diagnostic')
    assert.equal(await get('/api/fixture-cancel', true), 200)
    let cancellation
    for (let attempt = 0; attempt < 40; attempt++) {
      const entries = output.split(/\r?\n/).filter(Boolean).flatMap(line => {try {return [JSON.parse(line)]} catch {return []}})
      cancellation = entries.find(value => value.logger === 'http.handlers.reverse_proxy' && value.request?.uri === '/api/fixture-cancel')
      if (cancellation) break
      await new Promise(resolve => setTimeout(resolve, 25))
    }
    assert(cancellation, 'A real cancelled stream retains an upstream diagnostic')
    await writeFile(join(root, 'runtime.log'), output, {mode: 0o600})
    assert.equal(output.includes(secret), false, 'Runtime log must omit the private edge key')
    assert.equal(output.includes(canary), false, 'Runtime log must omit caller credentials and private headers')
    assert.equal(entry.request.headers, undefined, 'Runtime request header object is removed')
    const receipt = {platform: process.platform, edge: 'Caddy 2.11.7', status: 'passed', checks: [
      'actual TLS with explicit issuer verification', 'current edge identity overwrites caller forgery',
      'Git route strips edge assertions', 'internal routes never reach an upstream',
      'actual HTTP 502 retains route and diagnostic', 'actual cancelled stream retains diagnostic',
      'private edge key and caller headers absent from runtime log'],
      recorded_at: new Date().toISOString()}
    await writeFile(join(root, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n', {mode: 0o600})
    if (process.env.GITGOOD_EDGE_PRIVACY_RECEIPT) {
      await mkdir(dirname(process.env.GITGOOD_EDGE_PRIVACY_RECEIPT), {recursive: true})
      await writeFile(process.env.GITGOOD_EDGE_PRIVACY_RECEIPT, JSON.stringify(receipt, null, 2) + '\n', {mode: 0o600})
    }
    console.log('PASS actual edge privacy profile; private diagnostic root: ' + root)
  } finally {
    if (edge && edge.exitCode === null) {
      const ended = new Promise(resolve => edge.once('exit', resolve)); edge.kill(); await ended
    }
    await new Promise(resolve => upstream.close(resolve))
  }
})
