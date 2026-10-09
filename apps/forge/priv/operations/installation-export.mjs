import {mkdtemp,rm,lstat,realpath} from 'node:fs/promises'
import {join,resolve} from 'node:path'
import {spawn} from 'node:child_process'
import {fileURLToPath} from 'node:url'
import {unpackRecovery,RecoveryError} from './recovery-bundle.mjs'
import {privateFile,readConfiguration} from './recovery-configuration.mjs'
import {inspectRepositories} from './recovery-git.mjs'

const check=condition=>{if(!condition)throw new RecoveryError('export_invalid')}
async function dumpInventory(path,version){
  const tool=process.env.GITGOOD_PG_RESTORE??'pg_restore'
  async function run(args){
    const child=spawn(tool,args,{env:{PATH:process.env.PATH,HOME:'/nonexistent'},stdio:['ignore','pipe','pipe'],windowsHide:true})
    const chunks=[];let bytes=0,failed=false,killer
    const terminate=()=>{if(failed)return;failed=true;child.kill('SIGTERM');killer=setTimeout(()=>child.kill('SIGKILL'),1000)}
    const timer=setTimeout(terminate,300000)
    child.stdout.on('data',chunk=>{bytes+=chunk.length;if(bytes>1048576)terminate();else chunks.push(chunk)})
    child.stderr.resume()
    await new Promise((accept,reject)=>{
      child.once('error',()=>reject(new RecoveryError('export_dump_invalid')))
      child.once('close',code=>code===0&&!failed?accept():reject(new RecoveryError('export_dump_invalid')))
    }).finally(()=>{clearTimeout(timer);clearTimeout(killer)})
    return Buffer.concat(chunks).toString('utf8')
  }
  check((await run(['--version'])).trim()==='pg_restore (PostgreSQL) '+version)
  // Listing a custom-format dump does not execute SQL or connect to a database.
  const listing=await run(['--list',path]),tables=[]
  for(const line of listing.split('\n')){
    const match=line.match(/^\d+; \d+ \d+ TABLE public ([a-z][a-z0-9_]{0,62}) [^\s]+$/)
    if(match)tables.push(match[1])
  }
  check(tables.length<=1000&&new Set(tables).size===tables.length)
  return tables.sort()
}

export async function inspectInstallationExport({source,keyPath,scratchDirectory,expectedCandidate}){
  check(process.platform==='linux'&&process.arch==='x64'&&process.version==='v22.23.3')
  check(typeof expectedCandidate==='string'&&/^[a-f0-9]{40}$/.test(expectedCandidate))
  const parent=resolve(scratchDirectory),stat=await lstat(parent)
  check(stat.isDirectory()&&(stat.mode&0o077)===0&&stat.uid===process.getuid()&&await realpath(parent)===parent)
  const key=await privateFile(keyPath,32);check(key.length===32)
  const scratch=await mkdtemp(join(parent,'.gitgood-export-inspection-'))
  try{
    const unpacked=await unpackRecovery({source,key,target:join(scratch,'verified'),expectedCandidate})
    const configuration=join(unpacked.verified_directory,'configuration')
    const config=await readConfiguration(configuration)
    const descriptor=JSON.parse((await privateFile(join(configuration,'recovery.json'),16777216)).toString('utf8'))
    check(descriptor.protocol===1&&descriptor.installation===config.installation&&Array.isArray(descriptor.repositories))
    const repositories=await inspectRepositories(join(unpacked.verified_directory,'git'),descriptor.repositories.map(({storage_key,status})=>({storage_key,status})))
    check(JSON.stringify(repositories)===JSON.stringify(descriptor.repositories))
    check(Array.isArray(descriptor.database?.tables)&&descriptor.database.tables.length<=1000)
    const tables=await dumpInventory(join(unpacked.verified_directory,'database.dump'),unpacked.manifest.postgres)
    check(JSON.stringify(tables)===JSON.stringify(descriptor.database.tables.map(row=>row.table).sort()))
    return {protocol:1,purpose:'installation_export',candidate:unpacked.manifest.candidate,
      ciphertext_sha256:unpacked.ciphertext_sha256,recovery_point:unpacked.manifest.recovery_point,
      formats:{code:'bare Git SHA-1 repositories',collaboration:'PostgreSQL custom-format dump',configuration:'private JSON and key material'},
      repositories:repositories.length,tables:tables.length,files:unpacked.manifest.entries.filter(entry=>entry.type==='file').length,
      checks:['complete authenticated archive and file hashes','installation configuration and key custody','Git fsck and exact recorded refs','database dump table inventory'],
      limitations:['Inspection does not establish database restore or application readiness.','Independent archive decryption-key custody and matching application artifacts remain required.','No installation or provider resource was removed.']}
  }finally{
    key.fill(0)
    // Only the fresh directory created by this invocation is eligible for cleanup.
    check(await realpath(scratch)===scratch&&scratch.startsWith(parent+'/.gitgood-export-inspection-'))
    await rm(scratch,{recursive:true,force:true})
  }
}

if(process.argv[1]===fileURLToPath(import.meta.url)){
  try{
    check(process.argv.length===6)
    const [source,keyPath,scratchDirectory,expectedCandidate]=process.argv.slice(2)
    console.log(JSON.stringify(await inspectInstallationExport({source,keyPath,scratchDirectory,expectedCandidate})))
  }catch(error){console.error(JSON.stringify({status:'refused',code:error instanceof RecoveryError?error.code:'export_invalid'}));process.exitCode=1}
}
