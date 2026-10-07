import {classify, freshness} from './model.mjs'
export const escapeXml = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]))
const md = s => String(s).replace(/\|/g, '\\|').replace(/\r?\n/g, ' ')
function count(m, list, key, desired, clock) {
  const states = list.map(j => classify(m.snapshot.records.find(r => r.id === j.id), m.snapshot, clock)[key])
  if (states.some(s => ['unknown', 'stale'].includes(s))) return '?'
  return String(states.filter(s => s === desired).length)
}
export function svg(m) {
  const clock = new Date(m.snapshot.evaluatedAt ?? '2026-10-07T00:00:00Z')
  const snapshot = m.snapshot.evaluatedAt ?? 'No connected implementation evidence'
  const lines = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 720" role="img" aria-labelledby="title desc">',
    '<title id="title">Gitpark delivery roadmap</title>',
    '<desc id="desc">Eight milestones from scope to a complete native forge. Implementation, verification and release are separate. A question mark means unavailable or stale input, not zero progress.</desc>',
    '<style>:root{color-scheme:light dark} .bg{fill:#f5f7fa}.card{fill:#fff;stroke:#ced8e4}.text{fill:#162739}.muted{fill:#52677a}.accent{fill:#136e68}.line{stroke:#ced8e4} text{font-family:Arial,Helvetica,sans-serif} @media(prefers-color-scheme:dark){.bg{fill:#121c27}.card{fill:#1b2938;stroke:#405365}.text{fill:#eef5fb}.muted{fill:#bccbd7}.accent{fill:#82d6c8}.line{stroke:#405365}}</style>',
    '<rect class="bg" width="1120" height="720" rx="20"/>',
    '<text class="text" x="36" y="54" font-size="30" font-weight="700">GITPARK</text>',
    '<text class="muted" x="36" y="86" font-size="16">Native forge · Barkpark integration · Managed Cloud lifecycle</text>',
    '<text class="accent" x="36" y="121" font-size="14" font-weight="700">PLANNING BASELINE · Product completion requires connected evidence</text>'
  ]
  m.milestones.milestones.forEach((phase, i) => {
    const x = 36 + (i % 4) * 266, y = 151 + Math.floor(i / 4) * 194
    const js = m.catalog.journeys.filter(j => j.milestone === phase.id)
    lines.push('<rect class="card" x="'+x+'" y="'+y+'" width="250" height="177" rx="12"/>')
    lines.push('<text class="accent" x="'+(x+18)+'" y="'+(y+28)+'" font-size="13" font-weight="700">'+escapeXml(phase.id)+'</text>')
    const title = phase.title.split(' '), first = [], second = []
    for (const word of title) ((first.join(' ').length+word.length < 23 && !second.length) ? first : second).push(word)
    lines.push('<text class="text" x="'+(x+18)+'" y="'+(y+57)+'" font-size="17" font-weight="700">'+escapeXml(first.join(' '))+'</text>')
    if (second.length) lines.push('<text class="text" x="'+(x+18)+'" y="'+(y+79)+'" font-size="17" font-weight="700">'+escapeXml(second.join(' '))+'</text>')
    if (js.length) {
      lines.push('<text class="muted" x="'+(x+18)+'" y="'+(y+108)+'" font-size="13">'+js.length+' journey'+(js.length===1?'':'s')+' assigned here</text>')
      lines.push('<text class="text" x="'+(x+18)+'" y="'+(y+133)+'" font-size="12">Implemented '+count(m,js,'implementation','implemented',clock)+' · Verified '+count(m,js,'verification','verified',clock)+'</text>')
      lines.push('<text class="text" x="'+(x+18)+'" y="'+(y+154)+'" font-size="12">Released '+count(m,js,'release','released',clock)+'</text>')
    } else {
      lines.push('<text class="muted" x="'+(x+18)+'" y="'+(y+113)+'" font-size="13">Milestone exit evidence required</text>')
      lines.push('<text class="text" x="'+(x+18)+'" y="'+(y+145)+'" font-size="12">Acceptance: unverified</text>')
    }
  })
  lines.push('<line class="line" x1="36" y1="558" x2="1084" y2="558"/>')
  lines.push('<text class="text" x="36" y="588" font-size="15">'+m.catalog.journeys.length+' scoped journeys · ? = unknown or stale · task closure does not prove verification</text>')
  lines.push('<text class="muted" x="36" y="617" font-size="13">Snapshot: '+escapeXml(snapshot)+'</text>')
  lines.push('<text class="muted" x="36" y="643" font-size="13">Sources: '+Object.keys(m.snapshot.sources).map(n=>escapeXml(n+': '+freshness(m.snapshot,n,clock))).join(' · ')+'</text>')
  lines.push('<text class="muted" x="36" y="670" font-size="12">Freshness limit: '+m.snapshot.maxAgeHours+' hours. This static image does not refresh itself.</text>')
  lines.push('<text class="muted" x="36" y="694" font-size="12">Baseline: '+escapeXml(m.snapshot.baseline)+' · Open ROADMAP.md for exit criteria and limitations.</text>')
  lines.push('</svg>')
  return lines.join('\n')+'\n'
}
export function roadmap(m) {
  return '# Delivery roadmap\n\nGenerated from docs/milestones.json. Definitions are not execution status; view the README SVG and npm run status for evidence freshness.\n\n| Milestone | Work | Exit evidence |\n|---|---|---|\n'+m.milestones.milestones.map(p=>'| '+p.id+' '+md(p.title)+' | '+md(p.work)+' | '+md(p.exit)+' |').join('\n')+'\n\nM0/M1 and M7 have their own exit gates; an empty journey set never marks them complete. J04 begins in M2 but its full browsing scope is required by M4. Recovery and Cloud packaging research start before the final lifecycle phase.\n\nFollow [execution order](EXECUTION.md), [journey index](../JOURNEYS.md), and [quality rules](../QUALITY.md). Re-estimate after M2 and M3. No milestone is accepted by this generated diagram alone.\n'
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
    : "## What's new\n\n**Unreleased — planning foundation.** "+(pending.filter(f=>f.impact==='planning').map(f=>f.summary).join(' ')||'Development work has not been released.')+' No Gitpark application release has been published.'
  return {body,highlights}
}
