import test from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'node:http'
import {createHash,randomUUID} from 'node:crypto'
import {canonical,validateEvaluation,readVerification,reconcileVerification} from './verification-source.mjs'
import {classify} from './model.mjs'
const hash=value=>createHash('sha256').update(value).digest('hex')
const now=new Date('2026-10-09T14:00:00.000Z')
const requirements=[{id:'J15',sha256:'b'.repeat(64),criteria:['J15-A: Activate.', 'J15-B: Refuse.', 'J15-C: Recover.']}]
const specRevision='sha256:'+hash(JSON.stringify({J15:requirements[0].sha256}))
const config={schemaVersion:1,baseUrl:'https://fixture.invalid',workspace:'gitgood',workspaceId:'515e845b-2754-4963-93b7-e7486fb13646',project:'delivery',dataset:'production',goalId:'gitgood-first-release'}
function manifest(sequence=1,outcome='passed'){
 const content='Retained synthetic public probe result.\n'
 return {schemaVersion:1,journey:'J15',sequence,codeCommit:'a'.repeat(40),specRevision,requirementSha256:requirements[0].sha256,
  evaluatedAt:now.toISOString(),evaluator:'Fixture explicit evaluator',environment:'Disposable loopback source and synthetic artifact',limitations:'Fixture proves collector rules, not an installed upgrade.',
  artifacts:[{id:'proof',name:'proof.txt',content,bytes:Buffer.byteLength(content),sha256:hash(content)}],
  criteria:requirements[0].criteria.map(item=>({id:item.split(': ')[0],outcome,observedAt:'2026-10-09T13:00:00.000Z',producer:'Fixture producer',command:['fixed fixture command'],artifactIds:['proof'],reason:'Fixture evaluation'}))}
}
const document=value=>({_id:'gitgood-verification-'+randomUUID(),_type:'gitgood_verification',_draft:false,_rev:randomUUID(),manifest:value,manifest_sha256:hash(canonical(value))})
async function fixture(t,docs,{identity,redirect,denied=false}={}){
 const requests=[]
 const server=createServer((request,response)=>{
  requests.push({url:request.url,authorization:request.headers.authorization})
  if(redirect){response.writeHead(302,{location:redirect});response.end();return}
  if(denied&&request.url!=='/v1/auth/token'){response.writeHead(403);response.end();return}
  response.setHeader('content-type','application/json')
  if(request.url==='/v1/auth/token')response.end(JSON.stringify(identity??{id:'fixture-reader',workspace:{id:config.workspaceId,slug:'gitgood'},permissions:['read'],expires_at:'2026-10-10T00:00:00.000Z'}))
  else{
   const offset=Number(new URL(request.url,'http://fixture').searchParams.get('offset')),documents=docs.slice(offset,offset+2)
   response.end(JSON.stringify({result:{documents,count:documents.length,total:docs.length,offset,hasMore:offset+documents.length<docs.length,perspective:'published'}}))
  }
 })
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)))
 return {config:{...config,baseUrl:'http://127.0.0.1:'+server.address().port},requests}
}
const read=f=>readVerification({...f,token:'fixture_private_token',requirements,now,allowInsecureLoopback:true})
function snapshot(){return {headCommit:'a'.repeat(40),specRevision,maxAgeHours:24,evaluatedAt:now.toISOString(),sources:{ledger:{status:'ok',observedAt:now.toISOString(),reference:'fixture'},evidence:{status:'ok',observedAt:now.toISOString(),reference:'fixture'},releases:{status:'unconfigured',observedAt:null}},records:[{id:'J15',implementation:{state:'in_progress',reference:'fixture'}}]}}

test('actual scoped HTTP verifies protected bytes and latest failed evaluation supersedes pass',async t=>{
 const docs=[document(manifest(2,'failed')),document(manifest(1)),document({...manifest(1),journey:'J15',sequence:3,criteria:manifest().criteria.map(item=>({...item,outcome:'inconclusive'}))})]
 const f=await fixture(t,docs),observed=await read(f)
 assert.equal(observed.records[0].verification.state,'inconclusive');assert.equal(observed.provenance.documentCount,3)
 assert(f.requests[1].url.startsWith('/w/gitgood/p/delivery/v1/data/query/production/gitgood_verification?'))
 assert(f.requests.every(item=>item.authorization==='Bearer fixture_private_token'))
 assert(!JSON.stringify(observed).includes('fixture_private_token'));assert(!JSON.stringify(observed).includes('Retained synthetic'))
 const onlyFailed=await fixture(t,docs.slice(0,2));assert.equal((await read(onlyFailed)).records[0].verification.state,'failed')
})
test('artifact corruption and falsely current requirement cannot satisfy an evaluation',()=>{
 for(const mutate of [value=>value.artifacts[0].content+='changed',value=>value.artifacts[0].bytes++,value=>value.requirementSha256='c'.repeat(64),value=>value.criteria.pop(),value=>value.criteria[0].artifactIds=['missing'],value=>value.criteria[0].observedAt='2026-10-09T15:00:00.000Z']){
  const value=manifest();mutate(value);assert.throws(()=>validateEvaluation(value,requirements,now),/verification_/)
 }
})
test('manifest checksum, duplicate sequence and protected-source denial preserve prior results',async t=>{
 const bad=document(manifest());bad.manifest_sha256='0'.repeat(64)
 for(const docs of [[bad],[document(manifest()),document(manifest())]]){
  const f=await fixture(t,docs);await assert.rejects(read(f),/verification_(manifest_integrity|sequence_conflict)/)
 }
 const previous=snapshot();previous.records[0].verification=validateEvaluation(manifest(),requirements,now)
 const retained=reconcileVerification(previous,{error:'verification_request_failed',now:new Date('2026-10-09T14:10:00.000Z'),candidate:'a'.repeat(40)})
 assert.deepEqual(retained.records,previous.records);assert.equal(retained.sources.evidence.observedAt,previous.sources.evidence.observedAt)
 assert.equal(classify(retained.records[0],retained,now).verification,'unknown')
})
test('changed code, changed spec and old proof remain stale after a fresh source read',()=>{
 for(const mutate of [value=>value.codeCommit='c'.repeat(40),value=>value.specRevision='sha256:'+'c'.repeat(64),value=>value.criteria.forEach(item=>item.observedAt='2026-10-07T13:00:00.000Z')]){
  const value=manifest();mutate(value);const verification=validateEvaluation(value,requirements,now),s=snapshot()
  s.records[0].verification={...verification,reference:'fixture:protected'}
  assert.equal(classify(s.records[0],s,now).verification,'stale')
 }
})
test('read cannot forward credentials on redirect or use an admin identity',async t=>{
 const target=await fixture(t,[]),source=await fixture(t,[],{redirect:target.config.baseUrl})
 await assert.rejects(read(source),/verification_request_failed/);assert.equal(target.requests.length,0)
 const admin=await fixture(t,[],{identity:{workspace:{id:config.workspaceId,slug:'gitgood'},permissions:['read','admin'],expires_at:'2026-10-10T00:00:00.000Z'}})
 await assert.rejects(read(admin),/verification_identity_invalid/);assert.equal(admin.requests.length,1)
})
test('actual empty published source removes current verification but retains implementation',async t=>{
 const f=await fixture(t,[]),observed=await read(f),s=snapshot();s.records[0].verification=validateEvaluation(manifest(),requirements,now)
 const next=reconcileVerification(s,{observation:observed,now,candidate:s.headCommit})
 assert.equal(next.records[0].implementation.state,'in_progress');assert.equal(next.records[0].verification,undefined)
 assert.equal(classify(next.records[0],next,now).verification,'absent')
})

test('actual source denial and changed or missing retained proof cannot renew known provenance',async t=>{
 const original=document(manifest()),f=await fixture(t,[original]),observed=await read(f)
 const previous=reconcileVerification(snapshot(),{observation:observed,now,candidate:'a'.repeat(40)})
 const denied=await fixture(t,[original],{denied:true});await assert.rejects(read(denied),/verification_http_403/)
 const changed=structuredClone(original);changed.manifest.artifacts[0].content='Changed retained bytes'
 changed.manifest.artifacts[0].bytes=Buffer.byteLength(changed.manifest.artifacts[0].content)
 changed.manifest.artifacts[0].sha256=hash(changed.manifest.artifacts[0].content);changed.manifest_sha256=hash(canonical(changed.manifest));changed._rev=randomUUID()
 for(const docs of [[changed],[]]){
  const replacement=await fixture(t,docs),next=reconcileVerification(previous,{observation:await read(replacement),now:new Date('2026-10-09T14:05:00.000Z'),candidate:'a'.repeat(40)})
  assert.equal(next.sources.evidence.status,'unavailable');assert.equal(next.sources.evidence.failure,'verification_retained_proof_changed')
  assert.equal(next.sources.evidence.observedAt,previous.sources.evidence.observedAt);assert.deepEqual(next.records,previous.records)
 }
})
