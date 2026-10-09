import {createCipheriv,createDecipheriv,createHash,randomBytes,randomUUID} from 'node:crypto'
import {createReadStream,createWriteStream} from 'node:fs'
import {open,lstat,readdir,mkdir,chmod,link,unlink,rm,realpath,writeFile} from 'node:fs/promises'
import {dirname,join,resolve,sep,posix} from 'node:path'
import {Readable} from 'node:stream'
import {pipeline} from 'node:stream/promises'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {fileURLToPath} from 'node:url'

const envelope=Buffer.from('GitgoodRecovery1\n'),payload=Buffer.from('GGpack01')
const MAX_MANIFEST=16*1024*1024,MAX_ENTRIES=100000,MAX_BYTES=16*1024*1024*1024
const required=['git','ssh','configuration','database.dump','configuration/installation.json','ssh/ssh_host_ed25519_key']
export class RecoveryError extends Error {constructor(code='bundle_invalid'){super(code);this.name='RecoveryError';this.code=code}}
const requireThat=(condition,code)=>{if(!condition)throw new RecoveryError(code)}
const digest=()=>createHash('sha256')
const exists=async path=>{try{await lstat(path);return true}catch(error){if(error.code==='ENOENT')return false;throw error}}
const safePath=name=>typeof name==='string'&&Buffer.byteLength(name)<=4096&&!name.includes('\\')&&!name.includes('\0')&&!name.includes(':')&&
  !name.startsWith('/')&&name===posix.normalize(name)&&!name.split('/').some(part=>part==='.'||part==='..'||part==='')&&
  (name==='database.dump'||['git','ssh','configuration'].some(root=>name===root||name.startsWith(root+'/')))
const fileHash=async path=>{const hash=digest();for await(const chunk of createReadStream(path))hash.update(chunk);return hash.digest('hex')}
const keyBytes=key=>{requireThat(Buffer.isBuffer(key)&&key.length===32,'key_invalid');return key}
const syncPath=async path=>{if(process.platform==='linux'){const file=await open(path,'r');try{await file.sync()}finally{await file.close()}}}

function validate(manifest,expectedCandidate,expectedPostgres){
  requireThat(manifest&&Object.getPrototypeOf(manifest)===Object.prototype)
  requireThat(Object.keys(manifest).sort().join(',')==='arch,candidate,entries,format,migrations,platform,postgres,recovery_point')
  requireThat(manifest.format==='gitgood-recovery-1'&&manifest.platform==='linux'&&manifest.arch==='x64','bundle_incompatible')
  requireThat(typeof manifest.candidate==='string'&&/^[a-f0-9]{40}$/.test(manifest.candidate))
  requireThat(typeof manifest.postgres==='string'&&/^18\.[0-9]+$/.test(manifest.postgres),'bundle_incompatible')
  if(expectedCandidate)requireThat(manifest.candidate===expectedCandidate,'bundle_incompatible')
  if(expectedPostgres)requireThat(manifest.postgres===expectedPostgres,'bundle_incompatible')
  requireThat(typeof manifest.recovery_point==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(manifest.recovery_point)&&Number.isFinite(Date.parse(manifest.recovery_point)))
  requireThat(Array.isArray(manifest.migrations)&&manifest.migrations.length<=1000&&manifest.migrations.every(x=>typeof x==='string'&&/^\d{14}$/.test(x)))
  requireThat(new Set(manifest.migrations).size===manifest.migrations.length)
  requireThat(Array.isArray(manifest.entries)&&manifest.entries.length<=MAX_ENTRIES)
  const names=new Map();let total=0,previous=''
  for(const entry of manifest.entries){
    requireThat(entry&&Object.keys(entry).sort().join(',')==='bytes,mode,path,sha256,type')
    requireThat(safePath(entry.path)&&!names.has(entry.path)&&entry.path>previous)
    previous=entry.path
    requireThat(entry.type==='file'||entry.type==='directory')
    requireThat(entry.mode===0o600||entry.mode===0o700)
    requireThat(Number.isSafeInteger(entry.bytes)&&entry.bytes>=0&&entry.bytes<=MAX_BYTES)
    if(entry.type==='directory')requireThat(entry.bytes===0&&entry.sha256===null&&entry.mode===0o700)
    else requireThat(typeof entry.sha256==='string'&&/^[a-f0-9]{64}$/.test(entry.sha256))
    names.set(entry.path,entry);total+=entry.bytes;requireThat(total<=MAX_BYTES)
    const parent=posix.dirname(entry.path)
    if(parent!=='.')requireThat(names.get(parent)?.type==='directory')
  }
  requireThat(required.every(name=>names.has(name)))
  requireThat(['git','ssh','configuration'].every(name=>names.get(name).type==='directory'))
  requireThat(['database.dump','configuration/installation.json','ssh/ssh_host_ed25519_key'].every(name=>names.get(name).type==='file'))
  return total
}

async function inventory(roots,{withoutDatabase=false}={}){
  requireThat(Object.keys(roots).sort().join(',')===(withoutDatabase?'configuration,git,ssh':'configuration,database.dump,git,ssh'),'inventory_invalid')
  const entries=[],sources=new Map()
  async function walk(name,path){
    requireThat(entries.length<MAX_ENTRIES&&safePath(name),'inventory_invalid')
    const stat=await lstat(path);requireThat(stat.isDirectory()||stat.isFile(),'inventory_invalid')
    const type=stat.isDirectory()?'directory':'file'
    if(type==='file')requireThat(stat.nlink===1&&stat.size<=MAX_BYTES,'inventory_invalid')
    entries.push({path:name,type,bytes:type==='file'?stat.size:0,sha256:type==='file'?await fileHash(path):null,
      mode:type==='directory'||(stat.mode&0o111)!==0?0o700:0o600})
    if(type==='file')sources.set(name,path)
    else for(const child of (await readdir(path)).sort()){
      if(name==='git'&&['.gitgood-runtime-v1.json','.gitgood-maintenance-v1.json'].includes(child))continue
      await walk(name+'/'+child,join(path,child))
    }
  }
  const paths=[]
  for(const name of Object.keys(roots).sort()){
    const path=resolve(roots[name]);requireThat((await realpath(path))===path,'inventory_invalid')
    requireThat(!paths.some(other=>path===other||path.startsWith(other+sep)||other.startsWith(path+sep)),'inventory_invalid')
    paths.push(path);await walk(name,path)
  }
  entries.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0)
  return {entries,sources,paths}
}

export function resourceFingerprints(entries){
  return Object.fromEntries(['git','ssh','configuration'].map(root=>{
    const selected=entries.filter(entry=>(entry.path===root||entry.path.startsWith(root+'/'))&&entry.path!=='configuration/recovery.json')
    requireThat(selected.length>0,'inventory_invalid')
    return [root,createHash('sha256').update(JSON.stringify(selected)).digest('hex')]
  }))
}

export async function snapshotInstallationRoots(roots){
  // Read-only normalized archive-format hashes; this grants no removal action.
  const {entries}=await inventory(roots,{withoutDatabase:true})
  return resourceFingerprints(entries)
}

export async function packRecovery({destination,key,metadata,roots,beforePublish}){
  keyBytes(key);destination=resolve(destination)
  requireThat(!await exists(destination),'destination_exists')
  const {entries,sources,paths}=await inventory(roots)
  requireThat(!paths.some(path=>destination===path||destination.startsWith(path+sep)),'destination_invalid')
  const manifest={format:'gitgood-recovery-1',candidate:metadata.candidate,postgres:metadata.postgres,platform:'linux',arch:'x64',
    recovery_point:metadata.recovery_point,migrations:metadata.migrations,entries}
  const total=validate(manifest),encoded=Buffer.from(JSON.stringify(manifest))
  requireThat(encoded.length<=MAX_MANIFEST,'inventory_invalid')
  const size=Buffer.alloc(4);size.writeUInt32BE(encoded.length)
  const nonce=randomBytes(12),header=Buffer.concat([envelope,nonce])
  const cipher=createCipheriv('aes-256-gcm',key,nonce);cipher.setAAD(header)
  const temporary=destination+'.'+randomUUID()+'.partial'
  let file
  try{
    file=await open(temporary,'wx',0o600);await file.write(header)
    async function* plaintext(){
      yield payload;yield size;yield encoded
      for(const entry of entries)if(entry.type==='file'){
        const hash=digest();let bytes=0
        for await(const chunk of createReadStream(sources.get(entry.path))){bytes+=chunk.length;requireThat(bytes<=entry.bytes,'snapshot_changed');hash.update(chunk);yield chunk}
        requireThat(bytes===entry.bytes&&hash.digest('hex')===entry.sha256,'snapshot_changed')
      }
    }
    const output=createWriteStream(temporary,{fd:file.fd,autoClose:false,start:header.length})
    await pipeline(Readable.from(plaintext()),cipher,output)
    requireThat(output.bytesWritten===payload.length+4+encoded.length+total)
    await file.write(cipher.getAuthTag(),0,16,header.length+output.bytesWritten)
    await file.sync();await file.close();file=undefined
    if(beforePublish)await beforePublish()
    // Same-directory hard link publishes without overwriting a concurrent destination.
    await link(temporary,destination);await unlink(temporary);await syncPath(dirname(destination))
    return {candidate:manifest.candidate,files:entries.filter(x=>x.type==='file').length,plaintext_bytes:total,ciphertext_sha256:await fileHash(destination),recovery_point:manifest.recovery_point}
  }catch(error){throw error instanceof RecoveryError?error:new RecoveryError()}
  finally{if(file)await file.close().catch(()=>{});await unlink(temporary).catch(()=>{})}
}

async function readExact(file,bytes,position){
  const result=Buffer.alloc(bytes);let offset=0
  while(offset<bytes){const read=await file.read(result,offset,bytes-offset,position+offset);requireThat(read.bytesRead>0);offset+=read.bytesRead}
  return result
}
async function hashRange(path,start,bytes){
  const hash=digest();if(bytes)for await(const chunk of createReadStream(path,{start,end:start+bytes-1}))hash.update(chunk)
  return hash.digest('hex')
}

export async function unpackRecovery({source,key,target,expectedCandidate,expectedPostgres='18.4'}){
  keyBytes(key);source=resolve(source);target=resolve(target)
  requireThat(!await exists(target),'destination_exists')
  requireThat((await realpath(dirname(target)))===dirname(target),'destination_invalid')
  const stage=join(dirname(target),'.gitgood-verified-'+randomUUID()),plain=join(stage,'.authenticated-pack')
  let input,decoded,complete=false
  try{
    const stat=await lstat(source);requireThat(stat.isFile()&&stat.nlink===1&&stat.size>=envelope.length+12+16&&stat.size<=MAX_BYTES+MAX_MANIFEST+1024)
    input=await open(source,'r')
    const header=await readExact(input,envelope.length+12,0)
    requireThat(header.subarray(0,envelope.length).equals(envelope),'bundle_incompatible')
    const decipher=createDecipheriv('aes-256-gcm',key,header.subarray(envelope.length));decipher.setAAD(header)
    decipher.setAuthTag(await readExact(input,16,stat.size-16))
    await mkdir(stage,{mode:0o700})
    await pipeline(createReadStream(source,{fd:input.fd,autoClose:false,start:header.length,end:stat.size-17}),decipher,
      createWriteStream(plain,{flags:'wx',mode:0o600}))
    // Nothing is extracted until the complete AEAD tag has authenticated.
    await input.close();input=undefined;decoded=await open(plain,'r')
    const prefix=await readExact(decoded,payload.length+4,0);requireThat(prefix.subarray(0,payload.length).equals(payload))
    const length=prefix.readUInt32BE(payload.length);requireThat(length<=MAX_MANIFEST)
    const encoded=await readExact(decoded,length,prefix.length),manifest=JSON.parse(encoded.toString('utf8'))
    requireThat(Buffer.from(JSON.stringify(manifest)).equals(encoded))
    const total=validate(manifest,expectedCandidate,expectedPostgres),start=prefix.length+length
    requireThat((await decoded.stat()).size===start+total)
    let offset=start
    for(const entry of manifest.entries)if(entry.type==='file'){
      requireThat(await hashRange(plain,offset,entry.bytes)===entry.sha256);offset+=entry.bytes
    }
    // Inventory is fully authenticated and all declared file hashes match before materialization.
    offset=start
    for(const entry of manifest.entries){
      const path=join(stage,...entry.path.split('/'))
      if(entry.type==='directory')await mkdir(path,{mode:0o700})
      else{
        if(entry.bytes)await pipeline(createReadStream(plain,{start:offset,end:offset+entry.bytes-1}),createWriteStream(path,{flags:'wx',mode:entry.mode}))
        else await writeFile(path,Buffer.alloc(0),{flag:'wx',mode:entry.mode})
        await chmod(path,entry.mode);requireThat(await fileHash(path)===entry.sha256);offset+=entry.bytes
      }
    }
    const dump=await open(join(stage,'database.dump'),'r')
    try{requireThat((await readExact(dump,5,0)).equals(Buffer.from('PGDMP')))}finally{await dump.close()}
    await decoded.close();decoded=undefined;await unlink(plain)
    await writeFile(join(stage,'manifest.json'),JSON.stringify(manifest)+'\n',{flag:'wx',mode:0o600})
    for(const entry of [...manifest.entries].reverse())await syncPath(join(stage,...entry.path.split('/')))
    await syncPath(join(stage,'manifest.json'));await syncPath(stage)
    requireThat(!await exists(target),'destination_exists')
    await promisify(execFile)(process.env.GITGOOD_PYTHON??(process.platform==='win32'?'python':'python3'),
      ['-I',fileURLToPath(new URL('./publish_directory.py',import.meta.url)),stage,target],{timeout:5000,maxBuffer:1024,windowsHide:true})
    complete=true
    return {manifest,verified_directory:target,ciphertext_sha256:await fileHash(source)}
  }catch(error){throw error instanceof RecoveryError?error:new RecoveryError()}
  finally{
    if(input)await input.close().catch(()=>{});if(decoded)await decoded.close().catch(()=>{})
    if(!complete)await rm(stage,{recursive:true,force:true}).catch(()=>{})
  }
}
