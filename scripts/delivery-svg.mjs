import {classify, freshness} from './model.mjs'

const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]))
const wrap = (value, limit) => {
  const lines=[]
  for(const word of String(value).split(/\s+/).flatMap(w=>w.match(new RegExp(`.{1,${limit}}`,'gu'))??[])){
    if(!lines.length || lines.at(-1).length+word.length+1>limit)lines.push(word)
    else lines[lines.length-1]+=' '+word
  }
  return lines
}

export function svg(m) {
  const phases=m.milestones.milestones, tracks=m.milestones.supportTracks??[]
  const width=Math.max(1200,480+phases.length*80), right=width-36, chartX=470, chartWidth=right-chartX
  const step=chartWidth/Math.max(1,phases.length), clock=new Date(m.snapshot.evaluatedAt??'2026-10-07T00:00:00Z')
  const states=m.catalog.journeys.map(j=>classify(m.snapshot.records.find(r=>r.id===j.id),m.snapshot,clock))
  const rows=[...phases.map((p,i)=>({...p,kind:'delivery',startIndex:i,endIndex:i})),...tracks.map(t=>({...t,startIndex:phases.findIndex(p=>p.id===t.start),endIndex:phases.findIndex(p=>p.id===t.end)}))]
  let nextY=318
  for(const row of rows){
    row.titleLines=wrap(row.title,35);row.surfaceLines=wrap(row.surface??'See milestone criteria',48)
    row.y=nextY;row.height=Math.max(86,26+row.titleLines.length*25+row.surfaceLines.length*20)
    if(row===rows[phases.length]){nextY+=46;row.y=nextY}
    nextY+=row.height
  }
  const footer=nextY+28, height=footer+218, out=[]
  const text=(x,y,value,size=16,cls='',attrs='')=>out.push(`<text x="${x}" y="${y}" font-size="${size}" class="${cls}" ${attrs}>${esc(value)}</text>`)
  const rect=(x,y,w,h,cls,rx=6)=>out.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" class="${cls}"/>`)
  const line=(x1,y1,x2,y2)=>out.push(`<path d="M${x1} ${y1}L${x2} ${y2}" class="rule"/>`)
  out.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">`)
  out.push('<title id="title">Gitgood delivery scope — milestone Gantt</title>')
  out.push(`<desc id="desc">${phases.length} sequential milestone delivery gates with delivery surfaces, ${tracks.length} supporting work lanes, and separate evidence summaries. Equal columns do not represent equal durations. Bars are planned sequence, not completion. Research overlap is proposed. Full journey status and exit criteria are in the linked documentation.</desc>`)
  out.push(`<style>
    :root{color-scheme:light dark}
    text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;fill:#202c2a}
    .bg{fill:#f6f5f0}.muted{fill:#63706a}.rule{stroke:#dce2db;fill:none}.strong{font-weight:650}
    .label{font-weight:600;letter-spacing:1.6px}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
    .panel{fill:#eaf0e9}.delivery{fill:#c9e2f2}.research{fill:url(#research-pattern)}.continuous{fill:#d5e8d8}
    .hatch{stroke:#d5a372;stroke-width:4}.accent{fill:#245c47}.good{fill:#247253}.unknown{fill:#63706a}
    @media(prefers-color-scheme:dark){
      text{fill:#e9eee8}.bg{fill:#141c19}.muted{fill:#b0bdb3}.rule{stroke:#36453c}.panel{fill:#24352b}
      .delivery{fill:#284b64}.continuous{fill:#2d513b}.hatch{stroke:#775635}.accent{fill:#a8dfb7}.good{fill:#8bd2a9}.unknown{fill:#b0bdb3}
    }
  </style>`)
  out.push('<defs><pattern id="research-pattern" width="12" height="12" patternUnits="userSpaceOnUse"><path d="M-3 3L3-3M0 12L12 0M9 15L15 9" class="hatch"/></pattern></defs>')
  rect(0,0,width,height,'bg',24)
  text(36,68,'Gitgood',38,'strong')
  text(right,48,'DELIVERY SCOPE',13,'muted label','text-anchor="end"')
  text(right,78,`${phases.length} milestones / ${m.catalog.journeys.length} journeys`,17,'strong','text-anchor="end"')
  text(36,112,'From first private push to a complete managed forge.',23,'strong')
  text(36,143,'Milestone-based Gantt · sequence and overlap, not elapsed time',16,'muted')
  const metrics=[['implementation','Implemented','implemented','ledger'],['verification','Verified','verified','evidence'],['release','Released','released','releases']]
  metrics.forEach(([key,label,success,source],i)=>{
    const x=36+i*(width-72)/3, w=(width-72)/3-12
    const passed=states.filter(s=>s[key]===success).length, unknown=states.filter(s=>['unknown','stale'].includes(s[key])).length
    const summary=unknown?`${passed} confirmed · ${unknown} unknown or stale`:`${passed} / ${states.length} journeys`
    out.push(`<g data-metric="${key}"><title>${esc(label+': '+summary)}</title>`)
    rect(x,170,w,77,'panel',12)
    text(x+16,198,label,15,'strong')
    text(x+w-16,200,unknown?'?':`${passed}/${states.length}`,22,unknown?'unknown strong':'good strong','text-anchor="end"')
    text(x+16,229,freshness(m.snapshot,source,clock)==='unconfigured'?'Status source not connected':summary,14,'muted')
    out.push('</g>')
  })
  text(36,286,'WHAT YOU WILL SEE / WHERE',12,'muted label')
  text(chartX,278,'DELIVERY ORDER',12,'muted label')
  phases.forEach((p,i)=>text(chartX+(i+0.5)*step,305,p.id,14,'muted mono','text-anchor="middle"'))
  for(let i=0;i<=phases.length;i++)line(chartX+i*step,318,chartX+i*step,nextY)
  for(const row of rows){
    if(row===rows[phases.length])text(36,row.y-16,'SUPPORTING WORK / PROPOSED OVERLAP',12,'muted label')
    const y=row.y, bx=chartX+row.startIndex*step+6, bw=(row.endIndex-row.startIndex+1)*step-12
    const details=row.kind==='delivery'?`${row.work} Exit gate: ${row.exit} ${row.dependsOn.length?'After '+row.dependsOn.join(', ')+'.':'Foundation.'}`:row.note
    out.push(`<g data-${row.kind==='delivery'?'phase':'track'}="${esc(row.id)}"><title>${esc(row.id+' '+row.title+'. '+details)}</title>`)
    text(36,y+30,row.id,14,'accent mono strong')
    row.titleLines.forEach((s,i)=>text(79,y+30+i*25,s,19,'strong'))
    row.surfaceLines.forEach((s,i)=>text(79,y+30+row.titleLines.length*25+i*20,s,14,'muted'))
    rect(bx,y+22,bw,36,row.kind)
    text(bx+bw/2,y+46,row.kind==='delivery'?row.id:row.kind==='research'?'Research':'Every stage',15,'strong','text-anchor="middle"')
    line(36,y+row.height,right,y+row.height)
    out.push('</g>')
  }
  const deliveries=phases.filter(p=>p.delivery), deliveryStep=(width-72)/Math.max(1,deliveries.length)
  deliveries.forEach((p,i)=>{
    const x=36+i*deliveryStep
    text(x,footer+6,p.id,13,'accent mono strong')
    text(x,footer+33,p.delivery,19,'strong')
  })
  const legendY=footer+69
  rect(36,legendY-12,22,12,'delivery',2);text(67,legendY,'Delivery gate',14,'muted')
  rect(216,legendY-12,22,12,'research',2);text(247,legendY,'Proposed early research',14,'muted')
  rect(490,legendY-12,22,12,'continuous',2);text(521,legendY,'Continuous work',14,'muted')
  text(36,footer+100,'Equal columns ≠ equal durations. Bars show the plan, not verified completion.',15,'muted')
  text(36,footer+127,'Research overlap requires capacity. Re-estimate calendar timing after M2 and M3.',14,'muted')
  text(36,footer+155,metrics.map(([, , , source])=>`${source}: ${freshness(m.snapshot,source,clock)}`).join('   /   '),14,'muted')
  text(36,footer+182,m.snapshot.evaluatedAt?`Snapshot ${m.snapshot.evaluatedAt} · ${m.snapshot.maxAgeHours}h freshness window · static image`:'No connected status snapshot · journey evidence and full exit criteria linked below',13,'muted')
  out.push('</svg>')
  return out.join('\n')+'\n'
}
