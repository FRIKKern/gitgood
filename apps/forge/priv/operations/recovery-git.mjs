import {spawn} from 'node:child_process'
import {readFile,writeFile,lstat,readdir} from 'node:fs/promises'
import {join,resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import {RecoveryError} from './recovery-bundle.mjs'

const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/
const allowed=new Set(['core.repositoryformatversion','core.filemode','core.bare','core.hookspath',
  'receive.fsckobjects','transfer.fsckobjects','receive.denynonfastforwards','receive.denydeletes',
  'receive.maxinputsize','http.getanyfile','http.maxrequestbuffer','transfer.hiderefs'])
const check=condition=>{if(!condition)throw new RecoveryError('git_inventory_invalid')}
async function git(path,args){
  const child=spawn(process.env.GITGOOD_GIT??'git',['--git-dir',path,...args],{
    env:{PATH:process.env.PATH,HOME:'/nonexistent',GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',GIT_TERMINAL_PROMPT:'0'},
    stdio:['ignore','pipe','pipe'],windowsHide:true})
  const chunks=[];let bytes=0,failed=false,killer
  const terminate=()=>{if(failed)return;failed=true;child.kill('SIGTERM');killer=setTimeout(()=>child.kill('SIGKILL'),1000)}
  const timer=setTimeout(terminate,300000)
  child.stdout.on('data',chunk=>{bytes+=chunk.length;if(bytes>1048576)terminate();else chunks.push(chunk)})
  child.stderr.resume()
  await new Promise((resolve,reject)=>{
    child.once('error',()=>reject(new RecoveryError('git_inventory_invalid')))
    child.once('close',code=>code===0&&!failed?resolve():reject(new RecoveryError('git_inventory_invalid')))
  }).finally(()=>{clearTimeout(timer);clearTimeout(killer)})
  return Buffer.concat(chunks).toString('utf8').trim()
}
async function config(path){
  const raw=await git(path,['config','--local','--no-includes','--null','--list'])
  const entries=raw.split('\0').filter(Boolean).map(value=>value.split('\n'))
  check(entries.every(([name,value,...extra])=>allowed.has(name)&&typeof value==='string'&&extra.length===0))
  check(new Set(entries.map(([name])=>name)).size===entries.length)
  const values=Object.fromEntries(entries)
  check(values['transfer.hiderefs']===undefined||values['transfer.hiderefs']==='refs/gitgood/')
  check(values['core.bare']==='true'&&values['core.repositoryformatversion']==='0')
  check(values['receive.fsckobjects']==='true'&&values['transfer.fsckobjects']==='true'&&
    values['receive.denynonfastforwards']==='true'&&values['receive.denydeletes']==='true'&&
    values['receive.maxinputsize']==='33554432'&&values['http.getanyfile']==='false'&&values['http.maxrequestbuffer']==='33554432')
}
export async function inspectRepositories(root,rows){
  check(Array.isArray(rows)&&rows.length<=10000)
  const names=await readdir(root),result=[]
  for(const row of rows){
    check(row&&Object.keys(row).sort().join(',')==='status,storage_key'&&uuid.test(row.storage_key)&&['creating','ready','failed'].includes(row.status))
    const name=row.storage_key+'.git',path=join(root,name)
    if(!names.includes(name)){check(row.status!=='ready');result.push({...row,refs:null});continue}
    check((await lstat(path)).isDirectory())
    if(row.status!=='ready'){result.push({...row,refs:null});continue}
    // Native repositories never depend on objects outside their owned storage tree.
    try{await lstat(join(path,'objects/info/alternates'));throw new RecoveryError('git_inventory_invalid')}catch(error){if(error.code!=='ENOENT')throw error}
    await config(path)
    check(await git(path,['rev-parse','--show-object-format'])==='sha1')
    await git(path,['fsck','--full','--strict'])
    const refs=await git(path,['for-each-ref','--format=%(refname) %(objectname)'])
    check(refs.split('\n').filter(Boolean).every(line=>/^refs\/[^\s]+ [a-f0-9]{40}$/.test(line)))
    result.push({...row,refs})
  }
  return result
}
export async function rebindRepositories(stageRoot,targetRoot,repositories){
  const hook=await readFile(fileURLToPath(new URL('../pre-receive',import.meta.url)))
  for(const repository of repositories)if(repository.refs!==null){
    const path=join(stageRoot,repository.storage_key+'.git')
    await writeFile(join(path,'hooks/pre-receive'),hook,{mode:0o700})
    await git(path,['config','core.hooksPath',join(resolve(targetRoot),repository.storage_key+'.git/hooks')])
  }
}
