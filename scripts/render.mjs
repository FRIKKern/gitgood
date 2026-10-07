export {svg} from './delivery-svg.mjs'
export {svg as journeySvg} from './roadmap-svg.mjs'
export const escapeXml = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]))
const md = s => String(s).replace(/\|/g, '\\|').replace(/\r?\n/g, ' ')
export function roadmap(m) {
  const phases = m.milestones.milestones.map(p => '| '+p.id+' '+md(p.title)+' | '+md(p.surface ?? 'See work')+' | '+md(p.work)+' | '+md(p.exit)+' |').join('\n')
  const tracks = (m.milestones.supportTracks ?? []).map(t => '| '+md(t.title)+' | '+t.start+'–'+t.end+' | '+md(t.surface)+' | '+md(t.note)+' |').join('\n')
  return '# Delivery roadmap\n\nGenerated from docs/milestones.json. The [Gantt](images/roadmap.svg) shows milestone order and delivery surfaces; the [journey evidence map](images/journey-evidence.svg) shows detailed implementation, verification, and release states.\n\nEqual columns do not imply equal durations. Gantt bars show planned delivery gates, not completion or a calendar forecast. The milestone catalog is ordered by dependencies.\n\n| Milestone | Where it appears | Work | Exit evidence |\n|---|---|---|---|\n'+phases+'\n\n## Supporting work\n\nResearch spans are proposed early experiments and require execution capacity for overlap. Full lifecycle acceptance remains at M6.\n\n| Work | Stages, inclusive | Where | Conditions |\n|---|---|---|---|\n'+tracks+'\n\nM0/M1 and M7 have their own exit gates; an empty journey set never marks them complete. J04 begins in M2 but its full browsing scope is required by M4.\n\nFollow [execution order](EXECUTION.md), [journey index](../JOURNEYS.md), and [quality rules](../QUALITY.md). Re-estimate calendar timing after M2 and M3. No milestone is accepted by a generated diagram alone.\n'
}
export function index(m) {
  return '# Journey index\n\nGenerated from docs/journeys/catalog.json. Each specification owns its acceptance criteria. Status comes from evidence and the future Barkpark ledger, not this table.\n\n| ID | First milestone | Journey | Required |\n|---|---|---|---|\n'+m.catalog.journeys.map(j=>'| '+j.id+' | '+j.milestone+' | ['+md(j.title)+']('+j.spec+') | '+(j.required?'Yes':'No')+' |').join('\n')+'\n\nSee [quality rules](QUALITY.md), [roadmap](docs/ROADMAP.md), and [tracking contract](docs/TRACKING.md). J04 continues through M4; a milestone assignment does not reduce its acceptance scope.\n'
}
export function changelog(m) {
  const assigned = new Set(m.releases.releases.flatMap(r=>r.fragments))
  const pending = m.fragments.filter(f=>!f.withdrawn&&!assigned.has(f.id))
  const entries = fragments => fragments.map(f=>'- **'+f.category+':** '+f.summary+' Sources: '+f.references.map(r=>/^https:\/\//.test(r)?'[source]('+r+')':'['+r+']('+r+')').join(', ')).join('\n')
  const releases = [...m.releases.releases].sort((a,b)=>b.date.localeCompare(a.date)||b.version.localeCompare(a.version))
  let body='# Changelog\n\nGenerated from reviewed fragments and changelog/releases.json. This file does not publish an application release.\n\n## Unreleased\n\n'+(entries(pending)||'No pending entries.')+'\n'
  for (const r of releases) body+='\n## '+r.version+' — '+r.date+'\n\nSource commit: '+r.commit+'.\n\n'+entries(r.fragments.map(id=>m.fragments.find(f=>f.id===id)))+'\n'+(r.upgrade?'\nUpgrade: '+r.upgrade+'\n':'')
  const latest=releases[0]
  const highlights = latest
    ? "## What's new\n\n**"+latest.version+" — "+latest.date+".** "+latest.fragments.map(id=>m.fragments.find(f=>f.id===id)?.summary).filter(Boolean).slice(0,3).join(' ')+' See [release history](CHANGELOG.md).'
    : "## What's new\n\n**Unreleased — planning foundation.** "+(pending.filter(f=>f.impact==='planning').map(f=>f.summary).join(' ')||'Development work has not been released.')+' No Gitgood application release has been published.'
  return {body,highlights}
}
