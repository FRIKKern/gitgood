import test from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'node:http'
import {readLedger,reconcileLedger,requirementIdentity} from './ledger-source.mjs'
const now=new Date('2026-10-08T22:00:00Z'),token='synthetic-ledger-token'
const requirements=requirementIdentity({journeys:[{id:'J01',milestone:'M2',spec:'spec'}]},()=>'- **J01-A:** Real criterion.\n')
const template={schemaVersion:1,workspace:'gitgood',workspaceId:'515e845b-2754-4963-93b7-e7486fb13646',project:'delivery',dataset:'production',goalId:'gitgood-first-release'}
const identity=()=>({id:'synthetic-id',workspace:{id:template.workspaceId,slug:'gitgood'},permissions:['read'],expires_at:'2026-10-15T22:00:00Z'})
const documents=()=>[{_id:template.goalId,_type:'task',_draft:false,_rev:'goal-revision'},
  {_id:'gitgood-j01',_type:'task',_draft:false,_rev:'journey-revision',parent_id:'gitgood-m2',lifecycle_status:'done',
    acceptance_criteria:[{criterion:'J01-A: Real criterion.',met:true,evidence:'claimed pass'}],
    gitgood:{journey:'J01',spec_sha256:requirements[0].sha256,implementation:{state:'implemented',reference:'https://github.com/FRIKKern/gitgood/pull/1',unexpected:'must not enter snapshot'}}}]
const page=docs=>({result:{documents:docs,count:docs.length,total:docs.length,offset:0,hasMore:false,perspective:'published'}})
async function fixture(t,{auth=identity(),data=page(documents()),redirect}={}){
  const requests=[]
  const server=createServer((request,response)=>{
    requests.push({url:request.url,authorization:request.headers.authorization})
    if(redirect){response.writeHead(302,{location:redirect});response.end();return}
    response.setHeader('content-type','application/json')
    response.end(JSON.stringify(request.url==='/v1/auth/token'?auth:data))
  })
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
  t.after(()=>new Promise(resolve=>server.close(resolve)))
  return {config:{...template,baseUrl:'http://127.0.0.1:'+server.address().port},requests}
}
const read=fixture=>readLedger({...fixture,token,requirements,now,allowInsecureLoopback:true})
test('actual HTTP source scope is explicit and completion cannot create verification',async t=>{
  const f=await fixture(t),observation=await read(f)
  assert.deepEqual(observation.records,[{id:'J01',implementation:{state:'implemented',reference:'https://github.com/FRIKKern/gitgood/pull/1'}}])
  assert(f.requests.every(request=>request.authorization==='Bearer '+token))
  assert(f.requests[1].url.startsWith('/w/gitgood/p/delivery/v1/data/query/production/task?'))
  assert.equal(observation.source.observedAt,now.toISOString())
  assert(!JSON.stringify(observation).includes(token))
  assert(!JSON.stringify(observation).includes('claimed pass'))
})
test('wrong workspace, admin identity and expired identity are refused before data reads',async t=>{
  for(const auth of [{...identity(),workspace:{id:template.workspaceId,slug:'outsider'}},
    {...identity(),permissions:['read','admin']},{...identity(),expires_at:'2026-10-07T00:00:00Z'}]){
    const f=await fixture(t,{auth});await assert.rejects(read(f),/ledger_identity_invalid/);assert.equal(f.requests.length,1)
  }
})
test('partial, duplicate and requirement-changed source observations cannot replace prior state',async t=>{
  const changed=documents();changed[1].gitgood.spec_sha256='changed'
  const criteria=documents();criteria[1].acceptance_criteria[0].criterion='J01-A: Different promise.'
  for(const data of [page(documents().slice(0,1)),page([...documents(),documents()[1]]),page(changed),page(criteria),
    {...page(documents()),result:{...page(documents()).result,total:99}}]){
    const f=await fixture(t,{data});await assert.rejects(read(f),/ledger_/)
  }
  const previous={headCommit:'a'.repeat(40),sources:{ledger:{status:'ok',observedAt:'2026-10-07T22:00:00Z',reference:'old'}},
    records:[{id:'J01',implementation:{state:'implemented',reference:'old'},verification:{state:'verified',reference:'protected-artifact'}}]}
  const failed=reconcileLedger(previous,{error:'ledger_requirement_mismatch',now,candidate:'b'.repeat(40)})
  assert.deepEqual(failed.records,previous.records)
  assert.equal(failed.sources.ledger.observedAt,previous.sources.ledger.observedAt)
  assert.equal(failed.sources.ledger.status,'unavailable')
  assert.equal(previous.headCommit,'a'.repeat(40))
})
test('redirects cannot forward the ledger bearer to another listener',async t=>{
  const destination=await fixture(t),source=await fixture(t,{redirect:destination.config.baseUrl})
  await assert.rejects(read(source),/ledger_request_failed/)
  assert.equal(destination.requests.length,0)
})
test('production configuration rejects insecure origins and bearer-bearing references',async t=>{
  const f=await fixture(t)
  await assert.rejects(readLedger({...f,token,requirements,now}),/ledger_origin_invalid/)
  const docs=documents();docs[1].gitgood.implementation.reference+='?token=private'
  const secret=await fixture(t,{data:page(docs)})
  await assert.rejects(read(secret),/ledger_reference_invalid/)
})
