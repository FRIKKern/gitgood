import {createReadStream} from 'node:fs'
import {lstat,realpath} from 'node:fs/promises'
import {createHash} from 'node:crypto'
import {dirname,resolve,sep} from 'node:path'
import {fileURLToPath} from 'node:url'
import {inspectInstallationExport} from './installation-export.mjs'
import {RecoveryError,snapshotInstallationRoots,databaseFingerprint} from './recovery-bundle.mjs'
import {readConfiguration,privateFile} from './recovery-configuration.mjs'
import {assertDatabaseTools,fingerprintDatabase,query} from './recovery-database.mjs'

const check=condition=>{if(!condition)throw new RecoveryError('retirement_snapshot_invalid')}
const sha=async path=>{const hash=createHash('sha256');for await(const bytes of createReadStream(path))hash.update(bytes);return hash.digest('hex')}
const digest=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value)
const uuid=value=>typeof value==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value)
async function noOtherClients(){
  check(await query("SELECT NOT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid())")==='t')
}

export async function observeRetirementSnapshot(request){
  check(process.platform==='linux'&&process.arch==='x64'&&process.version==='v22.23.3')
  check(request&&Object.keys(request).sort().join(',')==='candidate,ciphertext_sha256,installation,key_path,protocol,roots,source')
  check(request.protocol===1&&typeof request.candidate==='string'&&/^[a-f0-9]{40}$/.test(request.candidate)&&uuid(request.installation)&&digest(request.ciphertext_sha256))
  check(request.roots&&Object.keys(request.roots).sort().join(',')==='configuration,git,ssh')
  for(const path of [request.source,request.key_path,...Object.values(request.roots)])check(typeof path==='string'&&path.length<=4096&&resolve(path)===path&&await realpath(path)===path)
  for(const path of [request.source,request.key_path])check(!Object.values(request.roots).some(root=>path===root||path.startsWith(root+sep)))
  const config=await readConfiguration(request.roots.configuration)
  check(config.installation===request.installation&&resolve(config.forge.GITGOOD_STORAGE)===request.roots.git&&resolve(config.forge.GITGOOD_SSH_HOST_KEY_DIRECTORY)===request.roots.ssh)
  const database=new URL(config.forge.DATABASE_URL)
  check(['postgres:','postgresql:'].includes(database.protocol)&&['localhost','127.0.0.1'].includes(database.hostname)&&database.port&& !database.search&&!database.hash)
  check(process.env.PGHOST==='127.0.0.1'&&process.env.PGPORT===database.port&&process.env.PGDATABASE===decodeURIComponent(database.pathname.slice(1))&&
    process.env.PGUSER===decodeURIComponent(database.username)&&process.env.PGPASSWORD===decodeURIComponent(database.password))
  await assertDatabaseTools('18.4')
  await noOtherClients()
  check(await sha(request.source)===request.ciphertext_sha256)
  const archive=await inspectInstallationExport({source:request.source,keyPath:request.key_path,scratchDirectory:dirname(request.source),
    expectedCandidate:request.candidate,expectedInstallation:request.installation})
  check(archive.ciphertext_sha256===request.ciphertext_sha256)
  const files=await snapshotInstallationRoots(request.roots),databaseHash=databaseFingerprint(await fingerprintDatabase())
  await noOtherClients()
  check(['git','ssh','configuration'].every(name=>files[name]===archive.resource_fingerprints[name])&&databaseHash===archive.database_fingerprint)
  check(await sha(request.source)===request.ciphertext_sha256)
  return {protocol:1,purpose:'retirement_snapshot',status:'observed',candidate:request.candidate,installation:request.installation,
    ciphertext_sha256:request.ciphertext_sha256,recovery_point:archive.recovery_point,
    resource_fingerprints:files,database_fingerprint:databaseHash,
    checks:['authenticated archive identity matches independent bindings','live file and database fingerprints match the authenticated archive','other database clients absent at both boundary observations'],
    limitations:['The native controller must continuously hold journal, fence and kernel custody.','This read establishes no functional restoration, resource removal or provider deallocation.']}
}

if(process.argv[1]===fileURLToPath(import.meta.url)){
  try{
    check(process.argv.length===4&&digest(process.argv[3]))
    const info=await lstat(process.argv[2]);check(info.uid===process.getuid())
    const bytes=await privateFile(process.argv[2],32768)
    check(createHash('sha256').update(bytes).digest('hex')===process.argv[3])
    console.log(JSON.stringify(await observeRetirementSnapshot(JSON.parse(bytes.toString('utf8')))))
  }catch(error){console.error(JSON.stringify({status:'refused',code:error instanceof RecoveryError?error.code:'retirement_snapshot_invalid'}));process.exitCode=1}
}
