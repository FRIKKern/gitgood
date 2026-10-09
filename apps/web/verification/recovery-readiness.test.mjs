import test from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'node:http'
import {mkdtemp, mkdir, copyFile, writeFile, rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

test('web readiness preserves recovery mode and refuses unknown upstream modes', async () => {
  const root = await mkdtemp(join(tmpdir(), 'gitgood-web-readiness-'))
  const candidate = 'a'.repeat(40)
  let mode = 'active'
  let requests = 0
  const upstream = createServer((request, response) => {
    assert.equal(request.url, '/health/ready')
    requests++
    response.writeHead(200, {'content-type': 'application/json'})
    response.end(JSON.stringify({candidate, status: 'ready', operational_mode: mode}))
  })
  const previous = Object.fromEntries(['GITGOOD_API_URL', 'NODE_ENV', 'GITGOOD_PROXY_KEY'].map(key => [key, process.env[key]]))
  try {
    await new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve))
    await mkdir(join(root, 'dist/server'), {recursive: true})
    await writeFile(join(root, 'package.json'), JSON.stringify({type: 'module'}))
    // Only the unrelated application handler is inert. Exercise the actual
    // production server and a real loopback upstream for health propagation.
    await writeFile(join(root, 'dist/server/server.js'), 'export default {fetch(){throw new Error("Unexpected application route")}}\n')
    await writeFile(join(root, 'dist/build-identity.json'), JSON.stringify({candidate, dirty: false}))
    for (const name of ['server.mjs', 'client-address.mjs']) await copyFile(new URL('../' + name, import.meta.url), join(root, name))
    process.env.GITGOOD_API_URL = 'http://127.0.0.1:' + upstream.address().port
    process.env.NODE_ENV = 'test'
    delete process.env.GITGOOD_PROXY_KEY
    const {default: web} = await import(pathToFileURL(join(root, 'server.mjs')).href)
    for (const [value, status, expected] of [['active', 200, 'active'], ['recovery_verification', 200, 'recovery_verification'], ['foreign', 503, 'unknown']]) {
      mode = value
      const response = await web.fetch(new Request('http://127.0.0.1/health/ready'))
      const body = await response.json()
      assert.equal(response.status, status)
      assert.equal(body.operational_mode, expected)
      assert.equal(body.candidate, candidate)
      assert.equal(body.forge_candidate, candidate)
      assert.equal(response.headers.get('cache-control'), 'no-store')
    }
    assert.equal(requests, 3)
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    upstream.closeAllConnections()
    await new Promise(resolve => upstream.close(resolve))
    await rm(root, {recursive: true})
  }
})
