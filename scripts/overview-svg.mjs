// A compact view of planned delivery order. Observed completion belongs to the
// generated STATUS.md and detailed journey evidence map.
export function svg(m) {
  const stages = m.milestones.milestones.map(milestone => milestone.id)
  if (stages.join(',') !== 'M0,M1,M2,M3,M4,M5,M6,M7') {
    throw new Error('Update the README overview grouping for the changed milestone order in docs/milestones.json')
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="318" viewBox="0 0 960 318" role="img" aria-labelledby="title desc">
<title id="title">Gitgood — from private Git to a complete managed forge</title>
<desc id="desc">Planned delivery order: M0 through M2, a private repository in the browser and Git client; M3 through M4, a team forge with reviews and releases; M5, a connected Barkpark workspace; M6 through M7, a managed release with Cloud deployment and recovery. Stages are not dates or completion claims.</desc>
<defs>
  <linearGradient id="background" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#142d28"/><stop offset="1" stop-color="#0c1b18"/></linearGradient>
  <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#9ce8be"/><stop offset="1" stop-color="#58ae8d"/></linearGradient>
</defs>
<style>
  text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;fill:#f1f8f3}
  .muted{fill:#b2c9bb}.small{font-size:12px;letter-spacing:1.2px}.strong{font-weight:650}
  .card{fill:#1a342d;stroke:#355446}.label{font-size:19px;font-weight:600}.detail{font-size:14px;fill:#b2c9bb}.stage{font-size:13px;fill:#a4e9c0}
</style>
<rect width="960" height="318" rx="20" fill="url(#background)"/>
<path d="M30 0h900" stroke="url(#accent)" stroke-width="4"/>
<g stroke="#a4e9c0" stroke-width="2.6" fill="none">
  <path d="M43 40v21m20-22v7c0 9-20 5-20 15"/>
  <circle cx="43" cy="36" r="4"/><circle cx="43" cy="65" r="4"/><circle cx="63" cy="35" r="4"/>
</g>
<text x="82" y="64" font-size="39" class="strong">Gitgood</text>
<text x="924" y="47" text-anchor="end" class="muted small">THE ROAD TO A COMPLETE FORGE</text>
<text x="36" y="105" font-size="23">Private code. Clear reviews. Recoverable releases.</text>
<g>
  <rect x="36" y="130" width="206" height="102" rx="10" class="card"/>
  <text x="52" y="155" class="stage">M0–M2</text><text x="52" y="183" class="label">Private Git</text><text x="52" y="210" class="detail">Browser + Git client</text>
  <rect x="264" y="130" width="206" height="102" rx="10" class="card"/>
  <text x="280" y="155" class="stage">M3–M4</text><text x="280" y="183" class="label">Team forge</text><text x="280" y="210" class="detail">Reviews + releases</text>
  <rect x="492" y="130" width="206" height="102" rx="10" class="card"/>
  <text x="508" y="155" class="stage">M5</text><text x="508" y="183" class="label">Connected work</text><text x="508" y="210" class="detail">Barkpark workspace</text>
  <rect x="720" y="130" width="204" height="102" rx="10" class="card"/>
  <text x="736" y="155" class="stage">M6–M7</text><text x="736" y="183" class="label">Managed release</text><text x="736" y="210" class="detail">Cloud + recovery</text>
</g>
<g stroke="#86b79b" stroke-width="1.8" fill="none">
  <path d="M248 181h10m-4-4 4 4-4 4M476 181h10m-4-4 4 4-4 4M704 181h10m-4-4 4 4-4 4"/>
</g>
<text x="36" y="260" font-size="13" class="muted">Planned sequence · stages, not dates or completion</text>
<text x="36" y="293" font-size="14" class="muted">Elixir / Phoenix</text>
<text x="220" y="293" font-size="14" class="muted">Postgres</text>
<text x="350" y="293" font-size="14" class="muted">React / TanStack</text>
<text x="924" y="293" font-size="14" text-anchor="end" class="stage">Barkpark Cloud</text>
</svg>
`
}
