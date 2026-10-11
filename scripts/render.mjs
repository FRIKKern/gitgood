import {classify, freshness} from './model.mjs'

export {svg} from './delivery-svg.mjs'
export {svg as journeySvg} from './roadmap-svg.mjs'
export {svg as overviewSvg} from './overview-svg.mjs'
export const escapeXml = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]))
const md = s => String(s).replace(/\|/g, '\\|').replace(/\r?\n/g, ' ')
const categories = ['Security', 'Added', 'Changed', 'Fixed', 'Deprecated', 'Removed']

export function roadmap(m) {
  const phases = m.milestones.milestones.map(p => '### '+p.id+' · '+p.title+'\n\n**Where:** '+(p.surface??'See the work below')+'\n\n'+p.work+'\n\n**Ready when:** '+p.exit).join('\n\n')
  const tracks = (m.milestones.supportTracks ?? []).map(t => '| '+md(t.title)+' | '+t.start+'–'+t.end+' | '+md(t.surface)+' |').join('\n')
  return '# Delivery roadmap\n\nThe route from a private repository to a complete, recoverable forge. Each milestone describes what you should see, where it appears, and what must pass before we advance.\n\n[Full Gantt](images/roadmap.svg) · [Progress snapshot](STATUS.md) · [What to build next](EXECUTION.md) · [Documentation guide](README.md)\n\n## How to read this plan\n\nMilestones follow dependency order. Their widths in the Gantt do not represent duration, and its bars show planned work rather than completion. There are no calendar promises in this view; re-estimate timing after M2 and M3.\n\n'+m.milestones.milestones.filter(p=>p.delivery).map(p=>'- **'+p.id+' — '+p.delivery+':** '+p.surface+'.').join('\n')+'\n\n## Milestones\n\n'+phases+'\n\n## Work that spans milestones\n\nResearch can start early when capacity allows. Its experiment does not complete the later product requirement; full installation and recovery acceptance remains at M6.\n\n| Work | Stages | Where |\n|---|---|---|\n'+tracks+'\n\n'+(m.milestones.supportTracks??[]).map(t=>'- **'+t.title+':** '+t.note).join('\n')+'\n\n## What counts as complete\n\nEach milestone must meet its own exit conditions. M0, M1 and M7 have requirements beyond journey counts. Code browsing (J04) starts at M2 and reaches its full scope at M4.\n\nUse the [journey specifications](../JOURNEYS.md) and [quality rules](../QUALITY.md) to assess completion. The [progress snapshot](STATUS.md) reports observed evidence separately from this plan.\n\nGenerated from [the milestone catalog](milestones.json); edit that source to change this roadmap.\n'
}

export function index(m) {
  return '# Product journeys\n\nA journey is a task a person must be able to complete from beginning to end, such as pushing code, reviewing a change, or restoring a lost host. These '+m.catalog.journeys.length+' specifications define the product we are building.\n\n[Product scope](PRODUCT.md) · [Delivery roadmap](docs/ROADMAP.md) · [Progress snapshot](docs/STATUS.md) · [Documentation guide](docs/README.md)\n\nOpen a journey to see its scenarios and acceptance criteria. The first milestone tells you when work begins; it does not claim that the journey is complete. Code browsing (J04) begins at M2 and continues through M4.\n\n| What you can do | ID | First milestone | Required for release |\n|---|---|---|---|\n'+m.catalog.journeys.map(j=>'| ['+md(j.title)+']('+j.spec+') | '+j.id+' | '+j.milestone+' | '+(j.required?'Yes':'No')+' |').join('\n')+'\n\nImplementation, verification and release are separate. Consult the [progress snapshot](docs/STATUS.md) for their recorded states and [quality rules](QUALITY.md) for the evidence required to advance. Live work is tracked in the ledger described by the [tracking contract](docs/TRACKING.md).\n\nGenerated from [the journey catalog](docs/journeys/catalog.json). Each linked specification owns its acceptance criteria.\n'
}

const stateLabels = {
  planned:'Planned', in_progress:'In progress', implemented:'Complete',
  verified:'Passed', failed:'Failed', inconclusive:'Inconclusive', absent:'No evidence',
  released:'Published', unknown:'Unknown', stale:'Needs recheck'
}
const sourceLabels = {
  current:'Current at snapshot time', stale:'Expired at snapshot time',
  unavailable:'Unavailable', unconfigured:'Not connected'
}

export function status(m) {
  const snapshot=m.snapshot
  const clock=new Date(snapshot.evaluatedAt??'2026-10-07T00:00:00Z')
  const states=m.catalog.journeys.map(j=>({journey:j, state:classify(snapshot.records.find(r=>r.id===j.id),snapshot,clock)}))
  const assessments=[
    ['implementation','Implementation',[
      ['implemented','complete'],['in_progress','in progress'],['planned','planned'],['stale','needs recheck'],['unknown','unknown']
    ]],
    ['verification','Verification',[
      ['verified','passed'],['failed','failed'],['inconclusive','inconclusive'],['absent','no evidence'],['stale','needs recheck'],['unknown','unknown']
    ]],
    ['release','Release',[
      ['released','confirmed published'],['stale','needs recheck'],['unknown','unknown']
    ]]
  ]
  const summaries=assessments.map(([key,label,outcomes])=>{
    const counts=outcomes.map(([outcome,description],index)=>{
      const count=states.filter(({state})=>state[key]===outcome).length
      return count||index===0?count+' '+description:null
    }).filter(Boolean)
    return '| '+label+' | '+counts.join(' · ')+' |'
  }).join('\n')
  const candidate=snapshot.headCommit?'[`'+snapshot.headCommit+'`](https://github.com/FRIKKern/gitgood/commit/'+snapshot.headCommit+')':'No candidate recorded'
  const ledger=snapshot.sources.ledger.reference
  const live=typeof ledger==='string'&&ledger.startsWith('https://')?'[Open the live delivery ledger]('+ledger+')':'See the [tracking contract](TRACKING.md) for ledger setup'
  const sources=[['ledger','Implementation ledger'],['evidence','Verification evidence'],['releases','Release records']]
    .map(([key,label])=>'| '+label+' | '+sourceLabels[freshness(snapshot,key,clock)]+' | '+md(snapshot.sources[key].observedAt??'Not observed')+' |').join('\n')
  const rows=states.map(({journey:j,state:s})=>'| ['+md(j.title)+'](../'+j.spec+') | '+j.id+' | '+stateLabels[s.implementation]+' | '+stateLabels[s.verification]+' | '+stateLabels[s.release]+' |').join('\n')
  return '# Progress snapshot\n\nThis page is a saved observation of the delivery ledger and evidence. **It does not prove the current main branch or any open development branch.** It stays unchanged until the reporting inputs are refreshed and regenerated.\n\n'+live+' · [Delivery roadmap](ROADMAP.md) · [Execution order](EXECUTION.md) · [Documentation guide](README.md)\n\n## What this snapshot says\n\n| Assessment | Saved result |\n|---|---|\n'+summaries+'\n\nThese counts assess all '+states.length+' product journeys end to end. A feature can have working code and passing component tests while its full journey is still in progress. Unknown and expired information cannot establish completion.\n\n- **Implemented:** the ledger records the complete journey as built.\n- **Verified:** recorded evidence passes the journey for this exact candidate and specification.\n- **Released:** a matching publication record exists and verification still passes.\n\n## Candidate and observation time\n\n- **Snapshot evaluated at:** '+md(snapshot.evaluatedAt??'Not recorded')+'.\n- **Candidate covered:** '+candidate+'.\n- **Freshness window:** '+snapshot.maxAgeHours+' hours.\n\nAll states below were evaluated at the saved snapshot time, not at the moment you opened this page. Run `npm run status` for an age check now. A fresh ledger read cannot make an older proof current.\n\n| Source | State at snapshot time | Last observation (UTC) |\n|---|---|---|\n'+sources+'\n\n## Journey by journey\n\n| What you can do | ID | Implementation | Verification | Release |\n|---|---|---|---|---|\n'+rows+'\n\n**Needs recheck** means the source or proof is expired, or the evidence no longer matches the candidate/specification. **Unknown** means the source is disconnected, unavailable, or has no declared result. **No evidence** means the connected evidence source has no result for that journey. **Inconclusive** means a recorded assessment did not establish a pass.\n\n## Refresh and inspect\n\nFollow the [tracking contract](TRACKING.md) to collect observations with the scoped credential. Run `npm run generate` and `npm run check` after collection. The [detailed evidence map](images/journey-evidence.svg) provides another view of the same saved inputs.\n\nGenerated from [evidence/status.json](../evidence/status.json) and the [journey catalog](journeys/catalog.json). The [quality rules](../QUALITY.md) govern acceptance. Edit the source records through their owning systems; do not hand-edit this report.\n'
}

export function changelog(m) {
  const assigned = new Set(m.releases.releases.flatMap(r=>r.fragments))
  const pending = m.fragments.filter(f=>!f.withdrawn&&!assigned.has(f.id))
  const entries = fragments => categories.map(category=>{
    const group=fragments.filter(f=>f.category===category)
    return group.length?'### '+category+'\n\n'+group.map(f=>'- '+f.summary+'\n  Sources: '+f.references.map((r,i)=>/^https:\/\//.test(r)?'[source '+(i+1)+']('+r+')':'[details '+(i+1)+']('+r+')').join(', ')).join('\n\n'):null
  }).filter(Boolean).join('\n\n')
  const releases = [...m.releases.releases].sort((a,b)=>b.date.localeCompare(a.date)||b.version.localeCompare(a.version))
  let body='# Changelog\n\nDevelopment changes and published releases, grouped by the kind of change. Unreleased work has not been published as a Gitgood application release.\n\n[Project overview](README.md) · [Progress snapshot](docs/STATUS.md) · [Changelog routine](changelog/ROUTINE.md)\n\nGenerated from reviewed fragments and [the release manifest](changelog/releases.json). This file does not publish a release.\n\n## Unreleased\n\n'+(entries(pending)||'No pending entries.')+'\n'
  for (const r of releases) body+='\n## '+r.version+' — '+r.date+'\n\nSource commit: '+r.commit+'.\n\n'+entries(r.fragments.map(id=>m.fragments.find(f=>f.id===id)))+'\n'+(r.upgrade?'\nUpgrade: '+r.upgrade+'\n':'')
  const latest=releases[0]
  // Keep README bounded as the detailed development history and release notes grow.
  const highlights = latest
    ? "## What's new\n\n**"+latest.version+" — "+latest.date+".** See the [release notes](CHANGELOG.md) for included changes and upgrade instructions."
    : "## What's new\n\n**Unreleased — development.** "+(pending.length
      ? pending.length+' development '+(pending.length===1?'change is':'changes are')+' recorded in the [changelog](CHANGELOG.md#unreleased).'
      : 'No pending changelog entries.')+' No Gitgood application release has been published.'
  return {body,highlights}
}
