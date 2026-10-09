import {createHash} from 'node:crypto'

const hash=value=>createHash('sha256').update(value).digest('hex')
const refuse=code=>{throw new Error(code)}
const states=new Set(['planned','in_progress','implemented'])
export function requirementIdentity(catalog,readSpec){
  return catalog.journeys.map(journey=>{
    const spec=readSpec(journey.spec)
    return {...journey,sha256:hash(spec),criteria:[...spec.matchAll(/^- \*\*(J\d\d-[A-Z]):\*\* (.+)$/gm)].map(([,id,text])=>id+': '+text.trim())}
  })
}
export async function sourceReader({config,token,now=new Date(),allowInsecureLoopback=false}){
  if(config.schemaVersion!==1||typeof config.workspaceId!=='string'||!/^[0-9a-f-]{36}$/.test(config.workspaceId)||
    !token||typeof token!=='string'||/[\r\n]/.test(token))refuse('ledger_configuration_invalid')
  const base=new URL(config.baseUrl)
  if(base.username||base.password||base.search||base.hash||base.pathname!=='/'||
    !(base.protocol==='https:'||allowInsecureLoopback&&base.protocol==='http:'&&base.hostname==='127.0.0.1'))refuse('ledger_origin_invalid')
  for(const key of ['workspace','project','dataset','goalId'])if(typeof config[key]!=='string'||!/^[a-z0-9][a-z0-9-]*$/.test(config[key]))refuse('ledger_configuration_invalid')
  async function get(path){
    let response
    try{response=await fetch(new URL(path,base),{headers:{authorization:'Bearer '+token,accept:'application/json'},redirect:'error',signal:AbortSignal.timeout(12000)})}
    catch{refuse('ledger_request_failed')}
    if(!response.ok)refuse('ledger_http_'+response.status)
    if(!/^application\/json(?:;|$)/i.test(response.headers.get('content-type')??''))refuse('ledger_response_invalid')
    const reader=response.body.getReader(),chunks=[];let bytes=0
    try{
      while(true){const result=await reader.read();if(result.done)break;bytes+=result.value.length;if(bytes>1048576)refuse('ledger_response_too_large');chunks.push(result.value)}
      return JSON.parse(Buffer.concat(chunks).toString('utf8'))
    }catch{refuse('ledger_response_invalid')}finally{await reader.cancel().catch(()=>{})}
  }
  const identity=await get('/v1/auth/token')
  if(identity.workspace?.id!==config.workspaceId||identity.workspace.slug!==config.workspace||
    !Array.isArray(identity.permissions)||!identity.permissions.includes('read')||identity.permissions.includes('admin')||
    !identity.expires_at||Date.parse(identity.expires_at)<=now.getTime()||!Number.isFinite(Date.parse(identity.expires_at)))refuse('ledger_identity_invalid')
  return {base,identity,get,scope:'/w/'+config.workspace+'/p/'+config.project+'/v1/data/query/'+config.dataset,
    documentScope:'/w/'+config.workspace+'/p/'+config.project+'/v1/data/doc/'+config.dataset}
}
export async function readLedger(options){
  const {config,requirements,now=new Date()}=options
  const {base,identity,get,scope:rootScope}=await sourceReader(options)
  const scope=rootScope+'/task'
  const docs=[],seen=new Set();let offset=0,total=null
  while(true){
    const query=new URLSearchParams({limit:'100',offset:String(offset),count:'true',fields:'gitgood,parent_id,acceptance_criteria,lifecycle_status,labels'})
    const body=await get(scope+'?'+query),result=body.result
    if(!result||!Array.isArray(result.documents)||result.documents.length>100||result.count!==result.documents.length||result.offset!==offset||
      !Number.isInteger(result.total)||result.total<0||result.total>1000||typeof result.hasMore!=='boolean'||result.perspective!=='published')refuse('ledger_page_invalid')
    if(total!==null&&total!==result.total)refuse('ledger_changed_during_read')
    total=result.total
    for(const doc of result.documents){
      if(!doc||typeof doc._id!=='string'||seen.has(doc._id)||doc._type!=='task'||doc._draft!==false||typeof doc._rev!=='string')refuse('ledger_record_invalid')
      seen.add(doc._id);docs.push(doc)
    }
    offset+=result.count
    if(!result.hasMore)break
    if(result.count===0||offset>=total)refuse('ledger_page_invalid')
  }
  if(docs.length!==total||!seen.has(config.goalId))refuse('ledger_incomplete')
  const byId=new Map(docs.map(doc=>[doc._id,doc])),records=[]
  for(const journey of requirements){
    const doc=byId.get('gitgood-'+journey.id.toLowerCase()),provenance=doc?.gitgood
    if(!doc||provenance?.journey!==journey.id||provenance.spec_sha256!==journey.sha256||
      doc.parent_id!=='gitgood-'+journey.milestone.toLowerCase()||!states.has(provenance.implementation?.state)||
      typeof provenance.implementation.reference!=='string'||!provenance.implementation.reference.startsWith('https://github.com/FRIKKern/gitgood/')||
      !Array.isArray(doc.acceptance_criteria)||JSON.stringify(doc.acceptance_criteria.map(item=>item.criterion))!==JSON.stringify(journey.criteria))refuse('ledger_requirement_mismatch')
    const reference=new URL(provenance.implementation.reference)
    if(reference.origin!=='https://github.com'||reference.username||reference.password||reference.search||reference.hash||
      !reference.pathname.startsWith('/FRIKKern/gitgood/'))refuse('ledger_reference_invalid')
    records.push({id:journey.id,implementation:{state:provenance.implementation.state,reference:reference.href}})
  }
  return {records,source:{status:'ok',observedAt:now.toISOString(),reference:base.origin+'/w/'+config.workspace+'/p/'+config.project+'/studio'},
    provenance:{tokenId:identity.id,workspaceId:config.workspaceId,goalId:config.goalId,documentCount:docs.length,
      revisions:docs.map(doc=>({id:doc._id,revision:doc._rev})).sort((a,b)=>a.id.localeCompare(b.id))}}
}
export function reconcileLedger(previous,{observation,error,now=new Date(),candidate}){
  const snapshot=structuredClone(previous);snapshot.evaluatedAt=now.toISOString();snapshot.headCommit=candidate
  if(error){snapshot.sources.ledger={...snapshot.sources.ledger,status:'unavailable',failure:error};return snapshot}
  snapshot.sources.ledger=observation.source
  const existing=new Map(snapshot.records.map(record=>[record.id,record]))
  snapshot.records=observation.records.map(record=>({...existing.get(record.id),...record}))
  return snapshot
}
