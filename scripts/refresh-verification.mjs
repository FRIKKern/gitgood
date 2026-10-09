import {readFile,writeFile,mkdir,rename,unlink} from 'node:fs/promises'
import {readFileSync} from 'node:fs'
import {join} from 'node:path'
import {execFileSync} from 'node:child_process'
import {createHash,randomUUID} from 'node:crypto'
import {load,root,validate} from './model.mjs'
import {requirementIdentity} from './ledger-source.mjs'
import {readVerification,reconcileVerification} from './verification-source.mjs'

const settings=JSON.parse(await readFile(join(root,'evidence/verification.json'),'utf8'))
if(settings.schemaVersion!==1||typeof settings.enabled!=='boolean'||Object.keys(settings).length!==2)throw new Error('verification_configuration_invalid')
if(!settings.enabled){console.log(JSON.stringify({verification:'unconfigured',reason:'Authenticated Source evaluation ingestion not enabled'}));process.exit(2)}
const model=load(),now=new Date()
const candidate=execFileSync(process.env.GITGOOD_GIT??'git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim()
const config=JSON.parse(await readFile(join(root,'evidence/ledger.json'),'utf8'))
const requirements=requirementIdentity(model.catalog,path=>readFileSync(join(root,path),'utf8'))
let observation,error
try{observation=await readVerification({config,token:process.env.GITGOOD_LEDGER_TOKEN,requirements,now})}
catch(failure){error=/^verification_[a-z0-9_]+$/.test(failure.message)?failure.message:'verification_refresh_failed'}
const snapshot=reconcileVerification(model.snapshot,{observation,error,now,candidate})
snapshot.specRevision='sha256:'+createHash('sha256').update(JSON.stringify(Object.fromEntries(requirements.map(item=>[item.id,item.sha256])))).digest('hex')
if(validate({...model,snapshot},now).length)throw new Error('verification_snapshot_invalid')
const history=join(root,'.gitgood/report-history',now.toISOString().replaceAll(':','-')+'-'+randomUUID())
await mkdir(history,{recursive:true,mode:0o700})
for(const [name,value] of Object.entries({'verification-observation':{candidate,recordedAt:now.toISOString(),observation,error},'previous-snapshot':model.snapshot,'next-snapshot':snapshot}))
  await writeFile(join(history,name+'.json'),JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600})
const temporary=join(root,'evidence','.status-'+randomUUID()+'.partial')
try{
  await writeFile(temporary,JSON.stringify(snapshot,null,2)+'\n',{flag:'wx',mode:0o600})
  await rename(temporary,join(root,'evidence/status.json'))
}finally{await unlink(temporary).catch(()=>{})}
console.log(JSON.stringify({candidate,verification:snapshot.sources.evidence.status,records:observation?.records.length??null,reason:snapshot.sources.evidence.failure??null}))
if(snapshot.sources.evidence.status!=='ok')process.exitCode=2
