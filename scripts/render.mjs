import {classify, freshness} from './model.mjs'

export {svg} from './delivery-svg.mjs'
export {svg as journeySvg} from './roadmap-svg.mjs'
export {svg as overviewSvg} from './overview-svg.mjs'

export function escapeXml(value) {
  const entities = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;'}
  return String(value).replace(/[&<>"']/g, character => entities[character])
}

function markdownCell(value) {
  return String(value).replace(/\|/g, '\\|').replace(/\r?\n/g, ' ')
}

function renderMilestone(milestone) {
  return `### ${milestone.id} · ${milestone.title}

**Where:** ${milestone.surface ?? 'See the work below'}

${milestone.work}

**Ready when:** ${milestone.exit}`
}

export function roadmap(model) {
  const milestones = model.milestones.milestones
  const supportTracks = model.milestones.supportTracks ?? []
  const milestoneSections = milestones.map(renderMilestone).join('\n\n')
  const deliveries = milestones
    .filter(milestone => milestone.delivery)
    .map(milestone => `- **${milestone.id} — ${milestone.delivery}:** ${milestone.surface}.`)
    .join('\n')
  const trackRows = supportTracks
    .map(track => `| ${markdownCell(track.title)} | ${track.start}–${track.end} | ${markdownCell(track.surface)} |`)
    .join('\n')
  const trackNotes = supportTracks
    .map(track => `- **${track.title}:** ${track.note}`)
    .join('\n')

  return `# Delivery roadmap

The route from a private repository to a complete, recoverable forge. Each milestone describes what you should see, where it appears, and what must pass before we advance.

[Full Gantt](images/roadmap.svg) · [Progress snapshot](STATUS.md) · [What to build next](EXECUTION.md) · [Documentation guide](README.md)

## How to read this plan

Milestones follow dependency order. Their widths in the Gantt do not represent duration, and its bars show planned work rather than completion. There are no calendar promises in this view; re-estimate timing after M2 and M3.

${deliveries}

## Milestones

${milestoneSections}

## Work that spans milestones

Research can start early when capacity allows. Its experiment does not complete the later product requirement; full installation and recovery acceptance remains at M6.

| Work | Stages | Where |
|---|---|---|
${trackRows}

${trackNotes}

## What counts as complete

Each milestone must meet its own exit conditions. M0, M1 and M7 have requirements beyond journey counts. Code browsing (J04) starts at M2 and reaches its full scope at M4.

Use the [journey specifications](../JOURNEYS.md) and [quality rules](../QUALITY.md) to assess completion. The [progress snapshot](STATUS.md) reports observed evidence separately from this plan.

Generated from [the milestone catalog](milestones.json); edit that source to change this roadmap.
`
}

export function index(model) {
  const journeys = model.catalog.journeys
  const rows = journeys.map(journey => {
    const title = markdownCell(journey.title)
    const required = journey.required ? 'Yes' : 'No'
    return `| [${title}](${journey.spec}) | ${journey.id} | ${journey.milestone} | ${required} |`
  }).join('\n')

  return `# Product journeys

A journey is a task a person must be able to complete from beginning to end, such as pushing code, reviewing a change, or restoring a lost host. These ${journeys.length} specifications define the product we are building.

[Product scope](PRODUCT.md) · [Delivery roadmap](docs/ROADMAP.md) · [Progress snapshot](docs/STATUS.md) · [Documentation guide](docs/README.md)

Open a journey to see its scenarios and acceptance criteria. The first milestone tells you when work begins; it does not claim that the journey is complete. Code browsing (J04) begins at M2 and continues through M4.

| What you can do | ID | First milestone | Required for release |
|---|---|---|---|
${rows}

Implementation, verification and release are separate. Consult the [progress snapshot](docs/STATUS.md) for their recorded states and [quality rules](QUALITY.md) for the evidence required to advance. Live work is tracked in the ledger described by the [tracking contract](docs/TRACKING.md).

Generated from [the journey catalog](docs/journeys/catalog.json). Each linked specification owns its acceptance criteria.
`
}

const stateLabels = {
  planned: 'Planned',
  in_progress: 'In progress',
  implemented: 'Complete',
  verified: 'Passed',
  failed: 'Failed',
  inconclusive: 'Inconclusive',
  absent: 'No evidence',
  released: 'Published',
  unknown: 'Unknown',
  stale: 'Needs recheck'
}

const sourceLabels = {
  current: 'Current at snapshot time',
  stale: 'Expired at snapshot time',
  unavailable: 'Unavailable',
  unconfigured: 'Not connected'
}

const assessments = [
  {
    key: 'implementation',
    label: 'Implementation',
    outcomes: [
      ['implemented', 'complete'],
      ['in_progress', 'in progress'],
      ['planned', 'planned'],
      ['stale', 'needs recheck'],
      ['unknown', 'unknown']
    ]
  },
  {
    key: 'verification',
    label: 'Verification',
    outcomes: [
      ['verified', 'passed'],
      ['failed', 'failed'],
      ['inconclusive', 'inconclusive'],
      ['absent', 'no evidence'],
      ['stale', 'needs recheck'],
      ['unknown', 'unknown']
    ]
  },
  {
    key: 'release',
    label: 'Release',
    outcomes: [
      ['released', 'confirmed published'],
      ['stale', 'needs recheck'],
      ['unknown', 'unknown']
    ]
  }
]

function renderAssessmentRow(assessment, journeyStates) {
  const counts = assessment.outcomes.map(([outcome, description], index) => {
    const count = journeyStates.filter(({state}) => state[assessment.key] === outcome).length
    // Keep the confirmed-success count visible, including zero. Other outcomes
    // appear only when a journey actually has that state.
    return count || index === 0 ? `${count} ${description}` : null
  }).filter(Boolean)

  return `| ${assessment.label} | ${counts.join(' · ')} |`
}

function renderJourneyStateRow({journey, state}) {
  const title = markdownCell(journey.title)
  const implementation = stateLabels[state.implementation]
  const verification = stateLabels[state.verification]
  const release = stateLabels[state.release]
  return `| [${title}](../${journey.spec}) | ${journey.id} | ${implementation} | ${verification} | ${release} |`
}

export function status(model) {
  const snapshot = model.snapshot
  const clock = new Date(snapshot.evaluatedAt ?? '2026-10-07T00:00:00Z')
  const journeyStates = model.catalog.journeys.map(journey => {
    const record = snapshot.records.find(record => record.id === journey.id)
    return {journey, state: classify(record, snapshot, clock)}
  })
  const summaryRows = assessments
    .map(assessment => renderAssessmentRow(assessment, journeyStates))
    .join('\n')
  const journeyRows = journeyStates.map(renderJourneyStateRow).join('\n')
  const candidate = snapshot.headCommit
    ? `[\`${snapshot.headCommit}\`](https://github.com/FRIKKern/gitgood/commit/${snapshot.headCommit})`
    : 'No candidate recorded'
  const ledgerReference = snapshot.sources.ledger.reference
  const liveLedgerLink = typeof ledgerReference === 'string' && ledgerReference.startsWith('https://')
    ? `[Open the live delivery ledger](${ledgerReference})`
    : 'See the [tracking contract](TRACKING.md) for ledger setup'
  const sources = [
    ['ledger', 'Implementation ledger'],
    ['evidence', 'Verification evidence'],
    ['releases', 'Release records']
  ]
  const sourceRows = sources.map(([key, label]) => {
    const sourceState = sourceLabels[freshness(snapshot, key, clock)]
    const observedAt = markdownCell(snapshot.sources[key].observedAt ?? 'Not observed')
    return `| ${label} | ${sourceState} | ${observedAt} |`
  }).join('\n')

  return `# Progress snapshot

This page is a saved observation of the delivery ledger and evidence. **It does not prove the current main branch or any open development branch.** It stays unchanged until the reporting inputs are refreshed and regenerated.

${liveLedgerLink} · [Delivery roadmap](ROADMAP.md) · [Execution order](EXECUTION.md) · [Documentation guide](README.md)

## What this snapshot says

| Assessment | Saved result |
|---|---|
${summaryRows}

These counts assess all ${journeyStates.length} product journeys end to end. A feature can have working code and passing component tests while its full journey is still in progress. Unknown and expired information cannot establish completion.

- **Implemented:** the ledger records the complete journey as built.
- **Verified:** recorded evidence passes the journey for this exact candidate and specification.
- **Released:** a matching publication record exists and verification still passes.

## Candidate and observation time

- **Snapshot evaluated at:** ${markdownCell(snapshot.evaluatedAt ?? 'Not recorded')}.
- **Candidate covered:** ${candidate}.
- **Freshness window:** ${snapshot.maxAgeHours} hours.

All states below were evaluated at the saved snapshot time, not at the moment you opened this page. Run \`npm run status\` for an age check now. A fresh ledger read cannot make an older proof current.

| Source | State at snapshot time | Last observation (UTC) |
|---|---|---|
${sourceRows}

## Journey by journey

| What you can do | ID | Implementation | Verification | Release |
|---|---|---|---|---|
${journeyRows}

**Needs recheck** means the source or proof is expired, or the evidence no longer matches the candidate/specification. **Unknown** means the source is disconnected, unavailable, or has no declared result. **No evidence** means the connected evidence source has no result for that journey. **Inconclusive** means a recorded assessment did not establish a pass.

## Refresh and inspect

Follow the [tracking contract](TRACKING.md) to collect observations with the scoped credential. Run \`npm run generate\` and \`npm run check\` after collection. The [detailed evidence map](images/journey-evidence.svg) provides another view of the same saved inputs.

Generated from [evidence/status.json](../evidence/status.json) and the [journey catalog](journeys/catalog.json). The [quality rules](../QUALITY.md) govern acceptance. Edit the source records through their owning systems; do not hand-edit this report.
`
}

const changelogCategories = ['Security', 'Added', 'Changed', 'Fixed', 'Deprecated', 'Removed']

function renderFragmentReference(reference, index) {
  const label = /^https:\/\//.test(reference) ? 'source' : 'details'
  return `[${label} ${index + 1}](${reference})`
}

function renderFragment(fragment) {
  const references = fragment.references.map(renderFragmentReference).join(', ')
  return `- ${fragment.summary}
  Sources: ${references}`
}

function renderChangelogEntries(fragments) {
  return changelogCategories.map(category => {
    const group = fragments.filter(fragment => fragment.category === category)
    if (!group.length) return null

    const entries = group.map(renderFragment).join('\n\n')
    return `### ${category}

${entries}`
  }).filter(Boolean).join('\n\n')
}

function renderRelease(release, fragments) {
  const includedFragments = release.fragments.map(id => fragments.find(fragment => fragment.id === id))
  const entries = renderChangelogEntries(includedFragments)
  const upgrade = release.upgrade ? `\nUpgrade: ${release.upgrade}\n` : ''

  return `
## ${release.version} — ${release.date}

Source commit: ${release.commit}.

${entries}
${upgrade}`
}

function renderChangelogHighlights(latestRelease, pendingCount) {
  // Keep README bounded as the detailed development history and release notes grow.
  if (latestRelease) {
    return `## What's new

**${latestRelease.version} — ${latestRelease.date}.** See the [release notes](CHANGELOG.md) for included changes and upgrade instructions.`
  }

  const changeLabel = pendingCount === 1 ? 'change is' : 'changes are'
  const pendingSummary = pendingCount
    ? `${pendingCount} development ${changeLabel} recorded in the [changelog](CHANGELOG.md#unreleased).`
    : 'No pending changelog entries.'

  return `## What's new

**Unreleased — development.** ${pendingSummary} No Gitgood application release has been published.`
}

export function changelog(model) {
  const assignedFragments = new Set(model.releases.releases.flatMap(release => release.fragments))
  const pendingFragments = model.fragments.filter(fragment => !fragment.withdrawn && !assignedFragments.has(fragment.id))
  const releases = [...model.releases.releases].sort((a, b) =>
    b.date.localeCompare(a.date) || b.version.localeCompare(a.version))
  const pendingEntries = renderChangelogEntries(pendingFragments) || 'No pending entries.'

  let body = `# Changelog

Development changes and published releases, grouped by the kind of change. Unreleased work has not been published as a Gitgood application release.

[Project overview](README.md) · [Progress snapshot](docs/STATUS.md) · [Changelog routine](changelog/ROUTINE.md)

Generated from reviewed fragments and [the release manifest](changelog/releases.json). This file does not publish a release.

## Unreleased

${pendingEntries}
`
  for (const release of releases) {
    body += renderRelease(release, model.fragments)
  }

  const highlights = renderChangelogHighlights(releases[0], pendingFragments.length)
  return {body, highlights}
}
