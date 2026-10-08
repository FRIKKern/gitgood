import {test, expect} from '@playwright/test'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {mkdtemp, writeFile, readFile, rm, mkdir} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {dirname, join, resolve, sep} from 'node:path'
import {createServer as httpsServer} from 'node:https'
import {request as httpRequest} from 'node:http'
import type {AddressInfo} from 'node:net'
const execute = promisify(execFile)
const upstream = 'http://127.0.0.1:47841'
const git = process.env.GITGOOD_GIT ?? 'git'
async function session(username: string) {
  const result = await fetch(upstream + '/api/session', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({username, password: 'synthetic-password'})})
  expect(result.status).toBe(200)
  const token = /gitgood_session=([^;]+)/.exec(result.headers.getSetCookie()[0])![1]
  return {authorization: 'Bearer ' + token, 'content-type': 'application/json'}
}
test('real Git over trusted HTTPS clones pushes fetches, protects main and denies read-only/outsider credentials', async ({page}, testInfo) => {
  test.setTimeout(90_000)
  const prefix = join(tmpdir(), 'gitgood-client-')
  const root = await mkdtemp(prefix)
  let complete = false
  const certificate = join(root, 'certificate.pem')
  const key = join(root, 'key.pem')
  const openssl = process.env.GITGOOD_OPENSSL ?? 'openssl'
  await execute(openssl, ['req','-x509','-newkey','rsa:2048','-sha256','-nodes','-keyout',key,'-out',certificate,
    '-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'])
  let interruptNextReceive = false
  const proxy = httpsServer({key: await readFile(key), cert: await readFile(certificate)}, (request, response) => {
    const forward = httpRequest(new URL(request.url!, upstream), {method: request.method, headers: request.headers, agent: false}, result => {
      response.writeHead(result.statusCode!, result.headers); result.pipe(response)
    })
    forward.on('error', () => {response.writeHead(502); response.end()})
    if (interruptNextReceive && request.method === 'POST' && request.url?.endsWith('/git-receive-pack')) {
      interruptNextReceive = false
      request.once('data', (chunk: Buffer) => {
        forward.write(chunk.subarray(0, Math.min(chunk.length, 128)))
        forward.destroy()
        request.destroy()
        response.destroy()
      })
    } else request.pipe(forward)
  })
  await new Promise<void>(resolve => proxy.listen(0, '127.0.0.1', resolve))
  try {
    const name = 'git-' + Date.now()
    const owner = await session('owner')
    const created = await fetch(upstream + '/api/repos', {method: 'POST', headers: {...owner, 'idempotency-key': name}, body: JSON.stringify({team: 'team', name})})
    expect(created.status).toBe(201)
    const repo = await created.json()
    const credential = await fetch(upstream + '/api/repos/team/' + name + '/credentials', {method: 'POST', headers: owner})
    expect(credential.status).toBe(200)
    const token = (await credential.json()).token
    const url = 'https://localhost:' + (proxy.address() as AddressInfo).port + '/git/team/' + name + '.git'
    const clientEnv = (username: string, token: string) => { const env = {...process.env,
      GIT_TERMINAL_PROMPT: '0', GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: process.platform === 'win32' ? 'NUL' : '/dev/null',
      GIT_CONFIG_COUNT: '2', GIT_CONFIG_KEY_0: 'credential.helper', GIT_CONFIG_VALUE_0: '',
      GIT_CONFIG_KEY_1: 'http.extraHeader', GIT_CONFIG_VALUE_1: 'Authorization: Basic ' + Buffer.from(username + ':' + token).toString('base64'),
      GIT_SSL_CAINFO: certificate}; delete env.GIT_SSL_NO_VERIFY; return env }
    const client = join(root, 'checkout')
    const command = (args: string[], env = clientEnv('owner', token)) => execute(git, args, {cwd: client, env, timeout: 20_000, maxBuffer: 1_048_576})
    await mkdir(client)
    const clone = await command(['clone', url, '.'])
    expect(clone.stderr).toContain('empty repository')
    await writeFile(join(client, 'README.md'), '# Private project\n<script>window.untrusted=true</script>\n')
    await writeFile(join(client, 'space & $(demo).txt'), 'literal filename\n')
    await writeFile(join(client, 'binary.dat'), Buffer.from([0,1,2,255]))
    await command(['add','--','.'])
    await command(['-c','user.name=Synthetic owner','-c','user.email=fixture@example.invalid','commit','-m','Initial private commit'])
    const initial = (await command(['rev-parse','HEAD'])).stdout.trim()
    await command(['push','origin','HEAD:main'])
    expect((await command(['ls-remote','origin','refs/heads/main'])).stdout).toContain(initial)
    await command(['switch','-c','feature'])
    await writeFile(join(client,'README.md'), '# Changed private project\n')
    await command(['add','--','.'])
    await command(['-c','user.name=Synthetic owner','-c','user.email=fixture@example.invalid','commit','-m','Feature commit'])
    const feature = (await command(['rev-parse','HEAD'])).stdout.trim()
    await command(['push','origin','HEAD:feature'])
    await expect(command(['push','origin','HEAD:main'])).rejects.toThrow()
    expect((await command(['ls-remote','origin','refs/heads/main'])).stdout).toContain(initial)
    await page.goto('/')
    await page.getByLabel('Username').fill('owner')
    await page.getByLabel('Password').fill('synthetic-password')
    await page.getByRole('button', {name:'Sign in',exact:true}).click()
    await expect(page.getByRole('heading', {name:'Your repositories'})).toBeVisible()
    await page.goto('/repos/team/' + name + '?sha=' + initial + '&path=' + encodeURIComponent('space & $(demo).txt'))
    await expect(page.locator('.source')).toHaveText('literal filename\n')
    await page.goto('/repos/team/' + name + '?sha=' + initial + '&path=README.md')
    await expect(page.locator('.source')).toContainText('<script>window.untrusted=true</script>')
    expect(await page.evaluate(() => 'untrusted' in window)).toBe(false)
    await page.goto('/repos/team/' + name + '?sha=' + initial + '&path=binary.dat')
    await expect(page.getByText('Binary file. A text preview is unavailable.', {exact:false})).toBeVisible()
    await page.goto('/repos/team/' + name + '?sha=' + feature)
    await expect(page.getByRole('heading', {name:'Commit history'})).toBeVisible()
    await page.getByRole('link', {name:'Commit diff', exact:true}).click()
    await expect(page.locator('.source')).toContainText('+# Changed private project')
    await page.reload()
    await expect(page.locator('.source')).toContainText('+# Changed private project')
    await page.goto('/repos/team/' + name + '?sha=' + feature)
    const reader = await session('reader')
    const readerResult = await fetch(upstream + '/api/repos/team/' + name + '/credentials', {method:'POST',headers:reader})
    const readerCredential = await readerResult.json()
    expect((await command(['ls-remote','origin','refs/heads/feature'], clientEnv('reader',readerCredential.token))).stdout).toContain(feature)
    await expect(command(['push','origin','HEAD:reader-write'], clientEnv('reader',readerCredential.token))).rejects.toThrow()
    const outsider = await session('outsider')
    expect((await fetch(upstream + '/api/repos/team/' + name, {headers:outsider})).status).toBe(404)
    await expect(command(['ls-remote',url], clientEnv('outsider',token))).rejects.toThrow()
    await expect(command(['ls-remote',url], {...clientEnv('owner', token), GIT_SSL_CAINFO: ''})).rejects.toThrow()
    await command(['fetch','origin'])
    await writeFile(join(client, 'interrupted.dat'), Buffer.from(Array.from({length:262144}, () => Math.floor(Math.random()*256))))
    await command(['add','--','.'])
    await command(['-c','user.name=Synthetic owner','-c','user.email=fixture@example.invalid','commit','-m','Interrupted upload fixture'])
    const interrupted = (await command(['rev-parse','HEAD'])).stdout.trim()
    interruptNextReceive = true
    await expect(command(['push','origin','HEAD:interrupted'])).rejects.toThrow()
    expect((await command(['ls-remote','origin','refs/heads/interrupted'])).stdout.trim()).toBe('')
    expect((await command(['ls-remote','origin','refs/heads/feature'])).stdout).toContain(feature)
    await command(['push','origin','HEAD:interrupted'])
    expect((await command(['ls-remote','origin','refs/heads/interrupted'])).stdout).toContain(interrupted)
    await command(['push','origin','HEAD:feature'])
    await page.getByRole('button', {name:'Refresh branches'}).click()
    await expect(page.getByLabel('Branch', {exact:true})).toHaveValue('')
    expect(new URL(page.url()).searchParams.get('sha')).toBe(feature)
    await page.getByLabel('Branch', {exact:true}).selectOption('feature')
    await expect(page).toHaveURL(new RegExp(interrupted))
    await expect(page.getByRole('heading', {name:'Commit history'})).toBeVisible()
    await page.screenshot({path:testInfo.outputPath('repository-browser.png'),fullPage:true})
    const oversized = await fetch(upstream + '/git/team/' + name + '.git/git-receive-pack', {method:'POST', headers:{
      authorization:'Basic ' + Buffer.from('owner:' + token).toString('base64'), 'content-type':'application/x-git-receive-pack-request'}, body: Buffer.alloc(33_554_433)})
    expect(oversized.status).toBe(413)
    await oversized.json()
    await command(['fsck','--full','--strict'])
    const revoked = await fetch(upstream + '/api/credentials/' + readerCredential.id, {method:'DELETE',headers:reader})
    expect(revoked.status).toBe(200)
    await expect(command(['ls-remote',url], clientEnv('reader',readerCredential.token))).rejects.toThrow()
    await writeFile(testInfo.outputPath('git-receipt.json'), JSON.stringify({repository:repo.id, initial, feature,
      actors:['owner','reader','outsider'], transport:'HTTPS, explicit CA verification',
      checks:['empty clone','commit','push','fetch','protected main','reader denied write','outsider denied read','revoked credential denied','untrusted TLS denied','interrupted real push leaves refs unchanged','interrupted upload retry','32 MiB size limit','object fsck']},null,2))
    complete = true
  } finally {
    proxy.closeAllConnections()
    await new Promise<void>(resolve => proxy.close(() => resolve()))
    const checked = resolve(root)
    if (complete && checked.startsWith(resolve(prefix)) && checked.startsWith(resolve(tmpdir()) + sep)) await rm(checked, {recursive:true,force:true})
  }
})
