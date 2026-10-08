import {test, expect} from '@playwright/test'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join,resolve} from 'node:path'
import {randomBytes} from 'node:crypto'
const run=promisify(execFile)
const upstream=process.env.GITGOOD_TEST_API_URL??'http://127.0.0.1:47841'
const git=process.env.GITGOOD_GIT??'git'
const windows=process.platform==='win32'
const ssh=process.env.GITGOOD_SSH??(windows?'C:/Windows/System32/OpenSSH/ssh.exe':'ssh')
const keygen=process.env.GITGOOD_SSH_KEYGEN??(windows?'C:/Windows/System32/OpenSSH/ssh-keygen.exe':'ssh-keygen')
const quote=(s:string)=>"'"+s.replaceAll("'","'\\''")+"'"
async function session(username:string) {
  const response=await fetch(upstream+'/api/session',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username,password:'synthetic-password'})})
  expect(response.status).toBe(200)
  return {authorization:'Bearer '+/gitgood_session=([^;]+)/.exec(response.headers.getSetCookie()[0])![1],'content-type':'application/json'}
}
test('native SSH browser key registration, real clone/push/fetch, permissions, revocation and interruption',async({page},info)=>{
  test.setTimeout(180000)
  const root=await mkdtemp(join(tmpdir(),'gitgood-ssh-client-'))
  const keys:Record<string,string>={}
  for(const actor of ['owner','reader','outsider']) {
    keys[actor]=join(root,actor)
    await run(keygen,['-q','-t','ed25519','-N','','-f',keys[actor]])
  }
  const owner=await session('owner'),label='Workstation '+Date.now()
  const ownerPublic=await readFile(keys.owner+'.pub','utf8')
  await page.goto('/')
  await page.getByLabel('Username').fill('owner')
  await page.getByLabel('Password').fill('synthetic-password')
  await page.getByRole('button',{name:'Sign in',exact:true}).click()
  await expect(page.getByRole('heading',{name:'SSH access'})).toBeVisible()
  await page.getByLabel('SSH key label').fill(label)
  await page.getByLabel('SSH public key').fill(ownerPublic)
  let loseReply=true
  await page.route('**/api/ssh-keys',async route=>{
    if(route.request().method()==='POST'&&loseReply){loseReply=false;const response=await route.fetch();expect(response.status()).toBe(201);await route.abort()}
    else await route.continue()
  })
  await page.getByRole('button',{name:'Add SSH key',exact:true}).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await page.getByRole('button',{name:'Add SSH key',exact:true}).click()
  await expect(page.getByRole('heading',{name:label,exact:true})).toBeVisible()
  const keyList=await (await fetch(upstream+'/api/ssh-keys',{headers:owner})).json()
  expect(keyList.keys.filter((k:{label:string})=>k.label===label)).toHaveLength(1)
  expect(keyList.transport.enabled).toBe(true)
  const ownerKey=keyList.keys.find((k:{label:string})=>k.label===label)
  const host=keyList.transport.host,port=keyList.transport.port
  const known=join(root,'known_hosts')
  await writeFile(known,'['+host+']:'+port+' '+keyList.transport.public_key+'\n')
  const name='ssh-'+Date.now()
  const created=await fetch(upstream+'/api/repos',{method:'POST',headers:{...owner,'idempotency-key':name},body:JSON.stringify({team:'team',name})})
  expect(created.status).toBe(201)
  const repo=await created.json()
  expect(repo.ssh_clone_url).toBe('ssh://owner@'+host+':'+port+'/team/'+name+'.git')
  const args=(actor:string,knownPath=known)=>['-F',windows?'NUL':'/dev/null','-i',keys[actor],'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+knownPath]
  const env=(actor:string,knownPath=known)=>({...process.env,GIT_TERMINAL_PROMPT:'0',GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:windows?'NUL':'/dev/null',GIT_SSH_VARIANT:'ssh',GIT_SSH_COMMAND:[ssh,...args(actor,knownPath)].map(quote).join(' ')})
  const client=join(root,'checkout');await mkdir(client)
  const command=(arguments_:string[],actor='owner',override:NodeJS.ProcessEnv={})=>run(git,arguments_,{cwd:client,env:{...env(actor),...override},timeout:25000,maxBuffer:1048576})
  await command(['clone',repo.ssh_clone_url,'.'])
  await writeFile(join(client,'README.md'),'# Native SSH fixture\n')
  await writeFile(join(client,'binary.dat'),Buffer.from([0,255,10,13,128]))
  const large=randomBytes(1048576)
  await writeFile(join(client,'large.dat'),large)
  await command(['add','.'])
  await command(['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','Native SSH initial'])
  const initial=(await command(['rev-parse','HEAD'])).stdout.trim()
  await command(['push','origin','HEAD:main'])
  expect((await command(['ls-remote','origin','refs/heads/main'])).stdout).toContain(initial)
  await command(['switch','-c','feature'])
  await writeFile(join(client,'README.md'),'# Feature over SSH\n')
  await command(['add','.'])
  await command(['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','SSH feature'])
  const feature=(await command(['rev-parse','HEAD'])).stdout.trim()
  await command(['push','origin','HEAD:feature'])
  await expect(command(['push','origin','HEAD:main'])).rejects.toThrow()
  expect((await command(['ls-remote','origin','refs/heads/main'])).stdout).toContain(initial)
  for(const actor of ['reader','outsider']) {
    const headers=await session(actor)
    const response=await fetch(upstream+'/api/ssh-keys',{method:'POST',headers:{...headers,'idempotency-key':'ssh-'+actor+'-'+Date.now()},body:JSON.stringify({label:actor,public_key:await readFile(keys[actor]+'.pub','utf8')})})
    expect(response.status).toBe(201)
  }
  const readerUrl=repo.ssh_clone_url.replace('ssh://owner@','ssh://reader@')
  expect((await command(['ls-remote',readerUrl],'reader')).stdout).toContain(feature)
  await expect(command(['push',readerUrl,'HEAD:reader-write'],'reader')).rejects.toThrow()
  await expect(command(['ls-remote',repo.ssh_clone_url.replace('ssh://owner@','ssh://outsider@')],'outsider')).rejects.toThrow()
  await expect(command(['ls-remote',readerUrl],'owner')).rejects.toThrow()
  const reader=await session('reader')
  expect((await fetch(upstream+'/api/ssh-keys',{method:'POST',headers:{...reader,'idempotency-key':'stolen-'+Date.now()},body:JSON.stringify({label:'Stolen',public_key:ownerPublic})})).status).toBe(409)
  const wrongKnown=join(root,'wrong_hosts')
  await writeFile(wrongKnown,'['+host+']:'+port+' '+await readFile(keys.reader+'.pub','utf8'))
  await expect(command(['ls-remote','origin'],'owner',env('owner',wrongKnown))).rejects.toThrow()
  for(const denied of [['id'],['-s','sftp'],['git-upload-pack /etc/passwd']]) {
    await expect(run(ssh,[...args('owner'),'-p',String(port),'owner@'+host,...denied],{env:process.env,timeout:10000})).rejects.toThrow()
  }
  await command(['fetch','origin'])
  const second=join(root,'second');await mkdir(second)
  await run(git,['clone',repo.ssh_clone_url,'.'],{cwd:second,env:env('owner'),timeout:25000})
  expect(await readFile(join(second,'binary.dat'))).toEqual(Buffer.from([0,255,10,13,128]))
  expect(await readFile(join(second,'large.dat'))).toEqual(large)
  await writeFile(join(client,'interrupted.dat'),Buffer.from(Array.from({length:262144},()=>Math.floor(Math.random()*256))))
  await command(['add','.'])
  await command(['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','Interrupted SSH upload'])
  const interrupted=(await command(['rev-parse','HEAD'])).stdout.trim()
  const wrapper=join(root,'interrupt.mjs')
  await writeFile(wrapper,`import {spawn} from 'node:child_process'; const child=spawn(process.env.GITGOOD_TEST_SSH,JSON.parse(process.env.GITGOOD_TEST_SSH_ARGS).concat(process.argv.slice(2)),{stdio:['pipe','inherit','inherit'],windowsHide:true});child.on('error',()=>process.exit(1));child.on('exit',()=>process.exit(1));process.stdin.once('data',data=>{child.stdin.write(data.subarray(0,128),()=>{child.kill('SIGTERM')})});`)
  await expect(command(['push','origin','HEAD:interrupted'],'owner',{GIT_SSH_COMMAND:[process.execPath,wrapper].map(quote).join(' '),GITGOOD_TEST_SSH:ssh,GITGOOD_TEST_SSH_ARGS:JSON.stringify(args('owner'))})).rejects.toThrow()
  expect((await command(['ls-remote','origin','refs/heads/interrupted'])).stdout.trim()).toBe('')
  expect((await command(['ls-remote','origin','refs/heads/feature'])).stdout).toContain(feature)
  await command(['push','origin','HEAD:interrupted'])
  expect((await command(['ls-remote','origin','refs/heads/interrupted'])).stdout).toContain(interrupted)
  const actor=(await (await fetch(upstream+'/api/session',{headers:owner})).json()).user.id
  const operations=(await (await fetch(upstream+'/api/repos/team/'+name+'/operations',{headers:owner})).json()).operations
  const applied=operations.filter((o:{kind:string;state:string})=>o.kind==='push'&&o.state==='applied')
  expect(applied).toHaveLength(3)
  for(const operation of applied) {expect(operation.actor_id).toBe(actor);expect(operation.credential_id).toBe(ownerKey.credential_id)}
  expect(operations.some((o:{kind:string;state:string})=>o.kind==='push'&&o.state==='failed')).toBe(true)
  await page.goto('/')
  await expect(page.getByRole('heading',{name:label,exact:true})).toBeVisible()
  await page.getByRole('button',{name:'Revoke '+label,exact:true}).click()
  await expect(page.getByRole('heading',{name:label,exact:true}).locator('..').getByText('Revoked',{exact:true})).toBeVisible()
  await expect(command(['ls-remote','origin'])).rejects.toThrow()
  const finalKeys=await (await fetch(upstream+'/api/ssh-keys',{headers:owner})).json()
  expect(finalKeys.keys.find((k:{id:number})=>k.id===ownerKey.id).revoked).toBe(true)
  await page.locator('.ssh-panel').screenshot({path:info.outputPath('ssh-key-management.png')})
  await writeFile(info.outputPath('ssh-receipt.json'),JSON.stringify({repository:repo.id,initial,feature,interrupted,ownerCredential:ownerKey.credential_id,hostFingerprint:keyList.transport.fingerprint,checks:['lost-reply browser registration','strict host verification','byte-exact clone','push/fetch','protected main','reader/outsider/wrong identity denial','duplicate key denial','arbitrary exec and SFTP denial','interrupted push and retry','browser revocation']},null,2)+'\n')
})
