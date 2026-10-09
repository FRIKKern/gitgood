import {createReadStream} from 'node:fs'
import {lstat,realpath,mkdtemp,rm} from 'node:fs/promises'
import {createHash} from 'node:crypto'
import {join,resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import {inspectInstallationExport} from './installation-export.mjs'
import {RecoveryError,unpackRecovery,databaseFingerprint} from './recovery-bundle.mjs'
import {privateFile,readConfiguration} from './recovery-configuration.mjs'
import {assertDatabaseTools,assertDatabaseProfile,fingerprintDatabase,restoreDatabase,query} from './recovery-database.mjs'

const check=value=>{if(!value)throw new RecoveryError('retirement_restore_data_invalid')}
const digest=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value)
const uuid=value=>typeof value==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value)
const sha=async path=>{const hash=createHash('sha256');for await(const bytes of createReadStream(path))hash.update(bytes);return hash.digest('hex')}
const TARGET_KEYS='address,cluster,database,database_oid,encoding,owner_oid,port,role_oid,version'
async function identity(){
  return JSON.parse(await query(`SELECT json_build_object(
    'cluster',(SELECT system_identifier::text FROM pg_control_system()),
    'database',current_database(),'database_oid',d.oid::bigint,'owner_oid',d.datdba::bigint,
    'role_oid',r.oid::bigint,'encoding',pg_encoding_to_char(d.encoding),
    'version',current_setting('server_version'),'address',host(inet_server_addr()),'port',inet_server_port())
    FROM pg_database d,pg_roles r WHERE d.datname=current_database() AND r.rolname=current_user`))
}
async function noOtherClients(){
  check(await query("SELECT NOT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid())")==='t')
}
async function empty(){
  check(await query(`SELECT NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema') AND nspname NOT LIKE 'pg_%')
    AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public')
    AND NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public')
    AND NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public')`)==='t')
}

export async function verifyRetirementRestoreData(request){
  check(process.platform==='linux'&&process.arch==='x64'&&process.version==='v22.23.3')
  check(request&&Object.keys(request).sort().join(',')==='candidate,ciphertext_sha256,installation,key_path,operation,phase,protocol,scratch_directory,source,target')
  check(request.protocol===1&&['restore','observe'].includes(request.phase)&&uuid(request.operation)&&uuid(request.installation)&&
    typeof request.candidate==='string'&&/^[a-f0-9]{40}$/.test(request.candidate)&&digest(request.ciphertext_sha256))
  const target=request.target
  check(target&&Object.keys(target).sort().join(',')===TARGET_KEYS)
  check(target.database==='gitgood_retirement_restore_'+request.operation.replaceAll('-','')&&process.env.PGDATABASE===target.database)
  check(typeof target.cluster==='string'&&/^[0-9]+$/.test(target.cluster)&&target.version==='18.4'&&target.encoding==='UTF8'&&target.address==='127.0.0.1')
  for(const field of ['database_oid','owner_oid','role_oid','port'])check(Number.isSafeInteger(target[field])&&target[field]>0)
  check(target.owner_oid===target.role_oid)
  for(const path of [request.source,request.key_path,request.scratch_directory])check(typeof path==='string'&&path.length<=4096&&resolve(path)===path&&await realpath(path)===path)
  const parent=await lstat(request.scratch_directory)
  check(parent.isDirectory()&&parent.uid===process.getuid()&&(parent.mode&0o077)===0)
  check(await sha(request.source)===request.ciphertext_sha256)
  const archive=await inspectInstallationExport({source:request.source,keyPath:request.key_path,scratchDirectory:request.scratch_directory,
    expectedCandidate:request.candidate,expectedInstallation:request.installation})
  check(archive.ciphertext_sha256===request.ciphertext_sha256)
  await assertDatabaseTools('18.4')
  const same=value=>Object.keys(value).sort().join(',')===TARGET_KEYS&&Object.keys(target).every(key=>value[key]===target[key])
  check(same(await identity()))
  await noOtherClients()
  const key=await privateFile(request.key_path,32);check(key.length===32)
  const scratch=await mkdtemp(join(request.scratch_directory,'.gitgood-retirement-restore-data-'))
  try{
    const unpacked=await unpackRecovery({source:request.source,key,target:join(scratch,'verified'),expectedCandidate:request.candidate})
    check(unpacked.ciphertext_sha256===request.ciphertext_sha256)
    const configuration=join(unpacked.verified_directory,'configuration'),config=await readConfiguration(configuration)
    check(config.installation===request.installation)
    const original=new URL(config.forge.DATABASE_URL)
    check(['postgres:','postgresql:'].includes(original.protocol)&&['localhost','127.0.0.1'].includes(original.hostname)&&original.port&&!original.search&&!original.hash)
    check(decodeURIComponent(original.pathname.slice(1))!==target.database&&process.env.PGHOST==='127.0.0.1'&&process.env.PGPORT===original.port&&
      process.env.PGUSER===decodeURIComponent(original.username)&&process.env.PGPASSWORD===decodeURIComponent(original.password))
    const descriptor=JSON.parse((await privateFile(join(configuration,'recovery.json'),16777216)).toString('utf8'))
    check(descriptor.protocol===1&&descriptor.installation===request.installation&&databaseFingerprint(descriptor.database)===archive.database_fingerprint)
    await assertDatabaseProfile(descriptor.database.profile)
    check(same(await identity()))
    await noOtherClients()
    if(request.phase==='restore'){
      await empty()
      // The independently named target is allocated by the owner, never by this
      // helper. A failed/partial target is retained; there is no DROP or cleanup.
      await restoreDatabase(join(unpacked.verified_directory,'database.dump'))
    }
    check(databaseFingerprint(await fingerprintDatabase())===archive.database_fingerprint)
    await noOtherClients()
    check(same(await identity())&&await sha(request.source)===request.ciphertext_sha256)
    return {protocol:1,purpose:'retirement_restore_data',status:'verified',operation:request.operation,installation:request.installation,
      candidate:request.candidate,ciphertext_sha256:request.ciphertext_sha256,recovery_point:archive.recovery_point,
      resource_fingerprints:archive.resource_fingerprints,database_fingerprint:archive.database_fingerprint,
      target_database:target,phase:request.phase,
      checks:['authenticated archive and exact Git refs pass inspection','independent target database identity and source separation match','restored database schema, rows, sequences and locale match the archive','archive bytes and original target identity remain unchanged'],
      limitations:['This proves recovered contents; application startup and authenticated functional probes remain separate.','The native controller must retain writer custody and account for the target and any interrupted private scratch.','No original installation, target database or provider resource is removed.']}
  }finally{
    key.fill(0)
    check(await realpath(scratch)===scratch&&scratch.startsWith(request.scratch_directory+'/.gitgood-retirement-restore-data-'))
    await rm(scratch,{recursive:true,force:true})
  }
}

if(process.argv[1]===fileURLToPath(import.meta.url)){
  try{
    check(process.argv.length===4&&digest(process.argv[3]))
    const info=await lstat(process.argv[2]);check(info.uid===process.getuid())
    const raw=await privateFile(process.argv[2],32768)
    check(createHash('sha256').update(raw).digest('hex')===process.argv[3])
    console.log(JSON.stringify(await verifyRetirementRestoreData(JSON.parse(raw.toString('utf8')))))
  }catch(error){console.error(JSON.stringify({status:'refused',code:error instanceof RecoveryError?error.code:'retirement_restore_data_invalid'}));process.exitCode=1}
}
