import test from 'node:test'
import assert from 'node:assert/strict'
import {validate, classify, releaseProblems} from './model.mjs'
import {journeySvg as svg, svg as gantt, overviewSvg, changelog, status} from './render.mjs'
const now=new Date('2026-10-07T12:00:00Z')
const clone=()=>({
  catalog:{schemaVersion:1,journeys:[{id:'J01',milestone:'M1',title:'Fixture journey',required:true,spec:'docs/journeys/J01.md'}]},
  milestones:{schemaVersion:1,milestones:[
    {id:'M0',title:'Fixture foundation',dependsOn:[],work:'Define',exit:'Accepted'},
    {id:'M1',title:'Fixture slice',dependsOn:['M0'],work:'Build',exit:'Verified'}
  ]},
  snapshot:{schemaVersion:1,baseline:'planning-2026-10-07',headCommit:null,specRevision:'planning-2026-10-07',maxAgeHours:24,
    sources:Object.fromEntries(['ledger','evidence','releases'].map(k=>[k,{status:'unconfigured',observedAt:null}])),records:[]},
  releases:{schemaVersion:1,releases:[]},
  fragments:[{id:'planning-foundation',category:'Added',summary:'Fixture planning entry.',impact:'planning',references:['PRODUCT.md'],journeys:[],withdrawn:false}]
})
function connected(){
  const m=clone()
  m.snapshot.headCommit='a'.repeat(40)
  m.snapshot.evaluatedAt=now.toISOString()
  for(const k of ['ledger','evidence','releases'])m.snapshot.sources[k]={status:'ok',observedAt:now.toISOString(),reference:'fixture:'+k}
  return m
}
const record=()=>({id:'J01',implementation:{state:'implemented',reference:'fixture:task'},
verification:{state:'verified',passed:true,reference:'fixture:manifest',codeCommit:'a'.repeat(40),specRevision:'planning-2026-10-07'},
release:{state:'released',accepted:true,version:'0.1.0',reference:'fixture:release',codeCommit:'a'.repeat(40)}})
test('compact overview cannot silently omit or reorder new milestone scope',()=>{
  const m=clone()
  m.milestones.milestones=Array.from({length:8},(_,i)=>({id:'M'+i}))
  assert.match(overviewSvg(m),/Planned sequence/)
  m.milestones.milestones.push({id:'M8'})
  assert.throws(()=>overviewSvg(m),/Update the README overview grouping/)
  m.milestones.milestones.pop()
  m.milestones.milestones.reverse()
  assert.throws(()=>overviewSvg(m),/Update the README overview grouping/)
})
test('unconfigured inputs do not become zero or verified',()=>{
  const m=clone()
  assert.deepEqual(validate(m,now),[])
  assert.deepEqual(classify(undefined,m.snapshot,now),{implementation:'unknown',verification:'unknown',release:'unknown'})
  assert.match(svg(m),/Implemented: 0 confirmed · 1 unknown or stale/)
  assert.match(svg(m),/Status source not connected/)
  assert.ok(releaseProblems(m,now).length)
})
test('task completion alone cannot establish verification or release',()=>{
  const m=connected()
  const s=classify({id:'J01',implementation:record().implementation},m.snapshot,now)
  assert.equal(s.implementation,'implemented')
  assert.equal(s.verification,'absent')
  assert.equal(s.release,'unknown')
})
test('matching evidence and publication remain separate states',()=>{
  const m=connected(),r=record();m.snapshot.records=[r]
  assert.deepEqual(validate(m,now),[])
  assert.deepEqual(classify(r,m.snapshot,now),{implementation:'implemented',verification:'verified',release:'released'})
  delete r.release
  assert.equal(classify(r,m.snapshot,now).release,'unknown')
})
test('code or spec changes make prior verification stale',()=>{
  const m=connected(),r=record()
  m.snapshot.headCommit='b'.repeat(40)
  assert.equal(classify(r,m.snapshot,now).verification,'stale')
  assert.equal(classify(r,m.snapshot,now).release,'stale')
  m.snapshot.headCommit='a'.repeat(40);m.snapshot.specRevision='new-spec'
  assert.equal(classify(r,m.snapshot,now).verification,'stale')
})
test('expired source data cannot pass the release gate',()=>{
  const m=connected(),r=record();m.snapshot.records=[r]
  const later=new Date('2026-10-09T12:00:00Z')
  assert.equal(classify(r,m.snapshot,later).verification,'stale')
  assert.ok(releaseProblems(m,later).some(x=>x.includes('Source is not current')))
})
test('unavailable source preserves last-known record without asserting success',()=>{
  const m=connected(),r=record();m.snapshot.sources.evidence.status='unavailable'
  assert.equal(classify(r,m.snapshot,now).verification,'unknown')
  assert.equal(r.verification.state,'verified')
})
test('malformed timestamps and proof-free claims are rejected',()=>{
  const m=connected();m.snapshot.sources.ledger.observedAt='tomorrow'
  assert.ok(validate(m,now).some(x=>x.includes('timestamp')))
  const m2=connected(),r=record();delete r.verification.reference;m2.snapshot.records=[r]
  assert.ok(validate(m2,now).length)
})
test('duplicate IDs and circular milestone dependencies are rejected',()=>{
  const m=clone();m.catalog.journeys.push(m.catalog.journeys[0])
  assert.ok(validate(m,now).some(x=>x.includes('Duplicate journey')))
  const n=clone();n.milestones.milestones[0].dependsOn=['M1']
  assert.ok(validate(n,now).some(x=>x.includes('Cyclic')))
})
test('SVG output is deterministic and escapes injected labels',()=>{
  const m=clone();m.milestones.milestones[0].title='<script>alert("x")</script>'
  assert.equal(svg(m),svg(m))
  assert.ok(!svg(m).includes('<script>'))
  assert.match(svg(m),/&lt;script&gt;/)
})

test('roadmap shows partial evidence without turning unknown into zero',()=>{
  const m=connected();m.snapshot.records=[record()]
  m.catalog.journeys.push({id:'J02',milestone:'M1',title:'Second journey',required:true,spec:'docs/journeys/J02.md'})
  const out=svg(m)
  assert.match(out,/Implemented: 1 confirmed · 1 unknown or stale/)
  assert.match(out,/Verified: 1 of 2 journeys/)
  assert.match(out,/Released: 1 confirmed · 1 unknown or stale/)
  assert.match(out,/J02 Second journey\. Implemented: unknown; Verified: absent; Released: unknown/)
  assert.equal((out.match(/data-journey=/g)||[]).length,2)
  assert.match(out,/Milestone exit gates are not inferred from journey counts/)
})

test('roadmap exposes stale and unavailable sources without a success display',()=>{
  const m=connected();m.snapshot.records=[record()]
  m.snapshot.sources.evidence.observedAt='2026-10-05T12:00:00Z'
  m.snapshot.sources.releases.status='unavailable'
  const out=svg(m)
  assert.match(out,/Verified: 0 confirmed · 1 unknown or stale/)
  assert.match(out,/data-state="stale"/)
  assert.match(out,/evidence: stale/)
  assert.match(out,/Status source unavailable/)
  assert.match(out,/Released: unknown/)
})

test('roadmap expands for growing catalogs and preserves every journey',()=>{
  const m=clone(), before=Number(svg(m).match(/height="(\d+)"/)[1])
  m.milestones.milestones[1].title='An unusually long phase title that wraps without hiding the rest'
  m.catalog.journeys=Array.from({length:90},(_,i)=>({id:'J'+String(i+1).padStart(2,'0'),milestone:'M1',title:'A long journey description with important recovery behavior',required:true,spec:'fixture'}))
  const out=svg(m)
  assert.ok(Number(out.match(/height="(\d+)"/)[1])>before)
  assert.equal((out.match(/data-journey=/g)||[]).length,90)
  assert.ok(!/width="-/.test(out))
  assert.match(out,/data-journey="J90"/)
})
test('release notes select included fragments and omit withdrawals',()=>{
  const m=clone()
  m.fragments.push({id:'withdrawn-fix',category:'Fixed',summary:'Must not publish',impact:'product',references:['PRODUCT.md'],journeys:[],withdrawn:true})
  m.releases.releases=[{version:'0.1.0',date:'2026-10-07',commit:'a'.repeat(40),fragments:['planning-foundation'],upgrade:'Back up before migration.'}]
  assert.deepEqual(validate(m,now),[])
  const out=changelog(m)
  assert.ok(!out.body.includes('Must not publish'))
  assert.match(out.body,/Back up before migration/)
  assert.match(out.highlights,/0.1.0/)
  assert.equal(out.body,changelog(m).body)
})

test('README stays bounded while the changelog preserves grouped development history',()=>{
  const m=clone()
  m.fragments=Array.from({length:200},(_,i)=>({id:'fixture-'+i,category:i%2?'Fixed':'Added',summary:'Detailed change '+i+'. '+('Context '.repeat(80)),impact:'product',references:['PRODUCT.md'],journeys:[],withdrawn:false}))
  m.fragments.push({id:'withdrawn-fixture',category:'Security',summary:'Withdrawn change',impact:'product',references:['PRODUCT.md'],journeys:[],withdrawn:true})
  const out=changelog(m)
  assert.match(out.highlights,/200 development changes/)
  assert.match(out.highlights,/CHANGELOG\.md#unreleased/)
  assert.match(out.highlights,/No Gitgood application release has been published/)
  assert.ok(out.highlights.length<400)
  assert.ok(!out.highlights.includes('Detailed change'))
  assert.match(out.body,/### Added\n/)
  assert.match(out.body,/### Fixed\n/)
  assert.ok(!out.body.includes('Withdrawn change'))
  for(let i=0;i<200;i++) assert.equal(out.body.split('Detailed change '+i+'. ').length,2)
  assert.equal((out.body.match(/\]\(PRODUCT\.md\)/g)??[]).length,200)
})

test('README handles empty development history and lengthy published notes without growing',()=>{
  const m=clone()
  assert.match(changelog(m).highlights,/1 development change is/)
  m.fragments[0].withdrawn=true
  assert.match(changelog(m).highlights,/No pending changelog entries/)
  m.fragments[0].withdrawn=false
  m.fragments[0].summary='Long published detail '.repeat(200)
  m.releases.releases=[{version:'0.1.0',date:'2026-10-07',commit:'a'.repeat(40),fragments:['planning-foundation']}]
  const out=changelog(m)
  assert.match(out.highlights,/0\.1\.0 — 2026-10-07/)
  assert.ok(out.highlights.length<400)
  assert.ok(out.body.includes(m.fragments[0].summary))
})

test('human progress report keeps unknown states and exposes its observation boundary',()=>{
  const m=clone(), out=status(m)
  assert.match(out,/No candidate recorded/)
  assert.match(out,/does not prove the current main branch or any open development branch/)
  assert.match(out,/not at the moment you opened this page/)
  assert.match(out,/\| Implementation \| 0 complete · 1 unknown \|/)
  assert.match(out,/\| Verification \| 0 passed · 1 unknown \|/)
  assert.match(out,/\| Release \| 0 confirmed published · 1 unknown \|/)
  assert.match(out,/\| J01 \| Unknown \| Unknown \| Unknown \|/)
  assert.match(out,/\| Verification evidence \| Not connected \| Not observed \|/)
  assert.equal(out,status(m))
})

test('human progress report preserves candidate mismatches, partial work and unavailable sources',()=>{
  const m=connected();m.snapshot.records=[record()]
  let out=status(m)
  assert.match(out,/\| J01 \| Complete \| Passed \| Published \|/)
  assert.ok(out.includes('a'.repeat(40)))
  assert.ok(out.includes(now.toISOString()))
  m.snapshot.headCommit='b'.repeat(40)
  m.catalog.journeys.push({id:'J02',milestone:'M1',title:'Unfinished journey',required:true,spec:'docs/journeys/J02.md'})
  m.snapshot.records.push({id:'J02',implementation:{state:'in_progress',reference:'fixture:task'}})
  out=status(m)
  assert.match(out,/\| J01 \| Complete \| Needs recheck \| Needs recheck \|/)
  assert.match(out,/\| J02 \| In progress \| No evidence \| Unknown \|/)
  assert.match(out,/\| Implementation \| 1 complete · 1 in progress \|/)
  assert.match(out,/\| Verification \| 0 passed · 1 no evidence · 1 needs recheck \|/)
  m.snapshot.sources.evidence.status='unavailable'
  out=status(m)
  assert.match(out,/\| Verification evidence \| Unavailable \|/)
  assert.match(out,/\| J01 \| Complete \| Unknown \| Needs recheck \|/)
  assert.ok(!out.includes('| Passed |'))
})

test('human progress summary accounts for every known state without inventing zero failures',()=>{
  const m=connected()
  m.catalog.journeys=Array.from({length:6},(_,i)=>({id:'J0'+(i+1),milestone:'M1',title:'Journey '+(i+1),required:true,spec:'docs/journeys/J0'+(i+1)+'.md'}))
  m.snapshot.records=[
    record(),
    {id:'J02',implementation:{state:'in_progress',reference:'fixture:task'}},
    {id:'J03',implementation:{state:'planned',reference:'fixture:task'},verification:{state:'failed',reference:'fixture:assessment'}},
    {id:'J04',implementation:{state:'in_progress',reference:'fixture:task'},verification:{state:'inconclusive',reference:'fixture:assessment'}},
    {...record(),id:'J05',verification:{...record().verification,codeCommit:'b'.repeat(40)},release:undefined}
  ]
  const out=status(m)
  assert.match(out,/\| Implementation \| 2 complete · 2 in progress · 1 planned · 1 unknown \|/)
  assert.match(out,/\| Verification \| 1 passed · 1 failed · 1 inconclusive · 2 no evidence · 1 needs recheck \|/)
  assert.match(out,/\| Release \| 1 confirmed published · 5 unknown \|/)
  assert.ok(!status(clone()).includes('0 failed'))
  assert.ok(!status(clone()).includes('0 no evidence'))
})

test('Gantt spans use milestone IDs and stay distinct from completion',()=>{
  const m=clone()
  m.milestones.supportTracks=[{id:'R1',title:'Early experiment',surface:'Disposable fixtures',start:'M0',end:'M1',kind:'research',note:'Proposed overlap'}]
  assert.deepEqual(validate(m,now),[])
  const out=gantt(m)
  assert.equal((out.match(/data-phase=/g)||[]).length,2)
  assert.match(out,/data-track="R1"/)
  assert.match(out,/Equal columns ≠ equal durations/)
  assert.match(out,/Bars show the plan, not verified completion/)
  assert.match(out,/Implemented: 0 confirmed · 1 unknown or stale/)
  assert.equal(out,gantt(m))
  m.milestones.supportTracks[0].end='M99'
  assert.ok(validate(m,now).some(e=>e.includes('support track span')))
  m.milestones.supportTracks[0].start='M1';m.milestones.supportTracks[0].end='M0'
  assert.ok(validate(m,now).some(e=>e.includes('support track span')))
})

test('Gantt rejects dependency order drift and escapes every displayed label',()=>{
  const m=clone();m.milestones.milestones.reverse()
  assert.ok(validate(m,now).some(e=>e.includes('order must follow dependencies')))
  m.milestones.milestones.reverse()
  m.milestones.milestones[0].surface='<script>bad()</script>'
  const out=gantt(m)
  assert.ok(!out.includes('<script>'))
  assert.match(out,/&lt;script&gt;bad\(\)&lt;\/script&gt;/)
})
test('double-assigned or withdrawn release entries are rejected',()=>{
  const m=clone(),release={version:'0.1.0',date:'2026-10-07',commit:'a'.repeat(40),fragments:['planning-foundation']}
  m.releases.releases=[release,{...release,version:'0.2.0'}]
  assert.ok(validate(m,now).some(x=>x.includes('assigned twice')))
  m.releases.releases=[release];m.fragments[0].withdrawn=true
  assert.ok(validate(m,now).some(x=>x.includes('withdrawn')))
})
