import {readFile,writeFile,mkdir,mkdtemp,lstat,readdir,rename,rm,open,realpath} from 'node:fs/promises'
import {createReadStream} from 'node:fs'
import {createHash,randomUUID} from 'node:crypto'
import {hostname} from 'node:os'
import {dirname,join,resolve,sep} from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {packRecovery,unpackRecovery,RecoveryError} from './recovery-bundle.mjs'
import {privateFile,readConfiguration,validateConfiguration,forgeKeys} from './recovery-configuration.mjs'
import {assertLease,assertDatabaseTools,assertDatabaseProfile,fingerprintDatabase,dumpDatabase,restoreDatabase,query} from './recovery-database.mjs'
import {inspectRepositories,rebindRepositories} from './recovery-git.mjs'
import {quarantineInterruptedLocks} from './recovery-locks.mjs'

const check=(condition,code='recovery_configuration_invalid')=>{if(!condition)throw new RecoveryError(code)}
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b)
const sha=async path=>{const hash=createHash('sha256');for await(const chunk of createReadStream(path))hash.update(chunk);return hash.digest('hex')}
const absent=async path=>{try{await lstat(path);return false}catch(error){if(error.code==='ENOENT')return true;throw error}}
async function sync(path){const file=await open(path,'r');try{await file.sync()}finally{await file.close()}}
async function atomic(path,record,{exclusive=false}={}){
  const temporary=path+'.'+randomUUID()+'.partial'
  try{
    await writeFile(temporary,JSON.stringify(record)+'\n',{flag:'wx',mode:0o600});await sync(temporary)
    if(exclusive)check(await absent(path),'destination_exists')
    await rename(temporary,path);await sync(dirname(path))
  }finally{await rm(temporary,{force:true}).catch(()=>{})}
}
async function assertRuntimeStopped(context){
  const marker=join(context.root,'.gitgood-runtime-v1.json')
  await promisify(execFile)(process.env.GITGOOD_PYTHON??'python3',
    ['-I',fileURLToPath(new URL('./process_status.py',import.meta.url)),marker,'require-empty-cgroup'],{timeout:5000,maxBuffer:1024,windowsHide:true})
}
async function claim(context){
  check(process.platform==='linux'&&process.arch==='x64'&&process.version==='v22.23.3','recovery_platform_incompatible')
  check(context&&context.identity?.dirty===false&&/^[a-f0-9]{40}$/.test(context.identity.candidate),'recovery_candidate_invalid')
  check(Number.isInteger(context.owner_pid)&&context.owner_pid>0&&['backup','restore'].includes(context.mode))
  check((await realpath(context.root))===resolve(context.root))
  const marker=join(context.root,'.gitgood-maintenance-v1.json')
  const current=JSON.parse((await privateFile(marker,4096)).toString('utf8'))
  check(current.protocol===1&&current.host.toLowerCase()===hostname().toLowerCase()&&current.mode===context.mode&&
    current.candidate===context.identity.candidate&&equal(current.owners,[context.owner_pid]),'installation_not_quiescent')
  await assertLease(context)
  // A surviving operator child also prevents takeover after the owning BEAM loses its database connection.
  check(current.owner_births&&Object.keys(current.owner_births).join(',')===String(context.owner_pid),'installation_not_quiescent')
  const identity=await promisify(execFile)(process.env.GITGOOD_PYTHON??'python3',
    ['-I',fileURLToPath(new URL('./process_birth.py',import.meta.url)),String(process.pid)],{timeout:5000,maxBuffer:1024,windowsHide:true})
  const born=identity.stdout.trim();check(/^[1-9][0-9]{0,19}$/.test(born),'installation_not_quiescent')
  await atomic(marker,{...current,owners:[context.owner_pid,process.pid],owner_births:{...current.owner_births,[process.pid]:born}})
  await assertDatabaseTools(context.postgres)
  if(context.mode==='backup')await assertRuntimeStopped(context)
}
async function backup(context,options,key){
  check(equal(context.migrations,context.identity.migrations),'recovery_schema_incompatible')
  const configuration=resolve(options.configuration),config=await readConfiguration(configuration)
  check(resolve(config.forge.GITGOOD_STORAGE)===resolve(context.root)&&resolve(config.forge.GITGOOD_SSH_HOST_KEY_DIRECTORY)===resolve(options.ssh))
  for(const name of forgeKeys)check(config.forge[name]===process.env[name],'configuration_runtime_mismatch')
  check(await absent(join(configuration,'recovery.json')),'configuration_invalid')
  const scratch=await mkdtemp(join(dirname(resolve(options.destination)),'.gitgood-backup-'))
  try{
    const configRoot=join(scratch,'configuration');await mkdir(configRoot,{mode:0o700})
    for(const name of await readdir(configuration)){
      const value=await privateFile(join(configuration,name))
      check(['installation.json',...Object.values(config.edge)].includes(name),'configuration_invalid')
      await writeFile(join(configRoot,name),value,{flag:'wx',mode:0o600})
    }
    const recovery_point=new Date().toISOString()
    const rows=JSON.parse(await query("SELECT coalesce(json_agg(json_build_object('storage_key',storage_key::text,'status',status) ORDER BY storage_key),'[]'::json) FROM repositories"))
    // Validate owned stores first. Only complete runtime exclusion permits lock quarantine.
    await inspectRepositories(context.root,rows,{allowInterruptedLocks:true})
    const interrupted_git_locks=await quarantineInterruptedLocks(context.root,rows,async()=>{
      await assertLease(context)
      await assertRuntimeStopped(context)
    })
    const repositories=await inspectRepositories(context.root,rows)
    const database=await fingerprintDatabase()
    const descriptor={protocol:1,installation:config.installation,database,repositories,interrupted_git_locks}
    await writeFile(join(configRoot,'recovery.json'),JSON.stringify(descriptor)+'\n',{flag:'wx',mode:0o600})
    const dump=join(scratch,'database.dump');await dumpDatabase(dump)
    check(equal(database,await fingerprintDatabase()),'snapshot_changed')
    const packed=await packRecovery({destination:options.destination,key,metadata:{candidate:context.identity.candidate,postgres:context.postgres,
      migrations:context.migrations,recovery_point},roots:{git:context.root,ssh:resolve(options.ssh),configuration:configRoot,'database.dump':dump},
      beforePublish:async()=>{
        await assertLease(context)
        await assertRuntimeStopped(context)
        check(equal(repositories,await inspectRepositories(context.root,rows)),'snapshot_changed')
        check(equal(database,await fingerprintDatabase()),'snapshot_changed')
      }})
    return {...packed,interrupted_git_locks}
  }finally{await rm(scratch,{recursive:true,force:true})}
}
async function copyExact(source,target){
  const stat=await lstat(source)
  check(stat.isDirectory()||stat.isFile(),'bundle_invalid')
  if(stat.isDirectory()){
    if(await absent(target)){await mkdir(target,{mode:0o700});await sync(dirname(target))}
    else check((await lstat(target)).isDirectory()&&(await realpath(target))===resolve(target),'destination_exists')
    const names=await readdir(source),existing=await readdir(target)
    check(existing.every(name=>names.includes(name)||['.gitgood-maintenance-v1.json','.gitgood-restore-incomplete-v1.json'].includes(name)&&target===process.env.GITGOOD_STORAGE),'destination_exists')
    for(const name of names)await copyExact(join(source,name),join(target,name))
    await sync(target)
  }else{
    if(await absent(target)){
      await promisify(execFile)(process.env.GITGOOD_PYTHON??'python3',
        ['-I',fileURLToPath(new URL('./publish_file.py',import.meta.url)),source,target],{timeout:5000,maxBuffer:1024,windowsHide:true})
    }else{const other=await lstat(target);check(other.isFile()&&other.nlink===1&&await sha(target)===await sha(source),'destination_exists')}
  }
}
async function restore(context,options,key){
  const installation=resolve(options.installation)
  check(resolve(context.root)===join(installation,'git'),'recovery_target_invalid')
  check((await realpath(installation))===installation)
  const verified=join(installation,'.verified-'+randomUUID())
  let unpacked
  try{
    unpacked=await unpackRecovery({source:options.source,key,target:verified,expectedCandidate:context.identity.candidate,expectedPostgres:context.postgres})
    check(equal(unpacked.manifest.migrations,context.identity.migrations),'recovery_schema_incompatible')
    const configuration=join(verified,'configuration'),config=await readConfiguration(configuration)
    const descriptor=JSON.parse((await privateFile(join(configuration,'recovery.json'))).toString('utf8'))
    check(descriptor.protocol===1&&descriptor.installation===config.installation&&descriptor.database&&Array.isArray(descriptor.repositories),'bundle_invalid')
    // Database import cannot change encoding, locale provider or text semantics.
    // Refuse before creating an interrupted-restore gate or installing any store.
    await assertDatabaseProfile(descriptor.database.profile)
    const repositories=await inspectRepositories(join(verified,'git'),descriptor.repositories.map(({storage_key,status})=>({storage_key,status})))
    check(equal(repositories,descriptor.repositories),'bundle_invalid')
    const binding={protocol:1,ciphertext_sha256:unpacked.ciphertext_sha256,candidate:context.identity.candidate,
      installation:config.installation,database:{host:process.env.PGHOST,port:process.env.PGPORT,name:process.env.PGDATABASE,user:process.env.PGUSER},
      target:installation}
    const gate=join(context.root,'.gitgood-restore-incomplete-v1.json')
    if(!await absent(gate))check(equal(JSON.parse((await privateFile(gate)).toString('utf8')),binding),'restore_retry_mismatch')
    else{
      check(context.existing_tables?.length===0,'database_destination_not_empty')
      check(equal((await readdir(context.root)).sort(),['.gitgood-maintenance-v1.json']),'destination_exists')
      for(const name of ['ssh','configuration'])check(await absent(join(installation,name)),'destination_exists')
      await atomic(gate,binding,{exclusive:true})
    }
    await assertLease(context)
    const current=await fingerprintDatabase()
    if(!equal(current,descriptor.database)){
      check(JSON.parse(await query("SELECT coalesce(json_agg(tablename),'[]'::json) FROM pg_tables WHERE schemaname='public'")).length===0,'database_destination_not_empty')
      await restoreDatabase(join(verified,'database.dump'))
      check(equal(await fingerprintDatabase(),descriptor.database),'database_restore_mismatch')
    }
    await rebindRepositories(join(verified,'git'),context.root,descriptor.repositories)
    config.forge.DATABASE_URL=process.env.DATABASE_URL
    config.forge.GITGOOD_STORAGE=context.root
    config.forge.GITGOOD_SSH_HOST_KEY_DIRECTORY=join(installation,'ssh')
    if(config.forge.GITGOOD_BARKPARK_CA)config.forge.GITGOOD_BARKPARK_CA=join(installation,'configuration/source-ca.pem')
    validateConfiguration(config)
    await writeFile(join(configuration,'installation.json'),JSON.stringify(config)+'\n',{mode:0o600})
    for(const name of ['git','ssh','configuration'])await copyExact(join(verified,name),join(installation,name))
    check(equal(await inspectRepositories(context.root,descriptor.repositories.map(({storage_key,status})=>({storage_key,status}))),descriptor.repositories),'git_restore_mismatch')
    await assertLease(context)
    return {candidate:context.identity.candidate,ciphertext_sha256:unpacked.ciphertext_sha256,recovery_point:unpacked.manifest.recovery_point,
      installation:config.installation,status:'awaiting_native_key_verification'}
  }finally{if(unpacked)await rm(verified,{recursive:true,force:true})}
}
export async function runRecovery(context,options){
  check(options&&['backup','restore'].includes(options.mode)&&context.mode===options.mode)
  const key=await privateFile(options.key,32)
  check(key.length===32,'key_invalid')
  try{await claim(context);return options.mode==='backup'?await backup(context,options,key):await restore(context,options,key)}
  finally{key.fill(0)}
}
if(resolve(process.argv[1]??'')===fileURLToPath(import.meta.url)){
  try{
    const result=await runRecovery(JSON.parse(process.env.GITGOOD_RECOVERY_CONTEXT??''),{
      mode:process.argv[2],key:process.env.GITGOOD_RECOVERY_KEY_FILE,destination:process.env.GITGOOD_RECOVERY_BUNDLE,
      source:process.env.GITGOOD_RECOVERY_BUNDLE,configuration:process.env.GITGOOD_RECOVERY_CONFIGURATION,
      ssh:process.env.GITGOOD_SSH_HOST_KEY_DIRECTORY,installation:process.env.GITGOOD_RECOVERY_INSTALLATION})
    process.stdout.write(JSON.stringify(result)+'\n')
  }catch(error){process.stdout.write(JSON.stringify({error:error instanceof RecoveryError?error.code:'recovery_failed'})+'\n');process.exitCode=1}
}
