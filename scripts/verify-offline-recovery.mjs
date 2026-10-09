import assert from 'node:assert/strict'
import {mkdir,readFile,writeFile,lstat} from 'node:fs/promises'
import {join} from 'node:path'
import {randomBytes,createHash} from 'node:crypto'
import {provisionConfiguration,readConfiguration} from '../apps/forge/priv/operations/recovery-configuration.mjs'

export async function verifyOfflineRecovery(options){
  const {root,env,webEnv,release,installedForge,installedWeb,run,launch,wait,stop,ready,stopNative,startRestored,
    authorization,outsiderAuth,forgeUrl,webUrl,sourceControl,sourceLinks,gitRepo,gitEnv,sshEnv,main,sshBefore,
    releaseAssetPath,released,certificate,tlsKey,pendingEvidence}=options
  assert.equal(process.platform,'linux')
  const started=performance.now(),targetRtoMs=15*60*1000
  const configuration=join(root,'operator-configuration'),keyFile=join(root,'recovery-key.bin'),bundle=join(root,'recovery.ggbackup')
  await provisionConfiguration({directory:configuration,forge:env,web:webEnv,certificate,tlsKey,sourceCa:env.GITGOOD_BARKPARK_CA})
  await writeFile(keyFile,randomBytes(32),{flag:'wx',mode:0o600})
  const backupEnv={...env,GITGOOD_RECOVERY_KEY_FILE:keyFile,GITGOOD_RECOVERY_CONFIGURATION:configuration,GITGOOD_RECOVERY_BUNDLE:bundle}
  await wait(launch(release,['eval','Gitgood.Release.backup()'],backupEnv,installedForge,'backup-running-refusal'),'backup-running-refusal',[1])
  await assert.rejects(lstat(bundle))
  // Preserve a real sealed request whose upstream write happened but whose reply was lost.
  const base=forgeUrl+'/api/repos/team/'+sourceLinks.repository+'/pulls/'+sourceLinks.pull_id+'/links'
  const attached=await fetch(base,{method:'POST',headers:{authorization,'content-type':'application/json','idempotency-key':'recovery-pending-link'},
    body:JSON.stringify({type:'paper',document_id:'drafts.recovery-pending',connection_generation:sourceLinks.owner_connection_generation})})
  assert.equal(attached.status,200)
  const link=await attached.json(),returnBase=base+'/'+link.id+'/return-pointers'
  const control=async(path,body)=>{
    const response=await fetch(sourceControl+path,{method:'POST',headers:{authorization:'Bearer synthetic-fixture-control','content-type':'application/json'},body:JSON.stringify(body)})
    assert.equal(response.status,200)
  }
  await control('/control/journal-state',{lost_reply:true,outage_after_write:true})
  const returnResponse=await fetch(returnBase,{method:'POST',headers:{authorization,'content-type':'application/json','idempotency-key':'recovery-unknown-return'},
    body:JSON.stringify({generation:link.generation,connection_generation:sourceLinks.owner_connection_generation})})
  assert.equal(returnResponse.status,200)
  const returned=await returnResponse.json()
  let unknown
  const unknownDeadline=Date.now()+20000
  while(Date.now()<unknownDeadline){
    unknown=(await (await fetch(returnBase,{headers:{authorization}})).json()).operations.find(operation=>operation.id===returned.id)
    if(unknown?.state==='unknown')break
    await new Promise(resolve=>setTimeout(resolve,100))
  }
  assert.equal(unknown?.state,'unknown');assert.equal(unknown.source_transaction,null)
  const statsBefore=await (await fetch(sourceControl+'/journal/stats')).json()
  assert(Number.isSafeInteger(gitRepo.id)&&gitRepo.id>0)
  const sourceDatabase=new URL(env.DATABASE_URL)
  const pgEnv={...process.env,PGHOST:sourceDatabase.hostname,PGPORT:sourceDatabase.port,PGUSER:decodeURIComponent(sourceDatabase.username),
    PGPASSWORD:decodeURIComponent(sourceDatabase.password),PGDATABASE:sourceDatabase.pathname.slice(1)}
  await run(process.env.GITGOOD_PSQL??'psql',['--no-psqlrc','--tuples-only','--no-align','--command',
    'SELECT storage_key::text FROM repositories WHERE id='+gitRepo.id],pgEnv,root,'interrupted-storage-key')
  const storageKey=(await readFile(join(root,'logs/interrupted-storage-key.log'),'utf8')).trim()
  assert(/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(storageKey))
  await stopNative()
  const group=process.env.GITGOOD_VERIFY_CGROUP,prepared=join(root,'git-ref-prepared'),holder=join(root,'hold-git-ref.mjs')
  const interruptedRef='refs/heads/recovery-interrupted',bare=join(env.GITGOOD_STORAGE,storageKey+'.git')
  assert(/^[a-f0-9]{40}$/.test(main.sha))
  const lock=join(bare,interruptedRef+'.lock')
  await writeFile(holder,`import {spawn} from 'node:child_process';import {writeFile} from 'node:fs/promises';
const child=spawn(process.env.GITGOOD_GIT,['--git-dir',process.argv[2],'update-ref','--stdin'],{stdio:['pipe','pipe','pipe']});
child.stderr.resume();let output='',marked=false;
child.stdout.on('data',async bytes=>{output+=bytes.toString();if(!marked&&output.includes('prepare: ok')){marked=true;await writeFile(process.argv[4],'prepared')}});
child.stdin.write('start\\ncreate refs/heads/recovery-interrupted '+process.argv[3]+'\\nprepare\\n');
`,{flag:'wx',mode:0o600})
  let held,interruptedLock
  try{
    held=launch(process.env.GITGOOD_PYTHON,['-I',join(options.sourceForge,'priv/operations/runtime_cgroup.py'),group,
      process.execPath,holder,bare,main.sha,prepared],{PATH:process.env.PATH,GITGOOD_GIT:process.env.GITGOOD_GIT??'git',
        GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',HOME:'/nonexistent'},root,'held-ref-transaction')
    held.runtimeCgroup=group
    const deadline=Date.now()+10000
    while(true){try{await lstat(prepared);break}catch{}assert(Date.now()<deadline);await new Promise(resolve=>setTimeout(resolve,25))}
    interruptedLock=await readFile(lock)
    await wait(launch(release,['eval','Gitgood.Release.backup()'],backupEnv,installedForge,'backup-held-writer-refusal'),'backup-held-writer-refusal',[1])
    assert((await readFile(lock)).equals(interruptedLock));await assert.rejects(lstat(bundle))
  }finally{if(held)await stop(held)}
  assert((await readFile(lock)).equals(interruptedLock),'Kernel termination must leave the real unpublished Git lock for recovery')
  const pausedAt=performance.now()
  await run(release,['eval','Gitgood.Release.backup()'],backupEnv,installedForge,'backup')
  const backupLog=await readFile(join(root,'logs/backup.log'),'utf8')
  const backupReceipt=JSON.parse(backupLog.trim().split('\n').find(line=>line.startsWith('{')))
  assert.equal(backupReceipt.status,'complete')
  const recoveredLock=backupReceipt.interrupted_git_locks.find(value=>value.storage_key===storageKey&&value.path===interruptedRef+'.lock')
  assert(recoveredLock&&recoveredLock.sha256===createHash('sha256').update(interruptedLock).digest('hex'))
  assert((await readFile(join(env.GITGOOD_STORAGE,recoveredLock.quarantine))).equals(interruptedLock))
  await assert.rejects(lstat(lock))
  assert.equal(createHash('sha256').update(await readFile(bundle)).digest('hex'),backupReceipt.ciphertext_sha256)
  const wrongLocaleDatabase='gitgood_wrong_locale_'+randomBytes(4).toString('hex')
  const wrongLocaleInstallation=join(root,'wrong-locale');await mkdir(wrongLocaleInstallation,{mode:0o700})
  await run(process.env.GITGOOD_CREATEDB??'createdb',['--template=template0','--encoding=UTF8','--locale=C',
    '--locale-provider=libc',wrongLocaleDatabase],process.env,root,'wrong-locale-database-create')
  const wrongLocaleUrl=new URL(env.DATABASE_URL);wrongLocaleUrl.pathname='/'+wrongLocaleDatabase
  const wrongLocaleEnv={...env,DATABASE_URL:wrongLocaleUrl.toString(),GITGOOD_STORAGE:join(wrongLocaleInstallation,'git'),
    GITGOOD_RECOVERY_KEY_FILE:keyFile,GITGOOD_RECOVERY_BUNDLE:bundle,GITGOOD_RECOVERY_INSTALLATION:wrongLocaleInstallation}
  await wait(launch(release,['eval','Gitgood.Release.restore()'],wrongLocaleEnv,installedForge,'wrong-locale-refusal'),'wrong-locale-refusal',[1])
  for(const path of ['configuration','ssh','git/.gitgood-restore-incomplete-v1.json'])
    await assert.rejects(lstat(join(wrongLocaleInstallation,path)))
  await run(process.env.GITGOOD_PSQL??'psql',['--no-psqlrc','--tuples-only','--no-align','--command',
    "SELECT count(*) FROM pg_tables WHERE schemaname='public'"],{...pgEnv,PGDATABASE:wrongLocaleDatabase},root,'wrong-locale-table-count')
  assert.equal((await readFile(join(root,'logs/wrong-locale-table-count.log'),'utf8')).trim(),'0')
  const installation=join(root,'recovered');await mkdir(installation,{mode:0o700})
  const database='gitgood_restored_'+randomBytes(4).toString('hex')
  await run(process.env.GITGOOD_CREATEDB??'createdb',['-h',process.env.PGHOST??'127.0.0.1','-p',process.env.PGPORT??'55432','-U',process.env.PGUSER??'gitgood',database],process.env,root,'restore-database-create')
  const targetUrl=new URL(env.DATABASE_URL);targetUrl.pathname='/'+database
  const restoreEnv={...env,DATABASE_URL:targetUrl.toString(),GITGOOD_STORAGE:join(installation,'git'),
    GITGOOD_CONNECTION_KEY:randomBytes(32).toString('base64'),GITGOOD_RECOVERY_KEY_FILE:keyFile,GITGOOD_RECOVERY_BUNDLE:bundle,GITGOOD_RECOVERY_INSTALLATION:installation}
  await run(release,['eval','Gitgood.Release.restore()'],restoreEnv,installedForge,'restore')
  await assert.rejects(lstat(join(installation,'git/.gitgood-restore-incomplete-v1.json')))
  const recovered=await readConfiguration(join(installation,'configuration'))
  for(const key of ['SECRET_KEY_BASE','GITGOOD_PROXY_KEY','GITGOOD_CONNECTION_KEY','GITGOOD_PUBLIC_URL','GITGOOD_WEB_ORIGIN'])
    assert(recovered.forge[key]===env[key],'Recovered custody/origin must equal the actual original installation')
  assert((await readFile(join(installation,'ssh/ssh_host_ed25519_key'))).equals(await readFile(join(env.GITGOOD_SSH_HOST_KEY_DIRECTORY,'ssh_host_ed25519_key'))),'Recovered SSH private identity must match')
  assert((await readFile(join(installation,'git',recoveredLock.quarantine))).equals(interruptedLock),'Interrupted lock bytes must survive in private recovery custody')
  await startRestored({...process.env,...recovered.forge,PHX_SERVER:'true'},{...process.env,...recovered.web})
  await ready(forgeUrl);await ready(webUrl)
  const repos=await (await fetch(forgeUrl+'/api/repos',{headers:{authorization}})).json()
  assert(repos.repositories.some(repository=>repository.id===gitRepo.id),'Session and private repositories must survive recovery')
  const alias='/api/changes/'+sourceLinks.pull_id
  assert.equal((await fetch(forgeUrl+alias,{headers:{authorization}})).status,200)
  for(const origin of [forgeUrl,webUrl]){
    const denied=await fetch(origin+alias,{headers:{authorization:outsiderAuth}})
    assert.equal(denied.status,404);assert.deepEqual(await denied.json(),{error:'change_not_found'})
    const asset=await fetch(origin+releaseAssetPath,{headers:{authorization}})
    assert.equal(asset.status,200)
    assert.equal(createHash('sha256').update(Buffer.from(await asset.arrayBuffer())).digest('hex'),released.published.asset.sha256)
    assert.equal((await fetch(origin+releaseAssetPath,{headers:{authorization:outsiderAuth}})).status,404)
  }
  const retained=(await (await fetch(returnBase,{headers:{authorization}})).json()).operations.find(operation=>operation.id===returned.id)
  assert.equal(retained.state,'unknown');assert.equal(retained.source_transaction,null)
  await control('/control/journal-state',{lost_reply:false,outage_after_write:false})
  await control('/control/document-state',{status:200})
  const observeDeadline=Date.now()+20000
  let observed
  while(Date.now()<observeDeadline){
    observed=(await (await fetch(returnBase,{headers:{authorization}})).json()).operations.find(operation=>operation.id===returned.id)
    if(observed?.state==='observed')break
    await new Promise(resolve=>setTimeout(resolve,100))
  }
  assert.equal(observed?.state,'observed');assert.equal(observed.source_transaction,null)
  const context=await fetch(base+'/'+link.id+'?connection_generation='+sourceLinks.owner_connection_generation,{headers:{authorization}})
  assert.equal(context.status,200);assert.equal((await context.json()).source_state,'available')
  const statsAfter=await (await fetch(sourceControl+'/journal/stats')).json()
  assert.equal(statsAfter.posts.length,statsBefore.posts.length,'Restoration must not duplicate the uncertain external mutation')
  for(const origin of [forgeUrl,webUrl]){
    const unresolved=await fetch(origin+pendingEvidence.path+'/intents',{headers:{authorization}})
    assert.equal(unresolved.status,200)
    assert.deepEqual(await unresolved.json(),{intents:[pendingEvidence.intent]},'Encrypted unapplied evidence responsibility survives complete restore')
    const retried=await fetch(origin+pendingEvidence.path+'/intents/'+pendingEvidence.intent.id+'/retry',{
      method:'POST',headers:{authorization,'content-type':'application/json'},body:'{}'})
    assert.equal(retried.status,409)
    assert(['evidence_requirement_changed','connection_changed','evidence_revision_changed','source_link_changed'].includes((await retried.json()).error))
  }
  const retirement=await fetch(forgeUrl+pendingEvidence.path+'/intents/'+pendingEvidence.intent.id+'/retire',{
    method:'POST',headers:{authorization,'content-type':'application/json'},body:'{}'})
  assert.equal(retirement.status,200)
  assert.deepEqual(await retirement.json(),{id:pendingEvidence.intent.id,intent_id:pendingEvidence.intent.id,retired:true})
  assert.equal(statsAfter.documents['drafts.recovery-pending'].blocks.filter(block=>block.id==='gitgood-link-'+link.id).length,1)
  assert.deepEqual((await (await fetch(forgeUrl+'/api/ssh-keys',{headers:{authorization}})).json()).transport,sshBefore.transport)
  await run(process.env.GITGOOD_GIT??'git',['ls-remote',gitRepo.clone_url,'refs/heads/main'],gitEnv,root,'restored-https-read')
  await run(process.env.GITGOOD_GIT??'git',['ls-remote',gitRepo.ssh_clone_url,'refs/heads/main'],sshEnv,root,'restored-ssh-read')
  for(const log of ['restored-https-read','restored-ssh-read'])assert((await readFile(join(root,'logs/'+log+'.log'),'utf8')).includes(main.sha+'\trefs/heads/main'))
  const clone=join(root,'restored-client')
  await run(process.env.GITGOOD_GIT??'git',['clone','--template=',gitRepo.clone_url,clone],gitEnv,root,'restored-clone')
  await writeFile(join(clone,'recovery-proof.txt'),'A new authorized write after offline restoration.\n')
  await run(process.env.GITGOOD_GIT??'git',['add','--','recovery-proof.txt'],gitEnv,clone,'restored-add')
  await run(process.env.GITGOOD_GIT??'git',['-c','user.name=Recovery fixture','-c','user.email=recovery@example.invalid','commit','-m','Recovery functional proof'],gitEnv,clone,'restored-commit')
  await run(process.env.GITGOOD_GIT??'git',['push','origin','HEAD:'+interruptedRef],gitEnv,clone,'restored-push')
  const branches=await (await fetch(forgeUrl+'/api/repos/'+gitRepo.team+'/'+gitRepo.name+'/branches',{headers:{authorization}})).json()
  assert(branches.branches.some(branch=>branch.name==='recovery-interrupted'))
  const recoveryMs=performance.now()-pausedAt
  assert(recoveryMs<targetRtoMs)
  const receipt={candidate:backupReceipt.candidate,recorded_at:new Date().toISOString(),profile:'same-host isolated database and installation, supporting proof',
    backup:{...backupReceipt},restored_database:database,installation:recovered.installation,
    targets:{rpo:'zero loss relative to the quiesced durable point',rto_ms:targetRtoMs},observed:{recovery_ms:recoveryMs,total_ms:performance.now()-started},
    checks:['running installation refuses backup','kernel cgroup empty before snapshot','exact database rows/sequences/schema and locale fingerprint',
      'real different-locale target refused before gate, database import or store installation',
      'real prepared Git transaction excluded while alive; killed lock quarantined byte-for-byte without publishing its ref',
      'restored session, proxy and source key custody','SSH host identity retained','unknown sealed request retained and observed without another write',
      'private collaboration and asset access retained','outsider denied','authorized HTTPS and SSH refs, clone and new push with rebound hooks'],
    limitations:['Same host; replacement-host exercise still required','No storage power-loss durability proof','No managed Cloud lifecycle']}
  await writeFile(join(options.evidence,'offline-recovery-receipt.json'),JSON.stringify(receipt,null,2)+'\n')
  return receipt
}
