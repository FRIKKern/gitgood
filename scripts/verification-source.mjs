import {createHash} from 'node:crypto'
import {sourceReader} from './ledger-source.mjs'

const refuse=code=>{throw new Error('verification_'+code)}
const require=(value,code)=>{if(!value)refuse(code)}
const hash=value=>createHash('sha256').update(value).digest('hex')
const sha=value=>typeof value==='string'&&/^[0-9a-f]{64}$/.test(value)
const text=(value,max)=>typeof value==='string'&&value.trim().length>0&&Buffer.byteLength(value)<=max&&!value.includes('\0')
const closed=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&JSON.stringify(Object.keys(value).sort())===JSON.stringify([...keys].sort())
export function canonical(value){
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']'
  if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+canonical(value[key])).join(',')+'}'
  return JSON.stringify(value)
}
const timestamp=(value,now)=>typeof value==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value)&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString()===value&&Date.parse(value)<=now.getTime()

export function validateEvaluation(manifest,requirements,now=new Date()){
  require(closed(manifest,['schemaVersion','journey','sequence','codeCommit','specRevision','requirementSha256','evaluatedAt','evaluator','criteria','artifacts','environment','limitations']),'manifest_invalid')
  require(Buffer.byteLength(JSON.stringify(manifest))<=262144,'manifest_too_large')
  require(manifest.schemaVersion===1&&Number.isSafeInteger(manifest.sequence)&&manifest.sequence>0,'manifest_invalid')
  const requirement=requirements.find(item=>item.id===manifest.journey)
  require(requirement&&/^[0-9a-f]{40}$/.test(manifest.codeCommit)&&/^sha256:[0-9a-f]{64}$/.test(manifest.specRevision)&&sha(manifest.requirementSha256),'identity_invalid')
  const currentSpec='sha256:'+hash(JSON.stringify(Object.fromEntries(requirements.map(item=>[item.id,item.sha256]))))
  require(manifest.specRevision!==currentSpec||manifest.requirementSha256===requirement.sha256,'requirement_mismatch')
  require(timestamp(manifest.evaluatedAt,now)&&text(manifest.evaluator,256)&&text(manifest.environment,4096)&&text(manifest.limitations,4096),'evaluation_invalid')
  require(Array.isArray(manifest.artifacts)&&manifest.artifacts.length>0&&manifest.artifacts.length<=16,'artifacts_invalid')
  const artifacts=new Map();let total=0
  for(const artifact of manifest.artifacts){
    require(closed(artifact,['id','name','content','bytes','sha256'])&&text(artifact.id,64)&&/^[a-z0-9][a-z0-9_-]*$/.test(artifact.id)&&/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(artifact.name),'artifact_invalid')
    require(typeof artifact.content==='string'&&!artifact.content.includes('\0')&&Number.isInteger(artifact.bytes)&&artifact.bytes>0&&artifact.bytes<=65536&&sha(artifact.sha256),'artifact_invalid')
    const bytes=Buffer.from(artifact.content,'utf8');total+=bytes.length
    require(bytes.length===artifact.bytes&&hash(bytes)===artifact.sha256&&!artifacts.has(artifact.id)&&total<=131072,'artifact_integrity')
    artifacts.set(artifact.id,artifact)
  }
  require(Array.isArray(manifest.criteria)&&manifest.criteria.length===requirement.criteria.length,'criteria_incomplete')
  const ids=requirement.criteria.map(value=>value.split(': ')[0]),seen=new Set()
  for(const criterion of manifest.criteria){
    require(closed(criterion,['id','outcome','observedAt','producer','command','artifactIds','reason'])&&ids.includes(criterion.id)&&!seen.has(criterion.id),'criterion_invalid')
    seen.add(criterion.id)
    require(['passed','failed','inconclusive'].includes(criterion.outcome)&&timestamp(criterion.observedAt,now)&&Date.parse(criterion.observedAt)<=Date.parse(manifest.evaluatedAt),'criterion_invalid')
    require(text(criterion.producer,256)&&text(criterion.reason,4096)&&Array.isArray(criterion.command)&&criterion.command.length>0&&criterion.command.length<=16&&criterion.command.every(value=>text(value,2048)),'criterion_invalid')
    require(Array.isArray(criterion.artifactIds)&&criterion.artifactIds.length>0&&new Set(criterion.artifactIds).size===criterion.artifactIds.length&&criterion.artifactIds.every(id=>artifacts.has(id)),'criterion_artifact_missing')
  }
  const state=manifest.criteria.some(item=>item.outcome==='failed')?'failed':manifest.criteria.every(item=>item.outcome==='passed')?'verified':'inconclusive'
  return {state,passed:state==='verified',codeCommit:manifest.codeCommit,specRevision:manifest.specRevision,
    requirementSha256:manifest.requirementSha256,observedAt:manifest.criteria.map(item=>item.observedAt).sort()[0],
    evaluatedAt:manifest.evaluatedAt,sequence:manifest.sequence,evaluator:manifest.evaluator,
    manifestSha256:hash(canonical(manifest)),artifacts:manifest.artifacts.map(({content,...metadata})=>metadata),
    criteria:manifest.criteria.map(({command,...criterion})=>criterion)}
}

export async function readVerification(options){
  const {requirements,now=new Date()}=options
  let reader
  try{reader=await sourceReader(options)}catch(error){refuse(error.message.replace(/^ledger_/,''))}
  const {base,get,identity,scope,documentScope}=reader
  const docs=[],seen=new Set();let offset=0,total=null
  while(true){
    const query=new URLSearchParams({limit:'2',offset:String(offset),count:'true',fields:'manifest,manifest_sha256'})
    let body
    try{body=await get(scope+'/gitgood_verification?'+query)}catch(error){refuse(error.message.replace(/^ledger_/,''))}
    const result=body.result
    require(result&&Array.isArray(result.documents)&&result.documents.length<=2&&result.count===result.documents.length&&result.offset===offset&&Number.isInteger(result.total)&&result.total>=0&&result.total<=128&&typeof result.hasMore==='boolean'&&result.perspective==='published','page_invalid')
    require(total===null||total===result.total,'changed_during_read');total=result.total
    for(const doc of result.documents){
      require(doc&&/^gitgood-verification-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(doc._id)&&doc._type==='gitgood_verification'&&doc._draft===false&&text(doc._rev,256)&&!seen.has(doc._id),'record_invalid')
      seen.add(doc._id);docs.push(doc)
    }
    offset+=result.count
    if(!result.hasMore)break
    require(result.count>0&&offset<total,'page_invalid')
  }
  require(docs.length===total,'incomplete')
  const latest=new Map(),sequences=new Set(),provenance=[]
  for(const doc of docs){
    const value=validateEvaluation(doc.manifest,requirements,now)
    require(doc.manifest_sha256===value.manifestSha256,'manifest_integrity')
    const key=doc.manifest.journey+':'+value.sequence;require(!sequences.has(key),'sequence_conflict');sequences.add(key)
    const record={id:doc.manifest.journey,verification:{...value,reference:base.origin+documentScope+'/gitgood_verification/'+doc._id}}
    if(!latest.has(record.id)||latest.get(record.id).verification.sequence<value.sequence)latest.set(record.id,record)
    provenance.push({id:doc._id,revision:doc._rev,manifestSha256:value.manifestSha256})
  }
  return {records:requirements.filter(item=>latest.has(item.id)).map(item=>latest.get(item.id)),
    source:{status:'ok',observedAt:now.toISOString(),reference:base.origin+scope+'/gitgood_verification'},
    provenance:{tokenId:identity.id,workspaceId:options.config.workspaceId,documentCount:docs.length,revisions:provenance.sort((a,b)=>a.id.localeCompare(b.id))}}
}

export function reconcileVerification(previous,{observation,error,now=new Date(),candidate}){
  const snapshot=structuredClone(previous);snapshot.evaluatedAt=now.toISOString();snapshot.headCommit=candidate
  if(!error){
    const current=new Map(observation.provenance.revisions.map(item=>[item.id,item.manifestSha256]))
    if(previous.sources.evidence.receipts?.some(item=>current.get(item.id)!==item.manifestSha256))error='verification_retained_proof_changed'
  }
  if(error){snapshot.sources.evidence={...snapshot.sources.evidence,status:'unavailable',failure:error};return snapshot}
  snapshot.sources.evidence={...observation.source,receipts:observation.provenance.revisions.map(({revision,...receipt})=>receipt)}
  const observed=new Map(observation.records.map(record=>[record.id,record]))
  snapshot.records=snapshot.records.map(record=>{
    const {verification,...rest}=record
    return {...rest,...observed.get(record.id)}
  })
  return snapshot
}
