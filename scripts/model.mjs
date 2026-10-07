import fs from 'node:fs'
import path from 'node:path'
import {fileURLToPath} from 'node:url'

export const root = fileURLToPath(new URL('../', import.meta.url))
export const read = name => fs.readFileSync(path.join(root, name), 'utf8')
const json = name => JSON.parse(read(name))
export function load() {
  return {
    catalog: json('docs/journeys/catalog.json'),
    milestones: json('docs/milestones.json'),
    snapshot: json('evidence/status.json'),
    releases: json('changelog/releases.json'),
    fragments: fs.readdirSync(path.join(root, 'changelog/fragments')).filter(n => n.endsWith('.json')).sort().map(n => json('changelog/fragments/' + n))
  }
}
const nonempty = x => typeof x === 'string' && x.trim().length > 0
function unique(items, key, label, errors) {
  const values = items.map(x => x[key])
  if (new Set(values).size !== values.length) errors.push('Duplicate ' + label)
}
export function validate(m, now = new Date()) {
  const errors = []
  for (const k of ['catalog', 'milestones', 'snapshot', 'releases']) {
    if (m[k]?.schemaVersion !== 1) errors.push('Unsupported schema: ' + k)
  }
  const journeys = m.catalog?.journeys, milestones = m.milestones?.milestones
  if (!Array.isArray(journeys) || !Array.isArray(milestones) || !Array.isArray(m.snapshot?.records) || !Array.isArray(m.fragments) || !Array.isArray(m.releases?.releases)) return [...errors, 'Missing catalog/record arrays']
  unique(journeys, 'id', 'journey ID', errors)
  unique(milestones, 'id', 'milestone ID', errors)
  unique(m.snapshot.records, 'id', 'status ID', errors)
  unique(m.fragments, 'id', 'fragment ID', errors)
  unique(m.releases.releases, 'version', 'release version', errors)
  const ids = new Set(journeys.map(j => j.id))
  const phases = new Set(milestones.map(p => p.id))
  for (const j of journeys) {
    if (!/^J\d{2}$/.test(j.id) || !nonempty(j.title) || typeof j.required !== 'boolean') errors.push('Invalid journey: ' + j.id)
    if (!phases.has(j.milestone)) errors.push('Unknown milestone: ' + j.id)
    if (j.spec !== 'docs/journeys/' + j.id + '.md') errors.push('Unexpected journey path: ' + j.id)
  }
  for (const p of milestones) {
    if (!/^M\d+$/.test(p.id) || !nonempty(p.title) || !nonempty(p.work) || !nonempty(p.exit) || !Array.isArray(p.dependsOn)) errors.push('Invalid milestone: ' + p.id)
    for (const d of p.dependsOn ?? []) if (!phases.has(d) || d === p.id) errors.push('Invalid milestone dependency: ' + p.id)
  }
  const visited = new Set(), active = new Set()
  const visit = id => {
    if (active.has(id)) { errors.push('Cyclic milestone dependency'); return }
    if (visited.has(id)) return
    active.add(id)
    for (const d of milestones.find(p => p.id === id)?.dependsOn ?? []) visit(d)
    active.delete(id); visited.add(id)
  }
  for (const id of phases) visit(id)
  const s = m.snapshot
  if (!nonempty(s.baseline) || !nonempty(s.specRevision) || !(s.maxAgeHours > 0 && s.maxAgeHours <= 168)) errors.push('Invalid snapshot baseline/freshness')
  if (s.headCommit !== null && !/^[0-9a-f]{40,64}$/.test(s.headCommit)) errors.push('Head commit must be a real commit identity or null')
  if (s.evaluatedAt != null && (!Number.isFinite(Date.parse(s.evaluatedAt)) || Date.parse(s.evaluatedAt) > now.getTime() + 300000)) errors.push('Invalid snapshot evaluation time')
  for (const name of ['ledger', 'evidence', 'releases']) {
    const src = s.sources?.[name]
    if (!src || !['unconfigured', 'ok', 'unavailable'].includes(src.status)) { errors.push('Invalid source: ' + name); continue }
    if (src.status === 'ok' && (!nonempty(src.observedAt) || !nonempty(src.reference) || !nonempty(s.evaluatedAt))) errors.push('Healthy source needs timestamp, reference, and evaluation time: ' + name)
    if (src.observedAt != null && (!Number.isFinite(Date.parse(src.observedAt)) || Date.parse(src.observedAt) > now.getTime() + 300000)) errors.push('Invalid source timestamp: ' + name)
    if (src.observedAt && s.evaluatedAt && Date.parse(src.observedAt) > Date.parse(s.evaluatedAt)) errors.push('Observation newer than snapshot: ' + name)
  }
  for (const r of s.records) {
    if (!ids.has(r.id)) errors.push('Unknown status journey: ' + r.id)
    if (r.implementation && (!['planned', 'in_progress', 'implemented'].includes(r.implementation.state) || !nonempty(r.implementation.reference))) errors.push('Invalid implementation: ' + r.id)
    if (r.verification) {
      const v = r.verification
      if (!['verified', 'failed', 'inconclusive'].includes(v.state) || !nonempty(v.reference)) errors.push('Invalid verification: ' + r.id)
      if (v.state === 'verified' && (v.passed !== true || !/^[0-9a-f]{40,64}$/.test(v.codeCommit ?? '') || !nonempty(v.specRevision))) errors.push('Verification lacks proof identity: ' + r.id)
    }
    if (r.release) {
      const v = r.release
      if (v.state !== 'released' || v.accepted !== true || !nonempty(v.version) || !nonempty(v.reference) || !/^[0-9a-f]{40,64}$/.test(v.codeCommit ?? '')) errors.push('Release lacks publication identity: ' + r.id)
    }
  }
  const categories = new Set(['Added', 'Changed', 'Fixed', 'Deprecated', 'Removed', 'Security'])
  for (const f of m.fragments) {
    if (!/^[a-z0-9][a-z0-9-]+$/.test(f.id) || !categories.has(f.category) || !nonempty(f.summary) || !['planning', 'product', 'operator'].includes(f.impact) || !Array.isArray(f.references) || !f.references.length || !Array.isArray(f.journeys) || typeof f.withdrawn !== 'boolean') errors.push('Invalid fragment: ' + f.id)
    for (const id of f.journeys ?? []) if (!ids.has(id)) errors.push('Unknown fragment journey: ' + id)
  }
  const assigned = new Set()
  for (const release of m.releases.releases) {
    if (!nonempty(release.version) || !/^\d{4}-\d{2}-\d{2}$/.test(release.date ?? '') || !Number.isFinite(Date.parse(release.date)) || !/^[0-9a-f]{40,64}$/.test(release.commit ?? '') || !Array.isArray(release.fragments)) errors.push('Invalid release manifest: ' + release.version)
    for (const id of release.fragments ?? []) {
      const f = m.fragments.find(f => f.id === id)
      if (!f || f.withdrawn) errors.push('Missing/withdrawn release fragment: ' + id)
      if (assigned.has(id)) errors.push('Fragment assigned twice: ' + id)
      assigned.add(id)
    }
  }
  return errors
}
export function freshness(snapshot, name, now = new Date()) {
  const source = snapshot.sources[name]
  if (source.status !== 'ok') return source.status
  const age = now.getTime() - Date.parse(source.observedAt)
  return age > snapshot.maxAgeHours * 3600000 ? 'stale' : 'current'
}
export function classify(record, snapshot, now) {
  const clock = now ?? new Date(snapshot.evaluatedAt ?? '2026-10-07T00:00:00Z')
  const status = {implementation: 'unknown', verification: 'unknown', release: 'unknown'}
  const states = {implementation: 'ledger', verification: 'evidence', release: 'releases'}
  for (const [key, source] of Object.entries(states)) {
    const fresh = freshness(snapshot, source, clock)
    if (fresh !== 'current') { status[key] = fresh === 'stale' ? 'stale' : 'unknown'; continue }
    status[key] = record?.[key]?.state ?? (key === 'verification' ? 'absent' : 'unknown')
  }
  const v = record?.verification
  if (status.verification === 'verified' && (v.codeCommit !== snapshot.headCommit || v.specRevision !== snapshot.specRevision)) status.verification = 'stale'
  if (status.release === 'released' && (record.release.codeCommit !== snapshot.headCommit || status.verification !== 'verified')) status.release = 'stale'
  return status
}
export function releaseProblems(m, now = new Date()) {
  const errors = validate(m, now)
  if (!m.snapshot.headCommit) errors.push('No implementation candidate commit')
  for (const src of ['ledger', 'evidence', 'releases']) if (freshness(m.snapshot, src, now) !== 'current') errors.push('Source is not current: ' + src)
  for (const j of m.catalog.journeys.filter(j => j.required)) {
    const state = classify(m.snapshot.records.find(r => r.id === j.id), m.snapshot, now)
    if (state.implementation !== 'implemented' || state.verification !== 'verified') errors.push('Acceptance incomplete: ' + j.id)
  }
  return errors
}
