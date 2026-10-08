import {lstat,readdir,realpath,mkdir,mkdtemp,open,readFile,writeFile} from 'node:fs/promises'
import {createHash} from 'node:crypto'
import {join,resolve,dirname} from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {RecoveryError} from './recovery-bundle.mjs'

const check=(condition)=>{if(!condition)throw new RecoveryError('git_interrupted_lock_invalid')}
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/
async function information(path){try{return await lstat(path)}catch(error){if(error.code==='ENOENT')return null;throw error}}
async function sync(path){const file=await open(path,'r');try{await file.sync()}finally{await file.close()}}

// A Git .lock contains an unpublished replacement. It must never become a ref by recovery.
export async function interruptedLocks(repository){
  const locks=[];let visited=0,bytes=0
  async function lock(path,relative){
    const value=await information(path);if(!value)return
    check(value.isFile()&&value.nlink===1&&value.size<=33554432)
    bytes+=value.size;check(bytes<=67108864&&locks.length<1000)
    locks.push({path,relative,bytes:value.size})
  }
  for(const name of ['HEAD.lock','config.lock','packed-refs.lock','shallow.lock'])await lock(join(repository,name),name)
  async function refs(path,relative,depth){
    check(depth<=64&&++visited<=100000)
    const value=await information(path);if(!value)return
    check(value.isDirectory()||value.isFile())
    if(value.isDirectory())for(const name of (await readdir(path)).sort())await refs(join(path,name),relative+'/'+name,depth+1)
    else if(relative.endsWith('.lock'))await lock(path,relative)
  }
  await refs(join(repository,'refs'),'refs',0)
  return locks
}

export async function quarantineInterruptedLocks(root,repositories,assertQuiescent){
  check(process.platform==='linux'&&typeof assertQuiescent==='function')
  root=resolve(root);check(await realpath(root)===root)
  await assertQuiescent()
  const locks=[]
  for(const row of repositories){
    check(row&&uuid.test(row.storage_key))
    if(row.status!=='ready')continue
    const repository=join(root,row.storage_key+'.git')
    for(const lock of await interruptedLocks(repository))locks.push({...lock,storage_key:row.storage_key})
  }
  check(locks.length<=1000&&locks.reduce((total,lock)=>total+lock.bytes,0)<=67108864)
  if(!locks.length)return []
  const directory=join(root,'.gitgood-interrupted-locks-v1')
  if(!await information(directory)){await mkdir(directory,{mode:0o700});await sync(root)}
  const value=await lstat(directory);check(value.isDirectory()&&(value.mode&0o077)===0&&await realpath(directory)===directory)
  const archive=await mkdtemp(join(directory,'quarantine-'));await sync(directory)
  const records=[]
  for(const lock of locks){
    await assertQuiescent()
    const destination=join(archive,lock.storage_key+'.git',lock.relative)
    await mkdir(dirname(destination),{recursive:true,mode:0o700})
    await sync(lock.path)
    for(let parent=dirname(destination);parent!==directory;parent=dirname(parent))await sync(parent)
    // renameat2 moves the original inode with NOREPLACE, and fsyncs both parents.
    await promisify(execFile)(process.env.GITGOOD_PYTHON??'python3',
      ['-I',fileURLToPath(new URL('./publish_file.py',import.meta.url)),lock.path,destination],{timeout:5000,maxBuffer:1024,windowsHide:true})
    const data=await readFile(destination)
    check(data.length===lock.bytes)
    const record={storage_key:lock.storage_key,path:lock.relative,bytes:data.length,
      sha256:createHash('sha256').update(data).digest('hex'),quarantine:destination.slice(root.length+1)}
    records.push(record)
    await writeFile(join(archive,'receipt.json'),JSON.stringify({protocol:1,records})+'\n',{mode:0o600})
    await sync(join(archive,'receipt.json'));await sync(archive)
  }
  await assertQuiescent()
  return records
}
