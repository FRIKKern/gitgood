import {spawn} from 'node:child_process'
import {mkdtemp,cp,mkdir,readFile,writeFile,rename} from 'node:fs/promises'
import {createWriteStream} from 'node:fs'
import {tmpdir} from 'node:os'
import {dirname,join,resolve,sep} from 'node:path'
import {fileURLToPath} from 'node:url'
import {randomBytes} from 'node:crypto'
import {createServer} from 'node:https'
import {request as httpRequest} from 'node:http'
import assert from 'node:assert/strict'
const repository=resolve(dirname(fileURLToPath(import.meta.url)),'..')
const sourceWeb=join(repository,'apps/web')
const sourceForge=join(repository,'apps/forge')
const root=await mkdtemp(join(tmpdir(),'gitgood-production-'))
const installedForge=join(root,'forge')
const installedWeb=join(root,'web')
const windows=process.platform==='win32'
const releaseName=windows?'gitgood.bat':'gitgood'
const release=join(installedForge,'bin',releaseName)
const forgePort=Number(process.env.GITGOOD_VERIFY_FORGE_PORT??47851)
const webPort=Number(process.env.GITGOOD_VERIFY_WEB_PORT??47850)
const forgeUrl='http://127.0.0.1:'+forgePort
const webUrl='http://127.0.0.1:'+webPort
const database='gitgood_production_'+randomBytes(4).toString('hex')
const storage=join(root,'storage')
const sshPort=Number(process.env.GITGOOD_VERIFY_SSH_PORT??47852)
const sshHost=join(root,'ssh-host')
const ssh=process.env.GITGOOD_SSH??(windows?'C:/Windows/System32/OpenSSH/ssh.exe':'ssh')
const keygen=process.env.GITGOOD_SSH_KEYGEN??(windows?'C:/Windows/System32/OpenSSH/ssh-keygen.exe':'ssh-keygen')
const identity=JSON.parse(await readFile(join(sourceWeb,'dist/build-identity.json'),'utf8'))
assert.equal(identity.dirty,false,'Production verification requires a clean stamped candidate')
const logs=join(root,'logs')
await mkdir(logs)
let backend,web,proxy
const log=(name)=>createWriteStream(join(logs,name+'.log'),{flags:'a'})
function launch(file,args,env,cwd,name) {
  // Only fixed release commands use cmd on Windows. Credentials are exclusively in environment.
  const child=spawn(file,args,{cwd,env,windowsHide:true,shell:windows&&file.endsWith('.bat'),detached:!windows,stdio:['ignore','pipe','pipe']})
  const output=log(name);child.stdout?.pipe(output);child.stderr?.pipe(output)
  child.logged=new Promise((resolve,reject)=>{output.once('finish',resolve);output.once('error',reject)})
  child.once('close',()=>output.end())
  return child
}
async function wait(child,name,allowed=[0]) {
  const result=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('close',(code)=>resolve(code))})
  await child.logged
  assert(allowed.includes(result),name+' failed with exit '+result+'; private logs: '+logs)
}
async function run(file,args,env,cwd,name) {await wait(launch(file,args,env,cwd,name),name)}
async function stop(child) {
  if(!child || child.exitCode!==null || child.signalCode!==null)return
  const ended=new Promise(resolve=>child.once('exit',resolve))
  if(windows) {
    await new Promise(resolve=>{const killer=spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});killer.once('exit',resolve);killer.once('error',resolve)})
  }else{try{process.kill(-child.pid,'SIGTERM')}catch{}}
  await Promise.race([ended,new Promise(resolve=>setTimeout(resolve,5000))])
}
async function ready(url,expected=true) {
  const deadline=Date.now()+45000
  let last
  while(Date.now()<deadline) {
    try{last=await fetch(url+'/health/ready',{signal:AbortSignal.timeout(3000)});if(last.status===(expected?200:503))return await last.json()}catch{}
    await new Promise(resolve=>setTimeout(resolve,250))
  }
  throw new Error('Readiness did not reach expected state at '+url)
}
function inside(path) {const absolute=resolve(path);assert(absolute.startsWith(resolve(root)+sep),'Fixture path escaped install root');return absolute}
try {
  await cp(process.env.GITGOOD_RELEASE_PATH??join(sourceForge,'_build/prod/rel/gitgood'),installedForge,{recursive:true})
  await mkdir(installedWeb)
  for(const name of ['dist','server.mjs','package.json','package-lock.json'])await cp(join(sourceWeb,name),join(installedWeb,name),{recursive:true})
  const npm=process.env.npm_execpath??join(dirname(process.execPath),'node_modules/npm/bin/npm-cli.js')
  await run(process.execPath,[npm,'ci','--omit=dev','--ignore-scripts'],process.env,installedWeb,'web-install')
  const certificate=join(root,'fixture-certificate.pem'),key=join(root,'fixture-key.pem')
  await run(process.env.GITGOOD_OPENSSL??'openssl',['req','-x509','-newkey','rsa:2048','-sha256','-nodes','-keyout',key,'-out',certificate,'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],process.env,root,'fixture-tls')
  await mkdir(sshHost)
  await run(keygen,['-q','-t','ed25519','-N','','-f',join(sshHost,'ssh_host_ed25519_key')],process.env,root,'fixture-ssh-host')
  proxy=createServer({key:await readFile(key),cert:await readFile(certificate)},(request,response)=>{
    if(request.url?.startsWith('/internal/')){response.writeHead(404);response.end();return}
    const target=request.url?.startsWith('/git/')?forgeUrl:webUrl
    const upstream=httpRequest(new URL(request.url,target),{method:request.method,headers:{...request.headers,host:new URL(target).host,'x-forwarded-proto':'https'},agent:false},result=>{response.writeHead(result.statusCode,result.headers);result.pipe(response)})
    upstream.on('error',()=>{if(!response.headersSent)response.writeHead(503);response.end()})
    request.pipe(upstream)
  })
  await new Promise(resolve=>proxy.listen(0,'127.0.0.1',resolve))
  const publicUrl='https://localhost:'+proxy.address().port
  const env={...process.env,NODE_ENV:'production',DATABASE_URL:'postgresql://'+encodeURIComponent(process.env.PGUSER??'gitgood')+(process.env.PGPASSWORD?':'+encodeURIComponent(process.env.PGPASSWORD):'')+'@'+(process.env.PGHOST??'127.0.0.1')+':'+(process.env.PGPORT??'55432')+'/'+database,
    SECRET_KEY_BASE:randomBytes(64).toString('base64'),PHX_HOST:'localhost',GITGOOD_PUBLIC_URL:publicUrl,GITGOOD_WEB_ORIGIN:publicUrl,GITGOOD_STORAGE:storage,PORT:String(forgePort),PHX_SERVER:'false',
    GITGOOD_SSH_PORT:String(sshPort),GITGOOD_SSH_HOST_KEY_DIRECTORY:sshHost,GITGOOD_SSH_PUBLIC_HOST:'localhost',GITGOOD_SSH_PUBLIC_PORT:String(sshPort)}
  await run(process.env.GITGOOD_CREATEDB??'createdb',['-h',process.env.PGHOST??'127.0.0.1','-p',process.env.PGPORT??'55432','-U',process.env.PGUSER??'gitgood',database],process.env,root,'database-create')
  await run(release,['eval','Gitgood.Release.migrate()'],env,installedForge,'migrate')
  for(const [username,team,role] of [['owner','team','owner'],['reviewer','team','writer'],['reader','team','reader'],['outsider','elsewhere','owner']]) {
    await run(release,['eval','Gitgood.Release.bootstrap()'],{...env,GITGOOD_BOOTSTRAP_USERNAME:username,GITGOOD_BOOTSTRAP_TEAM:team,GITGOOD_BOOTSTRAP_ROLE:role,GITGOOD_BOOTSTRAP_PASSWORD:'synthetic-password'},installedForge,'bootstrap')
  }
  const webEnv={...process.env,NODE_ENV:'production',PORT:String(webPort),GITGOOD_API_URL:forgeUrl}
  const startBackend=()=>launch(release,['start'],{...env,PHX_SERVER:'true'},installedForge,'forge')
  const startWeb=()=>launch(process.execPath,[join(installedWeb,'node_modules/srvx/bin/srvx.mjs'),'--prod','-s','dist/client','server.mjs'],webEnv,installedWeb,'web')
  backend=startBackend();web=startWeb()
  const forgeReady=await ready(forgeUrl),webReady=await ready(webUrl)
  assert.equal(forgeReady.candidate,identity.candidate);assert.equal(webReady.candidate,identity.candidate)
  const html=await fetch(webUrl);assert.equal(html.status,200);assert((await html.text()).includes('gitgood'))
  const testEnv={...process.env,GITGOOD_TEST_API_URL:forgeUrl,GITGOOD_TEST_WEB_URL:publicUrl,GITGOOD_TEST_PRODUCTION:'true',GITGOOD_TEST_CA:certificate}
  await run(process.execPath,[join(sourceWeb,'node_modules/@playwright/test/cli.js'),'test'],testEnv,sourceWeb,'browser')
  const login=async()=>{
    const response=await fetch(forgeUrl+'/api/session',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:'owner',password:'synthetic-password'})})
    assert.equal(response.status,200)
    return 'Bearer '+/gitgood_session=([^;]+)/.exec(response.headers.getSetCookie()[0])[1]
  }
  const authorization=await login()
  const before=await (await fetch(forgeUrl+'/api/repos',{headers:{authorization}})).json()
  assert(before.repositories.length>=2)
  const clientKey=join(root,'restart-client')
  await run(keygen,['-q','-t','ed25519','-N','','-f',clientKey],process.env,root,'fixture-ssh-client')
  const registered=await fetch(forgeUrl+'/api/ssh-keys',{method:'POST',headers:{authorization,'content-type':'application/json','idempotency-key':'production-restart-key'},body:JSON.stringify({label:'Restart proof',public_key:await readFile(clientKey+'.pub','utf8')})})
  assert.equal(registered.status,201)
  const sshBefore=await (await fetch(forgeUrl+'/api/ssh-keys',{headers:{authorization}})).json()
  await stop(web);web=null;await stop(backend);backend=null
  backend=startBackend();web=startWeb()
  await ready(forgeUrl);await ready(webUrl)
  const after=await (await fetch(forgeUrl+'/api/repos',{headers:{authorization}})).json()
  assert.deepEqual(after.repositories.map(r=>r.id),before.repositories.map(r=>r.id),'Repositories and session must survive restart')
  const imported=JSON.parse(await readFile(join(sourceWeb,'test-results-production/import-receipt.json'),'utf8'))
  const importRepo=after.repositories.find(r=>r.id===imported.repository_id)
  assert(importRepo,'Imported repository must persist after restart')
  const importBase=forgeUrl+'/api/repos/'+importRepo.team+'/'+importRepo.name
  const importState=await (await fetch(importBase+'/operations/'+imported.operation_id,{headers:{authorization}})).json()
  assert.equal(importState.operation.state,'applied')
  assert.equal(importState.operation.metadata.source_sha256,imported.source_sha256)
  assert.deepEqual(importState.operation.updates,imported.updates,'Import provenance and exact expected refs must persist')
  const importKeys=await (await fetch(importBase+'/credentials',{method:'POST',headers:{authorization}})).json()
  const importEnv={...process.env,GIT_TERMINAL_PROMPT:'0',GIT_SSL_CAINFO:certificate,GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:windows?'NUL':'/dev/null',GIT_CONFIG_COUNT:'2',GIT_CONFIG_KEY_0:'credential.helper',GIT_CONFIG_VALUE_0:'',GIT_CONFIG_KEY_1:'http.extraHeader',GIT_CONFIG_VALUE_1:'Authorization: Basic '+Buffer.from('owner:'+importKeys.token).toString('base64')}
  delete importEnv.GIT_SSL_NO_VERIFY
  await run(process.env.GITGOOD_GIT??'git',['ls-remote',importRepo.clone_url,'refs/heads/*','refs/tags/*'],importEnv,root,'persisted-import-read')
  const importRefs=await readFile(join(logs,'persisted-import-read.log'),'utf8')
  for(const update of imported.updates)assert(importRefs.split(/\r?\n/).includes(update.new+'\t'+update.ref),'Exact imported ref must persist')
  const gitRepo=after.repositories.find(r=>r.name.startsWith('git-'))
  assert(gitRepo)
  const branches=await (await fetch(forgeUrl+'/api/repos/'+gitRepo.team+'/'+gitRepo.name+'/branches',{headers:{authorization}})).json()
  const main=branches.branches.find(b=>b.name==='main');assert(main)
  const credentials=await fetch(forgeUrl+'/api/repos/'+gitRepo.team+'/'+gitRepo.name+'/credentials',{method:'POST',headers:{authorization}})
  const credential=await credentials.json()
  const gitEnv={...process.env,GIT_TERMINAL_PROMPT:'0',GIT_SSL_CAINFO:certificate,GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:windows?'NUL':'/dev/null',GIT_CONFIG_COUNT:'2',GIT_CONFIG_KEY_0:'credential.helper',GIT_CONFIG_VALUE_0:'',GIT_CONFIG_KEY_1:'http.extraHeader',GIT_CONFIG_VALUE_1:'Authorization: Basic '+Buffer.from('owner:'+credential.token).toString('base64')}
  delete gitEnv.GIT_SSL_NO_VERIFY
  await run(process.env.GITGOOD_GIT??'git',['ls-remote',gitRepo.clone_url,'refs/heads/main'],gitEnv,root,'persisted-git-read')
  const persistedRef=await readFile(join(logs,'persisted-git-read.log'),'utf8')
  assert(persistedRef.split(/\r?\n/).includes(main.sha+'\trefs/heads/main'),'Returned clone URL must serve the persisted main SHA')
  const sshAfter=await (await fetch(forgeUrl+'/api/ssh-keys',{headers:{authorization}})).json()
  assert.deepEqual(sshAfter.transport,sshBefore.transport,'SSH host identity must persist across release restart')
  const known=join(root,'known_hosts')
  await writeFile(known,'[localhost]:'+sshPort+' '+sshAfter.transport.public_key+'\n')
  const quote=value=>"'"+value.replaceAll("'","'\\''")+"'"
  const sshEnv={...process.env,GIT_SSH_VARIANT:'ssh',GIT_SSH_COMMAND:[ssh,'-F',windows?'NUL':'/dev/null','-i',clientKey,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+known].map(quote).join(' ')}
  await run(process.env.GITGOOD_GIT??'git',['ls-remote',gitRepo.ssh_clone_url,'refs/heads/main'],sshEnv,root,'persisted-ssh-read')
  const sshRef=await readFile(join(logs,'persisted-ssh-read.log'),'utf8')
  assert(sshRef.split(/\r?\n/).includes(main.sha+'\trefs/heads/main'),'Returned SSH clone URL must serve persisted main with a persisted account key')
  await rename(inside(storage),inside(join(root,'storage-unavailable')))
  try{await ready(forgeUrl,false);await ready(webUrl,false)}
  finally{await rename(inside(join(root,'storage-unavailable')),inside(storage))}
  await ready(forgeUrl);await ready(webUrl)
  await stop(web);web=null
  const identityFile=join(installedWeb,'dist/build-identity.json'),original=await readFile(identityFile)
  await writeFile(identityFile,JSON.stringify({...identity,candidate:'0'.repeat(40)}))
  web=startWeb();await ready(webUrl,false)
  await stop(web);web=null
  await writeFile(identityFile,original)
  web=startWeb();await ready(webUrl)
  const receipt={candidate:identity.candidate,identity,recordedAt:new Date().toISOString(),installation:root,database,
    runtime:{node:process.version,forge:forgeReady.runtime},actors:['owner','reviewer','reader','outsider'],persistentRepositories:after.repositories.map(r=>r.id),main:main.sha,importOperation:imported.operation_id,
    checks:['source-free copied Elixir release','production-only web dependency install','production SSR and static assets','browser and real HTTPS/SSH/import end-to-end flows','session/database/Git persistence after process restart','import provenance/branches/tags persistence after restart','returned HTTPS clone URL','persisted SSH host/account identity and returned SSH clone URL','missing storage rejects forge and web readiness','mismatched component identity rejects readiness'],
    browserTls:'Self-signed fixture bypass in browser only; real Git verifies its explicit CA',
    limitations:['No managed Cloud deployment','No replacement-host restore or storage power-loss proof']}
  await mkdir(join(sourceWeb,'test-results-production'),{recursive:true})
  await writeFile(join(sourceWeb,'test-results-production/production-receipt.json'),JSON.stringify(receipt,null,2)+'\n')
  console.log('PASS production artifacts, full workflow, persistence and readiness rejection: '+identity.candidate)
}finally {
  await stop(web);await stop(backend)
  if(proxy){proxy.closeAllConnections();await new Promise(resolve=>proxy.close(resolve))}
}
