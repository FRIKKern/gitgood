import {classify, freshness} from './model.mjs'

const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]))
const columns = [
  {key:'implementation', label:'Implemented', success:'implemented', source:'ledger'},
  {key:'verification', label:'Verified', success:'verified', source:'evidence'},
  {key:'release', label:'Released', success:'released', source:'releases'}
]
const appearance = state => ({
  implemented:['good','✓'], verified:['good','✓'], released:['good','✓'],
  in_progress:['active','◐'], planned:['muted','○'], absent:['muted','○'],
  failed:['failed','×'], inconclusive:['warning','!'], stale:['warning','~'], unknown:['muted','?']
}[state] ?? ['muted','?'])

// Bound line length, including unbroken identifiers. Never drop a journey or gate.
function wrap(value, limit) {
  const words = String(value).split(/\s+/).flatMap(word => word.match(new RegExp(`.{1,${limit}}`, 'gu')) ?? [])
  const lines = []
  for (const word of words) {
    if (!lines.length || lines.at(-1).length + word.length + 1 > limit) lines.push(word)
    else lines[lines.length - 1] += ' ' + word
  }
  return lines
}

export function svg(m) {
  const width = 1200, padding = 36, gap = 18, cardWidth = 555
  const clock = new Date(m.snapshot.evaluatedAt ?? '2026-10-07T00:00:00Z')
  const states = new Map(m.catalog.journeys.map(j => [j.id, classify(m.snapshot.records.find(r => r.id === j.id), m.snapshot, clock)]))
  const total = m.catalog.journeys.length
  const summaries = columns.map(c => {
    const values = [...states.values()].map(s => s[c.key])
    return {...c, passed:values.filter(s => s === c.success).length, uncertain:values.filter(s => ['unknown','stale'].includes(s)).length}
  })
  const phases = m.milestones.milestones.map(phase => {
    const journeys = m.catalog.journeys.filter(j => j.milestone === phase.id).map(j => ({...j, lines:wrap(j.title, 39)}))
    const titles = wrap(phase.title, 33)
    const exit = wrap(phase.exit, 60)
    const work = wrap(phase.work, 57)
    const bodyHeight = journeys.length ? journeys.reduce((n,j) => n + Math.max(34, j.lines.length * 21 + 12), 0) : work.length * 23 + 32
    const titleHeight = titles.length * 28
    const height = 110 + titleHeight + bodyHeight + exit.length * 20 + 50
    return {...phase, journeys, titles, exit, work, bodyHeight, titleHeight, height}
  })
  let nextY = 338
  const rows = []
  for (let i=0; i<phases.length; i+=2) {
    const cards=phases.slice(i,i+2), height=Math.max(...cards.map(p=>p.height))
    rows.push({cards,y:nextY,height});nextY+=height+gap
  }
  const footerY=nextY+12, height=footerY+164
  const out=[]
  const text=(x,y,value,size=16,cls='',attrs='')=>out.push(`<text x="${x}" y="${y}" font-size="${size}" class="${cls}" ${attrs}>${esc(value)}</text>`)
  const rect=(x,y,w,h,cls,rx=14)=>out.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" class="${cls}"/>`)
  const rule=(x,y,w)=>out.push(`<path d="M${x} ${y}h${w}" class="rule"/>`)
  const multiline=(x,y,lines,size=16,step=23,cls='')=>lines.forEach((line,i)=>text(x,y+i*step,line,size,cls))
  const metricText=s=>s.uncertain ? `${s.passed} confirmed · ${s.uncertain} unknown or stale` : `${s.passed} of ${total} journeys`
  out.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">`)
  out.push('<title id="title">Gitgood — from private repository to complete forge</title>')
  out.push(`<desc id="desc">${phases.length} milestones and ${total} scoped journeys. ${summaries.map(s=>esc(s.label+': '+metricText(s))).join('. ')}. Each journey shows implementation, verification, and release separately. Milestone exit gates are not inferred from journey counts. Unknown is not zero. Source freshness is evaluated at the recorded snapshot time.</desc>`)
  out.push(`<style>
    :root{color-scheme:light dark}
    text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;fill:#202c2a}
    .bg{fill:#f6f5f0}.card{fill:#fff;stroke:#d9dfd8}.panel{fill:#eaf0e9}.rule{stroke:#d9dfd8;fill:none}
    .muted{fill:#63706a}.good{fill:#247253}.active{fill:#176cad}.warning{fill:#91620b}.failed{fill:#b1393c}
    .badge{fill:#e5eee7}.accent{fill:#245c47}.track{fill:#e3e8e1}.unknown{fill:url(#unknown-pattern)}
    .mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.label{font-weight:600;letter-spacing:1.6px}
    .strong{font-weight:650}.symbol{font-weight:700}.pattern-line{stroke:#b7c2b8;stroke-width:1}.branch{stroke:#245c47;fill:none}
    @media(prefers-color-scheme:dark){
      text{fill:#e9eee8}.bg{fill:#141c19}.card{fill:#1d2722;stroke:#39473e}.panel{fill:#24352b}.rule{stroke:#39473e}
      .muted{fill:#b0bdb3}.good{fill:#8bd2a9}.active{fill:#8cbdeb}.warning{fill:#e7be70}.failed{fill:#ffaaaa}
      .badge{fill:#2d4033}.accent{fill:#a8dfb7}.track{fill:#35443a}.pattern-line{stroke:#5c7364}.branch{stroke:#a8dfb7}
    }
  </style>`)
  out.push('<defs><pattern id="unknown-pattern" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M-2 2L2-2M0 8L8 0M6 10L10 6" class="pattern-line"/></pattern></defs>')
  rect(0,0,width,height,'bg',24)
  // A small Git branch mark is native vector geometry, with no external assets.
  rect(36,32,52,52,'badge',15)
  out.push('<g class="branch" stroke-width="2.5"><path d="M53 50v16m18-15v3c0 8-18 3-18 12"/><circle cx="53" cy="46" r="4"/><circle cx="53" cy="70" r="4"/><circle cx="71" cy="47" r="4"/></g>')
  text(102,70,'Gitgood',38,'strong')
  text(1164,49,'DELIVERY MAP',13,'muted label','text-anchor="end"')
  text(1164,79,`${phases.length} milestones / ${total} journeys`,18,'strong','text-anchor="end"')
  text(36,120,'A native forge, from first push to a recoverable release.',23,'strong')
  text(36,151,'Elixir + Postgres   /   Barkpark workspace   /   Cloud lifecycle',16,'muted')
  summaries.forEach((s,i)=>{
    const x=36+i*382, values=[...states.values()].map(state=>state[s.key])
    out.push(`<g data-metric="${s.key}"><title>${esc(s.label+': '+metricText(s))}</title>`)
    rect(x,179,364,111,'panel')
    text(x+18,206,s.key==='implementation'?'Fully implemented':s.label,15,'strong')
    text(x+346,211,s.uncertain ? '?' : `${s.passed} / ${total}`,26,s.uncertain?'muted strong':'good strong','text-anchor="end"')
    const source=freshness(m.snapshot,s.source,clock)
    const detail=s.key==='implementation'&&!s.uncertain?`${s.passed} complete · ${values.filter(value=>value==='in_progress').length} in progress`:metricText(s)
    text(x+18,235,source==='unconfigured'?'Status source not connected':source==='unavailable'?'Status source unavailable':detail,14,'muted')
    const segmentGap=Math.min(4,164/Math.max(1,total-1))
    const cell=(328-Math.max(0,total-1)*segmentGap)/Math.max(1,total)
    values.forEach((state,k)=>{
      const cls=state===s.success?'good':state==='stale'?'warning':state==='failed'?'failed':state==='in_progress'?'active':['unknown','inconclusive'].includes(state)?'unknown':'track'
      out.push(`<rect data-state="${esc(state)}" x="${(x+18+k*(cell+segmentGap)).toFixed(2)}" y="255" width="${cell.toFixed(2)}" height="12" rx="3" class="${cls}"><title>${esc(m.catalog.journeys[k].id+': '+state)}</title></rect>`)
    })
    out.push('</g>')
  })
  text(36,319,'THE PATH TO A COMPLETE FORGE',13,'muted label')
  text(1164,319,'Sequence is the plan · evidence is the status',14,'muted','text-anchor="end"')
  for(const row of rows)row.cards.forEach((phase,index)=>{
    const x=padding+index*(cardWidth+gap),y=row.y
    out.push(`<g data-phase="${esc(phase.id)}"><title>${esc(phase.id+' '+phase.title+'. Exit gate: '+phase.exit)}</title>`)
    rect(x,y,cardWidth,row.height,'card',16)
    rect(x+20,y+19,42,27,'badge',7)
    text(x+41,y+38,phase.id,14,'accent mono strong','text-anchor="middle"')
    text(x+cardWidth-20,y+38,phase.dependsOn.length?'AFTER '+phase.dependsOn.join(' + '):'FOUNDATION',12,'muted label','text-anchor="end"')
    multiline(x+20,y+78,phase.titles,23,28,'strong')
    const bodyY=y+phase.titleHeight+96
    rule(x+20,bodyY-25,cardWidth-40)
    if(phase.journeys.length){
      text(x+20,bodyY-5,`${phase.journeys.length} JOURNEYS`,11,'muted label')
      const statusXs=[x+cardWidth-98,x+cardWidth-64,x+cardWidth-30]
      statusXs.forEach((sx,i)=>text(sx,bodyY-5,['I','V','R'][i],12,'muted mono','text-anchor="middle"'))
      let jy=bodyY+25
      phase.journeys.forEach(j=>{
        const state=states.get(j.id)
        out.push(`<g data-journey="${esc(j.id)}"><title>${esc(j.id+' '+j.title+'. '+columns.map(c=>c.label+': '+state[c.key]).join('; '))}</title>`)
        text(x+20,jy,j.id,13,'muted mono')
        multiline(x+65,jy,j.lines,16,21)
        statusXs.forEach((sx,i)=>{const [cls,symbol]=appearance(state[columns[i].key]);text(sx,jy,symbol,18,cls+' symbol','text-anchor="middle"')})
        out.push('</g>');jy+=Math.max(34,j.lines.length*21+12)
      })
    }else{
      text(x+20,bodyY-5,'MILESTONE GATE',11,'muted label')
      multiline(x+20,bodyY+25,phase.work,16,23)
    }
    const gateY=y+row.height-phase.exit.length*20-25
    rule(x+20,gateY-26,cardWidth-40)
    text(x+20,gateY-6,'EXIT EVIDENCE',11,'muted label')
    multiline(x+20,gateY+16,phase.exit,14,20,'muted')
    out.push('</g>')
  })
  rule(36,footerY,1128)
  text(36,footerY+29,'I · Implemented    /    V · Verified    /    R · Released',14,'strong')
  text(1164,footerY+29,'✓ pass    ◐ active    ○ pending    × failed    ! inconclusive    ~ stale    ? unknown',14,'muted','text-anchor="end"')
  text(36,footerY+58,'Journey status is not milestone completion. J04 continues through M4.',14,'muted')
  text(36,footerY+86,'SOURCES',11,'muted label')
  text(126,footerY+86,columns.map(c=>`${c.source}: ${freshness(m.snapshot,c.source,clock)}`).join('   /   '),14,'muted')
  text(36,footerY+113,m.snapshot.evaluatedAt?`Evaluated ${m.snapshot.evaluatedAt} · freshness window ${m.snapshot.maxAgeHours}h`:'No connected status snapshot · product progress is unknown',14,'muted')
  text(36,footerY+140,'Generated from canonical records · static snapshot · full criteria in docs/ROADMAP.md',13,'muted')
  out.push('</svg>')
  return out.join('\n')+'\n'
}
