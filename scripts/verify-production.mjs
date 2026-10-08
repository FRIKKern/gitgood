import {spawn} from 'node:child_process'
import {mkdtemp,cp,mkdir,readFile,writeFile,rename} from 'node:fs/promises'
import {createWriteStream} from 'node:fs'
import {tmpdir} from 'node:os'
import {dirname,join,resolve,sep} from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {randomBytes,createHash} from 'node:crypto'
import {request as httpsRequest} from 'node:https'
import {createHmac} from 'node:crypto'
import {createServer as netServer} from 'node:net'
import assert from 'node:assert/strict'
import {verifyOfflineRecovery} from './verify-offline-recovery.mjs'
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
const proxyKey=randomBytes(32).toString('base64')
const observedProbePeers=new Set()
const caddyExecutable=process.env.GITGOOD_CADDY
assert(caddyExecutable,'Copied production verification requires the actual Caddy binary')
const sshHost=join(root,'ssh-host')
const ssh=process.env.GITGOOD_SSH??(windows?'C:/Windows/System32/OpenSSH/ssh.exe':'ssh')
const keygen=process.env.GITGOOD_SSH_KEYGEN??(windows?'C:/Windows/System32/OpenSSH/ssh-keygen.exe':'ssh-keygen')
const identity=JSON.parse(await readFile(join(sourceWeb,'dist/build-identity.json'),'utf8'))
assert.equal(identity.dirty,false,'Production verification requires a clean stamped candidate')
const logs=join(root,'logs')
await mkdir(logs)
let backend,web,caddy,sourceFixture
const log=(name)=>createWriteStream(join(logs,name+'.log'),{flags:'a'})
function launch(file,args,env,cwd,name,stdin='ignore') {
  // Only fixed release commands use cmd on Windows. Credentials are exclusively in environment.
  const child=spawn(file,args,{cwd,env,windowsHide:true,shell:windows&&file.endsWith('.bat'),detached:!windows,stdio:[stdin,'pipe','pipe']})
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
  if(!child)return
  if(child.runtimeCgroup){
    await writeFile(join(child.runtimeCgroup,'cgroup.kill'),'1')
    const deadline=Date.now()+5000
    while(!(await readFile(join(child.runtimeCgroup,'cgroup.events'),'utf8')).includes('populated 0')){
      assert(Date.now()<deadline,'Owned runtime cgroup did not become empty')
      await new Promise(resolve=>setTimeout(resolve,25))
    }
  }
  if(child.exitCode!==null || child.signalCode!==null)return
  const ended=new Promise(resolve=>child.once('exit',resolve))
  if(windows) {
    await new Promise(resolve=>{const killer=spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});killer.once('exit',resolve);killer.once('error',resolve)})
  }else{try{process.kill(-child.pid,'SIGTERM')}catch{}}
  await Promise.race([ended,new Promise(resolve=>setTimeout(resolve,5000))])
  if(windows&&child.installationRoot){
    const marker=join(child.installationRoot,'.gitgood-runtime-v1.json'),deadline=Date.now()+15000
    while(true){
      try{
        await promisify(execFile)(process.env.GITGOOD_PYTHON,['-I',join(sourceForge,'priv/operations/process_status.py'),marker],{timeout:5000,maxBuffer:1024,windowsHide:true})
        break
      }catch{assert(Date.now()<deadline,'Previous native process instance did not finish stopping');await new Promise(resolve=>setTimeout(resolve,50))}
    }
  }
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
  for(const name of ['dist','server.mjs','client-address.mjs','package.json','package-lock.json'])await cp(join(sourceWeb,name),join(installedWeb,name),{recursive:true})
  const npm=process.env.npm_execpath??join(dirname(process.execPath),'node_modules/npm/bin/npm-cli.js')
  await run(process.execPath,[npm,'ci','--omit=dev','--ignore-scripts'],process.env,installedWeb,'web-install')
  const certificate=join(root,'fixture-certificate.pem'),key=join(root,'fixture-key.pem')
  await run(process.env.GITGOOD_OPENSSL??'openssl',['req','-x509','-newkey','rsa:2048','-sha256','-nodes','-keyout',key,'-out',certificate,'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],process.env,root,'fixture-tls')
  await mkdir(sshHost)
  await run(keygen,['-q','-t','ed25519','-N','','-f',join(sshHost,'ssh_host_ed25519_key')],process.env,root,'fixture-ssh-host')
  const reservation=netServer()
  await new Promise(resolve=>reservation.listen(0,'127.0.0.1',resolve))
  const publicPort=reservation.address().port
  await new Promise(resolve=>reservation.close(resolve))
  const publicUrl='https://localhost:'+publicPort
  const quotePath=path=>'"'+path.replaceAll('\\','/')+'"'
  const accessLog=join(logs,'caddy-access.log')
  const edgeTemplate=(await readFile(join(repository,'docs/deployment/Caddyfile.example'),'utf8')).replaceAll('\r\n','\n')
  const edgeSource=edgeTemplate.replace('gitgood.example.invalid',publicUrl)
    .replaceAll('127.0.0.1:47841','127.0.0.1:'+forgePort).replaceAll('127.0.0.1:47840','127.0.0.1:'+webPort)
    .replace(publicUrl+' {',publicUrl+' {\n  bind 127.0.0.1\n  tls '+quotePath(certificate)+' '+quotePath(key)+
      '\n  log {\n    output file '+quotePath(accessLog)+' {\n      mode 0600\n    }\n    format filter {\n      wrap json\n      fields {\n        request>headers delete\n        resp_headers delete\n      }\n    }\n  }')
  const edgeConfig=join(root,'Caddyfile')
  await writeFile(edgeConfig,'{\n  admin off\n  auto_https off\n  persist_config off\n}\n'+edgeSource)
  const edgeEnv={...process.env,GITGOOD_PROXY_KEY:proxyKey,XDG_DATA_HOME:join(root,'caddy-data'),XDG_CONFIG_HOME:join(root,'caddy-config'),APPDATA:join(root,'caddy-appdata')}
  await run(caddyExecutable,['version'],edgeEnv,root,'caddy-version')
  await run(caddyExecutable,['validate','--config',edgeConfig,'--adapter','caddyfile'],edgeEnv,root,'caddy-validate')
  const caddyVersion=(await readFile(join(logs,'caddy-version.log'),'utf8')).trim()
  assert(caddyVersion.startsWith('v2.11.7 '),'The verified direct-edge runtime is Caddy 2.11.7')
  caddy=launch(caddyExecutable,['run','--config',edgeConfig,'--adapter','caddyfile'],edgeEnv,root,'caddy')
  const sourceCa=join(root,'source-ca.pem')
  sourceFixture=launch(process.env.GITGOOD_PYTHON??'python3',['-I',join(sourceForge,'verification/barkpark_http_fixture.py'),
    process.env.GITGOOD_OPENSSL??'openssl',sourceCa],process.env,root,'source-wire','pipe')
  const sourcePorts=await new Promise((resolve,reject)=>{
    let output=''
    const deadline=setTimeout(()=>reject(new Error('Owned HTTPS source wire not ready')),20000)
    sourceFixture.once('error',reject)
    sourceFixture.stdout.on('data',chunk=>{
      output+=chunk.toString()
      const ready=/READY (\d+) (\d+) (\d+)/.exec(output)
      if(ready){clearTimeout(deadline);resolve(ready.slice(1).map(Number))}
    })
  })
  const sourceOrigin='https://127.0.0.1:'+sourcePorts[1]
  const sourceControl='http://127.0.0.1:'+sourcePorts[0]
  const env={...process.env,NODE_ENV:'production',DATABASE_URL:'postgresql://'+encodeURIComponent(process.env.PGUSER??'gitgood')+(process.env.PGPASSWORD?':'+encodeURIComponent(process.env.PGPASSWORD):'')+'@'+(process.env.PGHOST??'127.0.0.1')+':'+(process.env.PGPORT??'55432')+'/'+database,
    GITGOOD_PROXY_KEY:proxyKey,GITGOOD_BARKPARK_ORIGIN:sourceOrigin,GITGOOD_BARKPARK_CA:sourceCa,GITGOOD_CONNECTION_KEY:randomBytes(32).toString('base64'),
    SECRET_KEY_BASE:randomBytes(64).toString('base64'),PHX_HOST:'localhost',GITGOOD_PUBLIC_URL:publicUrl,GITGOOD_WEB_ORIGIN:publicUrl,GITGOOD_STORAGE:storage,PORT:String(forgePort),PHX_SERVER:'false',
    GITGOOD_SSH_PORT:String(sshPort),GITGOOD_SSH_HOST_KEY_DIRECTORY:sshHost,GITGOOD_SSH_PUBLIC_HOST:'localhost',GITGOOD_SSH_PUBLIC_PORT:String(sshPort)}
  await run(process.env.GITGOOD_CREATEDB??'createdb',['-h',process.env.PGHOST??'127.0.0.1','-p',process.env.PGPORT??'55432','-U',process.env.PGUSER??'gitgood',database],process.env,root,'database-create')
  await run(release,['eval','Gitgood.Release.migrate()'],env,installedForge,'migrate')
  for(const [username,team,role] of [['owner','team','owner'],['reviewer','team','writer'],['reader','team','reader'],['outsider','elsewhere','owner']]) {
    await run(release,['eval','Gitgood.Release.bootstrap()'],{...env,GITGOOD_BOOTSTRAP_USERNAME:username,GITGOOD_BOOTSTRAP_TEAM:team,GITGOOD_BOOTSTRAP_ROLE:role,GITGOOD_BOOTSTRAP_PASSWORD:'synthetic-password'},installedForge,'bootstrap')
  }
  const webEnv={...process.env,NODE_ENV:'production',PORT:String(webPort),GITGOOD_API_URL:forgeUrl,GITGOOD_PROXY_KEY:proxyKey}
  const startBackend=(configuration={...env,PHX_SERVER:'true'})=>{
    const group=process.env.GITGOOD_VERIFY_CGROUP
    const child=group?launch(process.env.GITGOOD_PYTHON??'python3',['-I',join(sourceForge,'priv/operations/runtime_cgroup.py'),group,release,'start'],configuration,installedForge,'forge'):
      launch(release,['start'],configuration,installedForge,'forge')
    if(group)child.runtimeCgroup=group
    child.installationRoot=configuration.GITGOOD_STORAGE
    return child
  }
  const startWeb=()=>launch(process.execPath,[join(installedWeb,'node_modules/srvx/bin/srvx.mjs'),'--prod','-s','dist/client','server.mjs'],webEnv,installedWeb,'web')
  backend=startBackend();web=startWeb()
  const forgeReady=await ready(forgeUrl),webReady=await ready(webUrl)
  assert.equal(forgeReady.candidate,identity.candidate);assert.equal(webReady.candidate,identity.candidate)
  const html=await fetch(webUrl);assert.equal(html.status,200);assert((await html.text()).includes('gitgood'))
  // Real TLS socket addresses select independent login buckets; caller headers are adversarial.
  // Observe the native monotonic window externally; no limiter reset, fake clock or raised allowance.
  const tlsLogin=(localAddress,index,password='invalid-synthetic-password',query='address_probe')=>new Promise((resolve,reject)=>{
    const body=JSON.stringify({username:'owner',password})
    const request=httpsRequest({hostname:'127.0.0.1',servername:'localhost',port:publicPort,
      path:'/api/session?'+query+'='+index,method:'POST',localAddress,ca:fixtureIssuer,rejectUnauthorized:true,
      headers:{host:new URL(publicUrl).host,'content-type':'application/json','content-length':Buffer.byteLength(body),
        'x-forwarded-for':'198.51.100.'+(index%200+1),forwarded:'for=203.0.113.'+(index%200+1),
        'x-gitgood-edge-key':'forged-edge-secret','x-gitgood-edge-client':'198.51.100.'+(index%200+1),
        'x-gitgood-client-address':'203.0.113.'+(index%200+1),'x-gitgood-client-time':String(Math.floor(Date.now()/1000)),
        'x-gitgood-client-signature':'0'.repeat(64)},agent:false},response=>{
      const chunks=[];response.on('data',chunk=>chunks.push(chunk))
      response.on('end',()=>{
        try{resolve({status:response.statusCode,body:JSON.parse(Buffer.concat(chunks).toString('utf8'))})}
        catch{reject(new Error('TLS login probe returned non-JSON at HTTP '+response.statusCode))}
      })
    })
    request.on('error',reject);request.setTimeout(12000,()=>request.destroy(new Error('TLS login probe deadline')))
    request.end(body)
  })
  // Load the disposable issuer explicitly; never disable TLS verification for these client sockets.
  const fixtureIssuer=await readFile(certificate)
  const warmupStatuses=[],warmupStarted=performance.now()
  let lastDeniedAt,lastDeniedWallTime
  for(let attempt=1;attempt<=41;attempt++){
    const started=performance.now(),wallTime=new Date().toISOString()
    const result=await tlsLogin('127.0.0.4',attempt,'invalid-synthetic-password','rate_window_warmup')
    assert([401,429].includes(result.status),'Window warmup must reach native authentication or rate refusal')
    warmupStatuses.push(result.status)
    assert(performance.now()-warmupStarted<55000,'Window warmup exceeded its bounded duration')
    if(result.status===429){lastDeniedAt=started;lastDeniedWallTime=wallTime;break}
  }
  assert(lastDeniedAt!==undefined,'Window warmup must observe rate refusal')
  const resetDeadline=performance.now()+70000,resetStatuses=[]
  while(true){
    assert(performance.now()<resetDeadline,'Native rate window did not reset within the bounded wait')
    await new Promise(resolve=>setTimeout(resolve,1000))
    const started=performance.now(),wallTime=new Date().toISOString()
    const result=await tlsLogin('127.0.0.4',resetStatuses.length+1,'invalid-synthetic-password','rate_window_reset')
    assert([401,429].includes(result.status),'Window reset probe must reach native authentication or rate refusal')
    resetStatuses.push(result.status)
    if(result.status===401)break
    lastDeniedAt=started;lastDeniedWallTime=wallTime
  }
  const observedResetAt=new Date().toISOString(),probeStarted=performance.now()
  const limitedStatuses=[]
  for(let attempt=1;attempt<=21;attempt++){
    const result=await tlsLogin('127.0.0.2',attempt)
    assert.equal(result.status,attempt<=20?401:429)
    limitedStatuses.push(result.status)
  }
  assert.equal((await tlsLogin('127.0.0.2',22,'synthetic-password')).status,429,'Changing caller forwarding fields cannot escape a socket address bucket')
  const independent=await tlsLogin('127.0.0.3',23,'synthetic-password')
  assert.equal(independent.status,200);assert.equal(independent.body.user.username,'owner')
  const elapsedSinceLastDenied=performance.now()-lastDeniedAt,probeDuration=performance.now()-probeStarted
  assert(elapsedSinceLastDenied<58000,'The address proof must finish before another native fixed-window boundary')
  const edgeLogDeadline=Date.now()+5000
  do {
    const records=(await readFile(accessLog,'utf8')).trim().split('\n').filter(Boolean).map(line=>JSON.parse(line))
    for(const record of records){
      assert(!record.request?.headers&&!record.resp_headers,'Edge evidence must omit all credential-bearing headers')
      if(record.request?.uri?.startsWith('/api/session?address_probe='))observedProbePeers.add(record.request.remote_ip)
    }
    if(observedProbePeers.size===2)break
    await new Promise(resolve=>setTimeout(resolve,50))
  }while(Date.now()<edgeLogDeadline)
  assert.deepEqual([...observedProbePeers].sort(),['127.0.0.2','127.0.0.3'])
  assert(!(await readFile(join(logs,'caddy.log'),'utf8')).includes(proxyKey),'Caddy runtime log must not contain the edge secret')
  const directLogin={method:'POST',headers:{'content-type':'application/json','x-forwarded-for':'198.51.100.22',
    'x-gitgood-edge-key':'forged-edge-secret','x-gitgood-edge-client':'198.51.100.22',
    'x-gitgood-client-address':'198.51.100.22','x-gitgood-client-time':String(Math.floor(Date.now()/1000)),
    'x-gitgood-client-signature':'0'.repeat(64)},body:JSON.stringify({username:'owner',password:'synthetic-password'})}
  for(const origin of [forgeUrl,webUrl]){
    const refused=await fetch(origin+'/api/session',directLogin)
    assert.equal(refused.status,403);assert.deepEqual(await refused.json(),{error:'client_address_unverified'})
  }
  const clientAddressProof={edge:'actual Caddy using the committed direct-edge example',caddy_version:caddyVersion,template_sha256:createHash('sha256').update(edgeTemplate).digest('hex'),
    native_window:{warmup_peer:'127.0.0.4',warmup_statuses:warmupStatuses,reset_statuses:resetStatuses,last_denied_at:lastDeniedWallTime,observed_reset_at:observedResetAt,elapsed_since_last_denied_ms:elapsedSinceLastDenied,probe_duration_ms:probeDuration},actual_tls_peers:[...observedProbePeers].sort(),
    limited_statuses:limitedStatuses,changed_forwarding_cannot_escape:true,independent_actor:independent.body.user,
    direct_forge_and_web_refused:true,normal_tls_issuer_and_hostname_verification:true}
  const testEnv={...process.env,GITGOOD_TEST_API_URL:forgeUrl,GITGOOD_TEST_WEB_URL:publicUrl,GITGOOD_TEST_PRODUCTION:'true',GITGOOD_TEST_CA:certificate,NODE_EXTRA_CA_CERTS:certificate,GITGOOD_TEST_SOURCE_CONTROL:sourceControl}
  await run(process.execPath,[join(sourceWeb,'node_modules/@playwright/test/cli.js'),'test'],testEnv,sourceWeb,'browser')
  const signedLogin=()=>{
    const stamp=String(Math.floor(Date.now()/1000)),address='127.0.0.1'
    const frame=['gitgood-login-origin-v1',address,stamp,'POST','/api/session'].join('\n')
    return {'x-gitgood-client-address':address,'x-gitgood-client-time':stamp,
      'x-gitgood-client-signature':createHmac('sha256',Buffer.from(proxyKey,'base64')).update(frame).digest('hex')}
  }
  const login=async()=>{
    const response=await fetch(forgeUrl+'/api/session',{method:'POST',headers:{'content-type':'application/json',...signedLogin()},body:JSON.stringify({username:'owner',password:'synthetic-password'})})
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
  const discovery=JSON.parse(await readFile(join(sourceWeb,'test-results-production/activity-receipt.json'),'utf8'))
  const persistedActivity=await (await fetch(forgeUrl+'/api/repos/team/'+discovery.repository+'/activity',{headers:{authorization}})).json()
  const retainedActivity=persistedActivity.records.find(record=>record.url===discovery.record.url)
  assert(retainedActivity,'Permitted native activity link must persist after restart')
  assert.equal(retainedActivity.id,discovery.record.id)
  assert.equal(retainedActivity.occurred_at,discovery.record.occurred_at)
  const memberAudit=await (await fetch(forgeUrl+'/api/teams/team/members',{headers:{authorization}})).json()
  assert(!memberAudit.members.some(member=>member.username==='outsider'),'Removed access must remain removed after restart')
  for(const id of discovery.membership_events)assert(memberAudit.events.some(event=>event.id===id),'Audited access change must persist')
  const outsiderLogin=await fetch(forgeUrl+'/api/session',{method:'POST',headers:{'content-type':'application/json',...signedLogin()},body:JSON.stringify({username:'outsider',password:'synthetic-password'})})
  assert.equal(outsiderLogin.status,200)
  const outsiderAuth='Bearer '+/gitgood_session=([^;]+)/.exec(outsiderLogin.headers.getSetCookie()[0])[1]
  const deniedSearch=await (await fetch(forgeUrl+'/api/search?q='+discovery.repository,{headers:{authorization:outsiderAuth}})).json()
  assert.deepEqual(deniedSearch.records,[],'Restart must not restore revoked search access')
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
  const gitFlow=JSON.parse(await readFile(join(sourceWeb,'test-results-production/git-receipt.json'),'utf8'))
  const gitRepo=after.repositories.find(r=>r.id===gitFlow.repository)
  assert(gitRepo,'The browser change repository must persist')
  const nativeChangeUrl='/repos/'+gitRepo.team+'/'+gitRepo.name+'/pulls/'+gitFlow.pullRequest
  for(const origin of [forgeUrl,webUrl]) {
    const allowedAlias=await fetch(origin+'/api/changes/'+gitFlow.pullRequest,{headers:{authorization}})
    assert.equal(allowedAlias.status,200)
    assert.equal(allowedAlias.headers.get('cache-control'),'no-store')
    const resolvedAlias=await allowedAlias.json()
    assert.equal(resolvedAlias.id,gitFlow.pullRequest)
    assert.equal(resolvedAlias.url,nativeChangeUrl,'Opaque change destination must persist after restart')
    for(const id of [gitFlow.pullRequest,'00000000-0000-0000-0000-000000000001']) {
      const deniedAlias=await fetch(origin+'/api/changes/'+id,{headers:{authorization:outsiderAuth}})
      assert.equal(deniedAlias.status,404)
      assert.deepEqual(await deniedAlias.json(),{error:'change_not_found'},'Denied and missing aliases must reveal no private context')
    }
    const anonymousAlias=await fetch(origin+'/api/changes/'+gitFlow.pullRequest)
    assert.equal(anonymousAlias.status,401)
    assert.deepEqual(await anonymousAlias.json(),{error:'sign_in_required'})
  }
  const sourceLinks=JSON.parse(await readFile(join(sourceWeb,'test-results-production/source-link-receipt.json'),'utf8'))
  const linkedRepo=after.repositories.find(r=>r.id===sourceLinks.repository_id)
  assert(linkedRepo,'Native source-link repository must persist')
  const linkBase=forgeUrl+'/api/repos/'+linkedRepo.team+'/'+linkedRepo.name+'/pulls/'+sourceLinks.pull_id+'/links'
  const retainedLinks=await (await fetch(linkBase,{headers:{authorization}})).json()
  assert.deepEqual(retainedLinks.links,[sourceLinks.link],'Native link identity and lifecycle generation must persist')
  assert.deepEqual(Object.keys(retainedLinks.links[0]).sort(),['generation','id','state'],'Listings must not expose source locators or titles')
  const retainedContext=await fetch(linkBase+'/'+sourceLinks.link.id+'?connection_generation='+sourceLinks.owner_connection_generation,{headers:{authorization}})
  assert.equal(retainedContext.status,200)
  const sourceContext=await retainedContext.json()
  assert.equal(sourceContext.source_state,'available','Copied release must decrypt the retained viewer credential and read through verified HTTPS')
  assert.equal(sourceContext.title,'Private source specification')
  assert.equal(sourceContext.source_actor.token_id,sourceLinks.source_actors[0])
  assert.equal(sourceContext.locator.document_id,'drafts.private-spec')
  const replayAttach=await fetch(linkBase,{method:'POST',headers:{authorization,'content-type':'application/json','idempotency-key':sourceLinks.original_attach_request.key},body:JSON.stringify(sourceLinks.original_attach_request.body)})
  assert.equal(replayAttach.status,200)
  assert.deepEqual(await replayAttach.json(),sourceLinks.original_receipt,'Original attach receipt must survive even after removal and reactivation')
  assert.deepEqual((await (await fetch(linkBase,{headers:{authorization}})).json()).links,[sourceLinks.link],'Historical receipt must not replace current native link generation')
  for(const id of [sourceLinks.link.id,'00000000-0000-0000-0000-000000000001']){
    const deniedLink=await fetch(linkBase+'/'+id,{headers:{authorization:outsiderAuth}})
    assert.equal(deniedLink.status,404)
    assert.deepEqual(await deniedLink.json(),{error:'source_link_not_found'})
  }
  const returnBase=linkBase+'/'+sourceLinks.link.id+'/return-pointers'
  const retainedReturns=await fetch(returnBase,{headers:{authorization}})
  assert.equal(retainedReturns.status,200)
  const returnValues=(await retainedReturns.json()).operations
  assert.equal(returnValues.length,1)
  assert.equal(returnValues[0].id,sourceLinks.return_operation.id)
  assert.equal(returnValues[0].state,'observed')
  assert.equal(returnValues[0].source_transaction,null,'Observed source presence must not invent a transaction')
  const replayReturn=await fetch(returnBase,{method:'POST',headers:{authorization,'content-type':'application/json','idempotency-key':sourceLinks.return_request.key},body:JSON.stringify(sourceLinks.return_request.body)})
  assert.equal(replayReturn.status,200)
  assert.equal((await replayReturn.json()).id,sourceLinks.return_operation.id)
  const journalStats=await (await fetch(sourceControl+'/journal/stats')).json()
  assert.equal(journalStats.posts.length,1,'Restart/replay must not issue another external mutation')
  const ownedPointers=journalStats.documents['drafts.private-spec'].blocks.filter(b=>b.id==='gitgood-link-'+sourceLinks.link.id)
  assert.equal(ownedPointers.length,1)
  assert.equal(ownedPointers[0].content[0].href,publicUrl+'/changes/'+sourceLinks.pull_id)
  assert.equal(journalStats.documents['drafts.private-spec'].blocks[0].id,'source-intent')
  const criterionEvidence=JSON.parse(await readFile(join(sourceWeb,'test-results-production/criterion-evidence-receipt.json'),'utf8'))
  const gitCompatibility=JSON.parse(await readFile(join(sourceWeb,'test-results-production/git-compatibility-receipt.json'),'utf8'))
  const compatibilityRepo=after.repositories.find(r=>r.name===gitCompatibility.repositories.parent)
  assert(compatibilityRepo,'Compatibility repository must persist')
  const compatibilityPath='/api/repos/'+compatibilityRepo.team+'/'+compatibilityRepo.name
  for(const origin of [forgeUrl,webUrl]){
    const branches=await fetch(origin+compatibilityPath+'/branches',{headers:{authorization}})
    assert.equal(branches.status,200)
    assert((await branches.json()).branches.some(branch=>branch.name==='main'&&branch.sha===gitCompatibility.source_sha),'Exact signed commit must persist')
    const tags=await fetch(origin+compatibilityPath+'/tags',{headers:{authorization}})
    assert.equal(tags.status,200)
    assert((await tags.json()).tags.some(tag=>tag.tag==='signed-v1'&&tag.object===gitCompatibility.tag_sha),'Exact signed tag object must persist')
    const gitlink=await fetch(origin+compatibilityPath+'/snapshot?sha='+gitCompatibility.source_sha+'&path=vendor%2Fchild',{headers:{authorization}})
    assert.equal(gitlink.status,200)
    assert.equal((await gitlink.json()).object,gitCompatibility.child_sha,'Independent child gitlink must persist')
  }
  const evidenceRepo=after.repositories.find(r=>r.id===criterionEvidence.repository_id)
  assert(evidenceRepo,'Native criterion evidence repository must persist')
  const evidencePath='/api/repos/'+evidenceRepo.team+'/'+evidenceRepo.name+'/pulls/'+criterionEvidence.pull_id+'/links/'+criterionEvidence.link.id+'/evidence'
  const evidenceQuery='?connection_generation='+sourceLinks.owner_connection_generation
  for(const origin of [forgeUrl,webUrl]){
    const observed=await fetch(origin+evidencePath+evidenceQuery,{headers:{authorization}})
    assert.equal(observed.status,200)
    const view=await observed.json()
    assert.equal(view.records.length,4,'All original/reassessment results must persist')
    assert.equal(view.criteria[0].state,'unavailable','Restart cannot substitute an older pass for a withdrawn latest artifact')
    assert.equal(view.criteria[1].state,'absent','Task met flags cannot create native evidence')
    const original=view.records.find(record=>record.id===criterionEvidence.first_evidence.id)
    for(const field of ['source_sha','target_sha','source_revision','criterion_sha256','outcome','manifest','artifact','actor_id','recorded_at'])
      assert.deepEqual(original[field],criterionEvidence.first_evidence[field],'Immutable evidence provenance must persist: '+field)
    assert.equal(original.state,'stale')
    const replay=await fetch(origin+evidencePath,{method:'POST',headers:{authorization,'content-type':'application/json','idempotency-key':criterionEvidence.original_request.key},body:JSON.stringify(criterionEvidence.original_request.body)})
    assert.equal(replay.status,200)
    assert.deepEqual(await replay.json(),{id:original.id,recorded:true})
    const artifact=await fetch(origin+evidencePath+'/'+original.id+'/download'+evidenceQuery,{headers:{authorization}})
    assert.equal(artifact.status,200)
    assert.equal(artifact.headers.get('x-content-type-options'),'nosniff')
    assert.equal(artifact.headers.get('x-gitgood-sha256'),criterionEvidence.artifact_sha256)
    assert.equal(createHash('sha256').update(Buffer.from(await artifact.arrayBuffer())).digest('hex'),criterionEvidence.artifact_sha256)
    assert.equal((await fetch(origin+evidencePath+'/'+criterionEvidence.reassessed+'/download'+evidenceQuery,{headers:{authorization}})).status,409)
    assert.equal((await fetch(origin+evidencePath+evidenceQuery,{headers:{authorization:outsiderAuth}})).status,404)
  }
  const released=JSON.parse(await readFile(join(sourceWeb,'test-results-production/release-receipt.json'),'utf8'))
  const releaseRepo=after.repositories.find(r=>r.name===released.repository)
  assert(releaseRepo,'Release repository must persist after restart')
  const releaseBase=forgeUrl+'/api/repos/'+releaseRepo.team+'/'+releaseRepo.name+'/releases/'
  const publishedRelease=await (await fetch(releaseBase+released.published.id,{headers:{authorization}})).json()
  assert.equal(publishedRelease.release.state,'published')
  assert.equal(publishedRelease.release.commit_sha,released.published.commit_sha)
  assert.equal(publishedRelease.release.tag_object,released.published.tag_object)
  assert.deepEqual(publishedRelease.release.changes.commits.map(c=>c.sha),[released.main_sha])
  assert.equal(publishedRelease.events.filter(e=>e.kind==='publish').length,1)
  const releaseAssetPath='/api/repos/'+releaseRepo.team+'/'+releaseRepo.name+'/releases/'+released.published.id+'/assets/'+released.published.asset.id+'/download'
  for(const origin of [forgeUrl,webUrl]) {
    const assetResponse=await fetch(origin+releaseAssetPath,{headers:{authorization}})
    assert.equal(assetResponse.status,200)
    assert.equal(assetResponse.headers.get('cache-control'),'no-store')
    assert.equal(assetResponse.headers.get('x-content-type-options'),'nosniff')
    const bytes=Buffer.from(await assetResponse.arrayBuffer())
    assert.equal(bytes.length,released.published.asset.size)
    assert.equal(createHash('sha256').update(bytes).digest('hex'),released.published.asset.sha256)
  }
  const withdrawnRelease=await (await fetch(releaseBase+released.release_id,{headers:{authorization}})).json()
  assert.equal(withdrawnRelease.release.state,'withdrawn')
  assert.equal(withdrawnRelease.release.commit_sha,released.commit_sha)
  assert(withdrawnRelease.events.some(e=>e.kind==='correct'))
  assert(withdrawnRelease.events.some(e=>e.kind==='withdraw'))
  assert.equal((await fetch(releaseBase+released.release_id+'/assets/'+released.asset.id+'/download',{headers:{authorization}})).status,409)
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
  let offlineRecovery
  if(process.env.GITGOOD_VERIFY_RECOVERY==='true'){
    assert(!windows&&process.env.GITGOOD_VERIFY_CGROUP,'Offline operational proof requires the dedicated Linux cgroup')
    offlineRecovery=await verifyOfflineRecovery({root,env,webEnv,release,installedForge,installedWeb,sourceForge,run,launch,wait,stop,ready,
      stopNative:async()=>{await stop(web);web=null;await stop(backend);backend=null},
      startRestored:async(forgeEnvironment,webEnvironment)=>{backend=startBackend(forgeEnvironment);web=launch(process.execPath,
        [join(installedWeb,'node_modules/srvx/bin/srvx.mjs'),'--prod','-s','dist/client','server.mjs'],webEnvironment,installedWeb,'restored-web')},
      authorization,outsiderAuth,forgeUrl,webUrl,sourceControl,sourceLinks,gitRepo,gitEnv,sshEnv,main,sshBefore,releaseAssetPath,released,
      certificate,tlsKey:key,evidence:join(sourceWeb,'test-results-production')})
  }
  const receipt={candidate:identity.candidate,identity,recordedAt:new Date().toISOString(),installation:root,database,
    runtime:{node:process.version,forge:forgeReady.runtime},actors:['owner','reviewer','reader','outsider'],persistentRepositories:after.repositories.map(r=>r.id),main:main.sha,importOperation:imported.operation_id,
    release:{published:released.published.id,withdrawn:released.release_id,asset_sha256:released.published.asset.sha256},
    discovery:{record:discovery.record,membership_events:discovery.membership_events},
    nativeChange:{id:gitFlow.pullRequest,url:nativeChangeUrl},
    clientAddress:clientAddressProof,offlineRecovery,
    criterionEvidence:{repository:criterionEvidence.repository_id,pull:criterionEvidence.pull_id,link:criterionEvidence.link.id,original:criterionEvidence.first_evidence.id,reassessed:criterionEvidence.reassessed,artifact_sha256:criterionEvidence.artifact_sha256},
    gitCompatibility:{repository:compatibilityRepo.id,source_sha:gitCompatibility.source_sha,tag_sha:gitCompatibility.tag_sha,child_sha:gitCompatibility.child_sha},
    sourceLink:{repository:sourceLinks.repository_id,pull:sourceLinks.pull_id,link:sourceLinks.link,source_actors:sourceLinks.source_actors,return_operation:sourceLinks.return_operation,return_destination:sourceLinks.return_destination},
    checks:['authenticated edge/socket login buckets, twenty-attempt boundary, spoofed fields and direct bypass refusal','source-free copied Elixir release','production-only web dependency install','production SSR and static assets','browser and real HTTPS/SSH/import/release/discovery end-to-end flows','session/database/Git persistence after process restart','import provenance/branches/tags persistence after restart','published release identity/changes/assets persistence and private BFF downloads after restart','withdrawal/correction trace and download refusal after restart','returned HTTPS clone URL','persisted SSH host/account identity and returned SSH clone URL','stable native activity identity/time/link after restart','membership audit persistence and revoked search denial after restart','opaque change destination and denied/missing privacy persist after restart','native link lifecycle/original receipts and encrypted viewer HTTPS source context persist after restart','durable return responsibility, observed outcome, original native request and owned source pointer persist without another write after restart','immutable criterion evidence, reassessment history, exact retry and checksum-protected artifact downloads persist after restart','missing storage rejects forge and web readiness','mismatched component identity rejects readiness'],
    browserTls:'Self-signed fixture bypass in browser only; real Git verifies its explicit CA',
    limitations:['No managed Cloud deployment','No replacement-host restore or storage power-loss proof']}
  receipt.checks.push('Git compatibility signed commit/tag identity and independently authorized child gitlink persist after restart')
  await mkdir(join(sourceWeb,'test-results-production'),{recursive:true})
  await writeFile(join(sourceWeb,'test-results-production/production-receipt.json'),JSON.stringify(receipt,null,2)+'\n')
  console.log('PASS production artifacts, full workflow, persistence and readiness rejection: '+identity.candidate)
}finally {
  await stop(web);await stop(backend);await stop(caddy)
  if(sourceFixture && sourceFixture.exitCode===null){
    sourceFixture.stdin?.end('quit\n')
    await Promise.race([new Promise(resolve=>sourceFixture.once('exit',resolve)),new Promise(resolve=>setTimeout(resolve,3000))])
    await stop(sourceFixture)
  }
}
