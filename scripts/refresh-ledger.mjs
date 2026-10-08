import {readFile,writeFile,mkdir,rename,unlink} from 'node:fs/promises'
import {readFileSync} from 'node:fs'
import {join} from 'node:path'
import {execFileSync} from 'node:child_process'
import {createHash,randomUUID} from 'node:crypto'
import {load,root,validate} from './model.mjs'
import {readLedger,reconcileLedger,requirementIdentity} from './ledger-source.mjs'

const model=load(),now=new Date()
const candidate=execFileSync(process.env.GITGOOD_GIT??'git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim()
const config=JSON.parse(await readFile(join(root,'evidence/ledger.json'),'utf8'))
const requirements=requirementIdentity(model.catalog,path=>readFileSync(join(root,path),'utf8'))
let observation,error
try{observation=await readLedger({config,token:process.env.GITGOOD_LEDGER_TOKEN,requirements,now})}
catch(failure){error=/^ledger_[a-z0-9_]+$/.test(failure.message)?failure.message:'ledger_refresh_failed'}
const snapshot=reconcileLedger(model.snapshot,{observation,error,now,candidate})
snapshot.specRevision='sha256:'+createHash('sha256').update(JSON.stringify(Object.fromEntries(requirements.map(item=>[item.id,item.sha256])))).digest('hex')
const errors=validate({...model,snapshot},now)
if(errors.length)throw new Error('Refreshed ledger snapshot failed model validation')
const history=join(root,'.gitgood/report-history',now.toISOString().replaceAll(':','-')+'-'+randomUUID())
await mkdir(history,{recursive:true,mode:0o700})
await writeFile(join(history,'observation.json'),JSON.stringify({candidate,recordedAt:now.toISOString(),requirements:Object.fromEntries(requirements.map(item=>[item.id,item.sha256])),observation,error},null,2)+'\n',{flag:'wx',mode:0o600})
await writeFile(join(history,'previous-snapshot.json'),JSON.stringify(model.snapshot,null,2)+'\n',{flag:'wx',mode:0o600})
await writeFile(join(history,'next-snapshot.json'),JSON.stringify(snapshot,null,2)+'\n',{flag:'wx',mode:0o600})
const temporary=join(root,'evidence','.status-'+randomUUID()+'.partial')
try{
  await writeFile(temporary,JSON.stringify(snapshot,null,2)+'\n',{flag:'wx',mode:0o600})
  await rename(temporary,join(root,'evidence/status.json'))
}finally{await unlink(temporary).catch(()=>{})}
console.log(JSON.stringify({candidate,ledger:snapshot.sources.ledger.status,records:snapshot.records.length,reason:error??null,
  verification:'Preserved separately; task completion and criterion stamps do not establish verification.'}))
if(error)process.exitCode=2
