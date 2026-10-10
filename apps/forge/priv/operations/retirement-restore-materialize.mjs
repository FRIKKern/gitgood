import {createReadStream, constants} from 'node:fs'
import {open, lstat, realpath, readdir, mkdtemp, rm, cp, writeFile, readFile} from 'node:fs/promises'
import {createHash, X509Certificate, createPrivateKey, createPublicKey} from 'node:crypto'
import {join, resolve, basename} from 'node:path'
import {fileURLToPath} from 'node:url'
import {hostname} from 'node:os'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {RecoveryError, unpackRecovery, snapshotInstallationRoots} from './recovery-bundle.mjs'
import {privateFile, readConfiguration, validateConfiguration} from './recovery-configuration.mjs'
import {inspectRepositories, rebindRepositories} from './recovery-git.mjs'
import {verifyRetirementRestoreData} from './retirement-restore-data.mjs'

const check = value => { if (!value) throw new RecoveryError('retirement_materialization_invalid') }
const uuid = value => typeof value === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value)
const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const hash = async path => { const value=createHash('sha256'); for await(const bytes of createReadStream(path)) value.update(bytes); return value.digest('hex') }
const same = (a,b) => JSON.stringify(a) === JSON.stringify(b)
const roots = root => Object.fromEntries(['git','ssh','configuration'].map(name=>[name,join(root,name)]))
const overlaps = (a,b) => a===b || a.startsWith(b+'/') || b.startsWith(a+'/')

async function targetIdentity(value) {
  check(value && Object.keys(value).sort().join(',')==='device,inode,path,uid')
  check(typeof value.path==='string' && resolve(value.path)===value.path && await realpath(value.path)===value.path)
  for(const name of ['device','inode','uid']) check(Number.isSafeInteger(value[name]) && value[name]>=0)
  const stat=await lstat(value.path)
  check(stat.isDirectory() && stat.dev===value.device && stat.ino===value.inode && stat.uid===value.uid && value.uid===process.getuid() && (stat.mode&0o777)===0o700)
}

async function runtimeMarker(request) {
  const expected=request.runtime_marker,group=request.native_group
  const marker=join(request.target_root.path,'git/.gitgood-runtime-v1.json')
  check(expected && Object.keys(expected).sort().join(',')==='bytes,device,inode,mode,path,sha256,uid' && expected.path===marker)
  for(const key of ['device','inode','uid','mode','bytes']) check(Number.isSafeInteger(expected[key])&&expected[key]>=0)
  check(expected.uid===process.getuid() && expected.mode===0o600 && expected.bytes>0 && expected.bytes<=4096 && digest(expected.sha256))
  const stat=await lstat(marker),raw=await privateFile(marker,4096)
  check(stat.isFile()&&stat.nlink===1&&stat.dev===expected.device&&stat.ino===expected.inode&&stat.uid===expected.uid&&
    (stat.mode&0o777)===expected.mode&&stat.size===expected.bytes&&createHash('sha256').update(raw).digest('hex')===expected.sha256)
  const value=JSON.parse(raw.toString('utf8'))
  check(value && Object.keys(value).sort().join(',')==='candidate,cgroup,created_at,host,mode,owner_births,owners,protocol')
  check(value.protocol===1&&value.mode==='runtime'&&value.candidate===request.candidate&&value.host===hostname())
  check(typeof value.created_at==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value.created_at)&&Number.isFinite(Date.parse(value.created_at)))
  const kernel='/gitgood-installation-'+request.installation+'/retirement-'+request.operation+'/'+request.target_installation+'/native'
  check(value.cgroup===kernel&&group&&Object.keys(group).sort().join(',')==='delegated_uid,device,inode,kernel_path,path')
  check(group.path==='/sys/fs/cgroup'+kernel&&group.kernel_path===kernel&&group.delegated_uid===process.getuid())
  for(const key of ['device','inode','delegated_uid']) check(Number.isSafeInteger(group[key])&&group[key]>=0)
  check(await realpath(group.path)===group.path)
  const info=await lstat(group.path),mount=await lstat('/sys/fs/cgroup')
  check(info.isDirectory()&&info.dev===mount.dev&&info.dev===group.device&&info.ino===group.inode&&[0,process.getuid()].includes(info.uid))
  for(const name of ['cgroup.procs','cgroup.kill']) {const control=await lstat(join(group.path,name));check(control.isFile()&&control.uid===process.getuid())}
  check(/(?:^|\n)populated 0(?:\n|$)/.test(await readFile(join(group.path,'cgroup.events'),'utf8'))&&!(await readFile(join(group.path,'cgroup.procs'),'utf8')).trim())
  const {stdout}=await promisify(execFile)(process.env.GITGOOD_PYTHON??'/usr/bin/python3',
    ['-I',fileURLToPath(new URL('./process_status.py',import.meta.url)),marker,'require-empty-cgroup'],{timeout:5000,maxBuffer:1024,windowsHide:true})
  check(stdout.trim()==='clear')
  return marker
}

async function validateCopiedTree(source,target,marker=null) {
  // Compare the entire target, including any unexpected runtime markers. The
  // normalized archive fingerprint alone intentionally excludes those markers.
  const left=await lstat(source),right=await lstat(target)
  check(await realpath(target)===target && right.uid===process.getuid())
  check(left.isDirectory()===right.isDirectory() && left.isFile()===right.isFile() && (right.mode&0o777)===(left.mode&0o777))
  if(left.isDirectory()) {
    const names=(await readdir(source)).sort(),actual=(await readdir(target)).filter(name=>join(target,name)!==marker).sort()
    check(same(names,actual))
    for(const name of names) await validateCopiedTree(join(source,name),join(target,name),marker)
  } else {
    check(left.isFile() && right.nlink===1 && left.size===right.size && await hash(source)===await hash(target))
  }
  const handle=await open(target,constants.O_RDONLY|constants.O_NOFOLLOW)
  try { await handle.sync() } finally { await handle.close() }
}

export async function materializeRetirementRestore(request) {
  check(process.platform==='linux' && process.arch==='x64' && process.version==='v22.23.3')
  check(request && typeof request==='object')
  const afterRuntime=request.protocol===3&&request.phase==='observe'
  const observing=(request.protocol===2 || afterRuntime)&&request.phase==='observe'
  check(Object.keys(request).sort().join(',')===(afterRuntime ?
    'candidate,ciphertext_sha256,installation,key_path,native_group,operation,phase,ports,protocol,runtime_marker,scratch_directory,source,target_database,target_installation,target_root' : observing ?
    'candidate,ciphertext_sha256,installation,key_path,operation,phase,ports,protocol,scratch_directory,source,target_database,target_installation,target_root' :
    'candidate,ciphertext_sha256,installation,key_path,operation,ports,protocol,scratch_directory,source,target_database,target_installation,target_root'))
  check((request.protocol===1 || observing) && uuid(request.operation) && uuid(request.installation) && uuid(request.target_installation) && request.target_installation!==request.installation)
  check(typeof request.candidate==='string' && /^[a-f0-9]{40}$/.test(request.candidate) && digest(request.ciphertext_sha256))
  const ports=request.ports
  check(ports && Object.keys(ports).sort().join(',')==='forge,https,native_ssh,ssh,web')
  check(Object.values(ports).every(value=>Number.isSafeInteger(value)&&value>=1024&&value<=65535) && new Set(Object.values(ports)).size===5)
  await targetIdentity(request.target_root)
  const target=request.target_root.path
  check(basename(target)==='gitgood_retirement_restore_'+request.operation.replaceAll('-',''))
  check(observing ? same((await readdir(target)).sort(),['configuration','git','ssh']) : (await readdir(target)).length===0)
  const marker=afterRuntime?await runtimeMarker(request):null
  for(const path of [request.source,request.key_path]) check(typeof path==='string' && resolve(path)===path && !overlaps(target,path))
  check(typeof request.scratch_directory==='string' && resolve(request.scratch_directory)===request.scratch_directory &&
    request.scratch_directory!==target && !request.scratch_directory.startsWith(target+'/'))
  // This is a read-only observation of already restored contents. It refuses
  // target replacement, clients, changed data and a different archived source.
  const data=await verifyRetirementRestoreData({protocol:1,operation:request.operation,installation:request.installation,candidate:request.candidate,
    ciphertext_sha256:request.ciphertext_sha256,source:request.source,key_path:request.key_path,scratch_directory:request.scratch_directory,
    target:request.target_database,phase:'observe'})
  const key=await privateFile(request.key_path,32); check(key.length===32)
  const scratch=await mkdtemp(join(request.scratch_directory,'.gitgood-retirement-materialize-'))
  let targetHandle
  try {
    const unpacked=await unpackRecovery({source:request.source,key,target:join(scratch,'verified'),expectedCandidate:request.candidate})
    check(unpacked.ciphertext_sha256===request.ciphertext_sha256)
    const verified=unpacked.verified_directory,configuration=join(verified,'configuration'),config=await readConfiguration(configuration)
    check(config.installation===request.installation)
    for(const path of [config.forge.GITGOOD_STORAGE,config.forge.GITGOOD_SSH_HOST_KEY_DIRECTORY]) check(typeof path==='string' && resolve(path)===path && !overlaps(target,path))
    const originalPorts=[Number(config.forge.PORT),Number(config.web.PORT),Number(config.forge.GITGOOD_SSH_PORT),Number(config.forge.GITGOOD_SSH_PUBLIC_PORT),new URL(config.forge.GITGOOD_PUBLIC_URL).port].map(Number)
    check(Object.values(ports).every(value=>!originalPorts.includes(value)))
    const certificate=new X509Certificate(await privateFile(join(configuration,config.edge.tls_certificate)))
    check(certificate.checkIP('127.0.0.1')==='127.0.0.1' && Date.parse(certificate.validFrom)<=Date.now() && Date.parse(certificate.validTo)>Date.now())
    const tlsKey=createPrivateKey(await privateFile(join(configuration,config.edge.tls_key)))
    check(certificate.publicKey.export({type:'spki',format:'der'}).equals(createPublicKey(tlsKey).export({type:'spki',format:'der'})))
    const descriptor=JSON.parse((await privateFile(join(configuration,'recovery.json'),16777216)).toString('utf8'))
    check(descriptor.installation===request.installation && Array.isArray(descriptor.repositories))
    await rebindRepositories(join(verified,'git'),join(target,'git'),descriptor.repositories)
    const database=new URL(config.forge.DATABASE_URL); database.pathname='/'+request.target_database.database
    config.installation=request.target_installation
    if(Object.hasOwn(config.forge,'GITGOOD_INSTALLATION_ID'))
      config.forge.GITGOOD_INSTALLATION_ID=request.target_installation
    config.forge.DATABASE_URL=database.toString()
    config.forge.PHX_HOST='127.0.0.1'
    config.forge.GITGOOD_PUBLIC_URL='https://127.0.0.1:'+ports.https
    config.forge.GITGOOD_WEB_ORIGIN=config.forge.GITGOOD_PUBLIC_URL
    config.forge.GITGOOD_STORAGE=join(target,'git')
    config.forge.GITGOOD_SSH_HOST_KEY_DIRECTORY=join(target,'ssh')
    config.forge.GITGOOD_SSH_PUBLIC_HOST='127.0.0.1'
    config.forge.PORT=String(ports.forge)
    config.forge.GITGOOD_SSH_PORT=String(ports.native_ssh)
    config.forge.GITGOOD_SSH_PUBLIC_PORT=String(ports.ssh)
    delete config.forge.GITGOOD_BARKPARK_ORIGIN
    if(config.forge.GITGOOD_BARKPARK_CA) config.forge.GITGOOD_BARKPARK_CA=join(target,'configuration',config.edge.source_ca)
    config.web.PORT=String(ports.web)
    config.web.GITGOOD_API_URL='http://127.0.0.1:'+ports.forge
    validateConfiguration(config)
    await writeFile(join(configuration,'installation.json'),JSON.stringify(config)+'\n',{mode:0o600})
    await targetIdentity(request.target_root)
    check(observing ? same((await readdir(target)).sort(),['configuration','git','ssh']) : (await readdir(target)).length===0)
    targetHandle=await open(target,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW)
    const opened=await targetHandle.stat(); check(opened.dev===request.target_root.device && opened.ino===request.target_root.inode)
    // Descriptor anchoring keeps publication inside the original owned target
    // even if its pathname changes. Existing files are never overwritten.
    if(!observing) {
      for(const name of ['git','ssh','configuration']) {
        await targetIdentity(request.target_root)
        await cp(join(verified,name),'/proc/self/fd/'+targetHandle.fd+'/'+name,{recursive:true,force:false,errorOnExist:true})
      }
    }
    await targetIdentity(request.target_root)
    check(same((await readdir(target)).sort(),['configuration','git','ssh']))
    for(const name of ['git','ssh','configuration']) await validateCopiedTree(join(verified,name),join(target,name),marker)
    check(same(await inspectRepositories(join(target,'git'),descriptor.repositories.map(({storage_key,status})=>({storage_key,status}))),descriptor.repositories))
    const fingerprints=await snapshotInstallationRoots(roots(target))
    check(same(fingerprints,await snapshotInstallationRoots(roots(verified))))
    check(await hash(request.source)===request.ciphertext_sha256)
    // Recheck restored data and target identity after materialization. Nothing
    // here grants runtime launch, writer custody or removal authority.
    const after=await verifyRetirementRestoreData({protocol:1,operation:request.operation,installation:request.installation,candidate:request.candidate,
      ciphertext_sha256:request.ciphertext_sha256,source:request.source,key_path:request.key_path,scratch_directory:request.scratch_directory,
      target:request.target_database,phase:'observe'})
    check(same(data,after))
    if(afterRuntime) check(await runtimeMarker(request)===marker)
    await targetIdentity(request.target_root)
    await targetHandle.sync()
    return {protocol:afterRuntime?3:observing?2:1,purpose:'retirement_restore_materialization',status:observing?'observed':'materialized',...(observing?{phase:'observe'}:{}),...(afterRuntime?{runtime_marker:request.runtime_marker,native_group:request.native_group}:{}),operation:request.operation,
      installation:request.installation,candidate:request.candidate,ciphertext_sha256:request.ciphertext_sha256,recovery_point:data.recovery_point,
      resource_fingerprints:data.resource_fingerprints,database_fingerprint:data.database_fingerprint,
      target_installation:request.target_installation,target_root:request.target_root,target_database:request.target_database,
      target_resource_fingerprints:fingerprints,configuration_sha256:await hash(join(target,'configuration/installation.json')),ports,
      checks:['authenticated archive and restored database match',observing?'sealed existing separate target and retained local TLS identity match':'sealed empty separate target and retained local TLS identity match',observing?'existing private stores, fixed hooks and operational configuration match without copying':'private stores, fixed hooks and operational configuration materialize exactly','archive and restored target data remain unchanged'],
      limitations:['No runtime was launched and functional restoration remains unverified.','The fixed native controller must hold original custody and retain every target, group and interrupted material.','No original resource, target database, provider resource or failed target is removed.']}
  } finally {
    if(targetHandle) await targetHandle.close()
    key.fill(0)
    check(await realpath(scratch)===scratch && scratch.startsWith(request.scratch_directory+'/.gitgood-retirement-materialize-'))
    await rm(scratch,{recursive:true,force:true})
  }
}

if(process.argv[1]===fileURLToPath(import.meta.url)) {
  try {
    check(process.argv.length===4 && digest(process.argv[3]))
    const stat=await lstat(process.argv[2]); check(stat.uid===process.getuid())
    const raw=await privateFile(process.argv[2],32768); check(createHash('sha256').update(raw).digest('hex')===process.argv[3])
    console.log(JSON.stringify(await materializeRetirementRestore(JSON.parse(raw.toString('utf8')))))
  } catch(error) {
    console.error(JSON.stringify({status:'refused',code:error instanceof RecoveryError?error.code:'retirement_materialization_invalid'}));process.exitCode=1
  }
}
