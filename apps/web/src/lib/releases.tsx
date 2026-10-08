import {useEffect, useState} from 'react'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {api, type Session} from './api'

type Asset = {id: string; name: string; sha256: string; size: number; state: string}
type Release = {id: string; tag: string; tag_object: string; commit_sha: string; base_sha: string | null; title: string; notes: string; notes_digest: string; state: string; version: number; published_at: string | null; withdrawn_at: string | null; changes: {commits: {sha: string; subject: string}[]}; assets: Asset[]}
type Event = {id: string; kind: string; actor_id: number; reason: string; inserted_at: string; snapshot: Release}
type ReleaseSummary = Pick<Release, 'id' | 'tag' | 'commit_sha' | 'title' | 'state' | 'published_at'>
type Tag = {tag: string; object: string; commit_sha: string}
type Pending = {path: string; body: Record<string, unknown>; key: string}

const fingerprint = async (body: ArrayBuffer) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', body))].map(b => b.toString(16).padStart(2, '0')).join('')
export function Releases({base, session}: {base: string; session?: Session}) {
  const client = useQueryClient()
  const [selected, setSelected] = useState('')
  const [title, setTitle] = useState(''), [notes, setNotes] = useState(''), [tag, setTag] = useState(''), [baseSha, setBaseSha] = useState('')
  const [editTitle, setEditTitle] = useState(''), [editNotes, setEditNotes] = useState(''), [reason, setReason] = useState('')
  const [file, setFile] = useState<File | null>(null), [assetKey, setAssetKey] = useState('')
  const [pending, setPending] = useState<Pending | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const team = decodeURIComponent(base.split('/')[2])
  const writer = session?.teams.some(t => t.team === team && ['owner', 'writer'].includes(t.role))
  const list = useQuery({queryKey: ['releases', base, session?.user.id], enabled: !!session, retry: false,
    queryFn: async () => (await api<{releases: ReleaseSummary[]}>(base + '/releases')).releases})
  const tags = useQuery({queryKey: ['tags', base, session?.user.id], enabled: !!session && !!writer, retry: false,
    queryFn: async () => (await api<{tags: Tag[]}>(base + '/tags')).tags})
  const detail = useQuery({queryKey: ['release', base, selected, session?.user.id], enabled: !!session && !!selected, retry: false,
    queryFn: () => api<{release: Release; events: Event[]}>(base + '/releases/' + selected)})
  const release = detail.data?.release
  useEffect(() => {
    const follow = () => {const match = /^#release-([0-9a-f-]{36})$/.exec(window.location.hash); setSelected(match?.[1] ?? '')}
    follow(); window.addEventListener('hashchange', follow)
    return () => window.removeEventListener('hashchange', follow)
  }, [base])
  useEffect(() => {
    if (release) {setEditTitle(release.title); setEditNotes(release.notes); setReason('')}
  }, [release?.id, release?.version])
  useEffect(() => {setFile(null); setAssetKey(''); setPending(null); setError('')}, [selected])
  async function refresh() {
    await client.invalidateQueries({queryKey: ['releases', base]})
    if (selected) await detail.refetch()
  }
  async function submit(request: Pending) {
    if (!session) return
    setPending(request); setBusy(true); setError('')
    try {
      const result = await api<{release: Release}>(request.path, {method: 'POST',
        headers: {'x-gitgood-csrf': session.csrf, 'idempotency-key': request.key}, body: JSON.stringify(request.body)})
      window.location.hash = 'release-' + result.release.id
      setSelected(result.release.id); setPending(null); setTitle(''); setNotes('')
    } catch (e) {setError(e instanceof Error ? e.message.replaceAll('_', ' ') : 'Release unavailable. Retry the same operation.')}
    finally {setBusy(false); await refresh()}
  }
  function request(path: string, body: Record<string, unknown>) {void submit({path, body, key: crypto.randomUUID()})}
  async function upload() {
    if (!file || !session || !release) return
    setBusy(true); setError('')
    try {
      if (file.size < 1 || file.size > 16_777_216) throw new Error('Choose an asset from 1 byte to 16 MiB.')
      const sha = await fingerprint(await file.arrayBuffer())
      let asset = release.assets.find(a => a.name === file.name && a.sha256 === sha && a.size === file.size)
      if (!asset) asset = (await api<{asset: Asset}>(base + '/releases/' + release.id + '/assets', {method: 'POST',
        headers: {'x-gitgood-csrf': session.csrf, 'idempotency-key': assetKey}, body: JSON.stringify({name: file.name, sha256: sha, size: file.size})})).asset
      if (asset.state !== 'ready') {
        await api(base + '/releases/' + release.id + '/assets/' + asset.id + '/source', {method: 'PUT',
          headers: {'x-gitgood-csrf': session.csrf, 'content-type': 'application/octet-stream'}, body: file})
      }
      setFile(null)
    } catch (e) {setError(e instanceof Error ? e.message.replaceAll('_', ' ') : 'Asset unavailable. Retry the same file.')}
    finally {setBusy(false); await refresh()}
  }
  async function cancel(asset: Asset) {
    if (!session || !release) return
    setBusy(true); setError('')
    try {await api(base + '/releases/' + release.id + '/assets/' + asset.id, {method: 'DELETE', headers: {'x-gitgood-csrf': session.csrf}})}
    catch (e) {setError(e instanceof Error ? e.message.replaceAll('_', ' ') : 'Cancellation unavailable')}
    finally {setBusy(false); await refresh()}
  }
  if (!session) return null
  return <section className="panel releases-panel" aria-label="Releases">
    <h2>Releases</h2><p>Published releases identify an existing Git tag, its commit and checksummed assets. A draft is work in progress.</p>
    {list.error ? <p role="alert">Releases unavailable. <button onClick={() => void list.refetch()}>Retry releases</button></p> :
      list.data?.length === 0 ? <p>No releases recorded.</p> : <ul className="release-list">{list.data?.map(item =>
        <li key={item.id}><a href={'#release-' + item.id}>{item.title}</a><span>{item.tag} · {item.state}{item.published_at && ' · ' + item.published_at}</span></li>)}</ul>}
    <button className="subtle" onClick={() => void refresh()}>Refresh releases</button>
    {writer && <details><summary>Create release draft</summary>
      {tags.error ? <p role="alert">Tags unavailable. <button onClick={() => void tags.refetch()}>Retry tags</button></p> :
      <form onSubmit={e => {e.preventDefault(); const selectedTag = tags.data?.find(t => t.tag === tag); if (selectedTag) request(base + '/releases', {tag, commit_sha: selectedTag.commit_sha, base_sha: baseSha || null, title, notes})}}>
        <label>Release tag<select aria-label="Release tag" value={tag} onChange={e => setTag(e.target.value)} required><option value="">Choose a tag</option>{tags.data?.map(t => <option key={t.tag}>{t.tag}</option>)}</select></label>
        <p>Create and push a commit tag with Git first. Tags pointing to a file or tree cannot be released.</p>
        <button type="button" className="subtle" onClick={() => void tags.refetch()}>Refresh tags</button>
        <label>Previous release<select value={baseSha} onChange={e => setBaseSha(e.target.value)}><option value="">All reachable commits · up to 200</option>{list.data?.filter(r => r.state === 'published').map(r => <option key={r.id} value={r.commit_sha}>{r.tag}</option>)}</select></label>
        <label>Release title<input value={title} onChange={e => setTitle(e.target.value)} required maxLength={200}/></label>
        <label>Release notes<textarea value={notes} onChange={e => setNotes(e.target.value)} required maxLength={16384}/></label>
        <button disabled={busy || !!pending}>Save draft</button>
      </form>}
    </details>}
    {error && <p role="alert">{error}{pending && <button disabled={busy} onClick={() => void submit(pending)}>Retry same release operation</button>}{file && <button disabled={busy} onClick={() => void upload()}>Retry same asset</button>}
      <button disabled={busy} onClick={() => {setPending(null); setError(''); void refresh()}}>Refresh current record</button></p>}
    {selected && (detail.error ? <p role="alert">This release is unavailable. <button onClick={() => void detail.refetch()}>Retry release</button></p> : release ? <article id={'release-' + release.id} className="release-detail">
      <h3>{release.title}</h3><p role="status">Release {release.state}</p>
      <p>Tag {release.tag} · commit <code>{release.commit_sha}</code></p><p className="context-note">Tag object <code>{release.tag_object}</code>{release.base_sha && <> · Changes since <code>{release.base_sha}</code></>}</p>
      <pre className="release-notes">{release.notes}</pre>
      <details><summary>Included commits · {release.changes.commits.length}</summary><ol className="history">{release.changes.commits.map(commit =>
        <li key={commit.sha}><a href={base + '?' + new URLSearchParams({sha: commit.sha})}>{commit.subject}</a><code>{commit.sha}</code></li>)}</ol></details>
      <h4>Assets</h4>{release.assets.length === 0 && <p>No assets attached.</p>}
      {release.assets.map(asset => <div className="release-asset" key={asset.id}>
        <p>{release.state === 'published' && asset.state === 'ready' ? <a href={'/api' + base + '/releases/' + release.id + '/assets/' + asset.id + '/download'} download={asset.name}>{asset.name}</a> : <span>{asset.name}</span>} · {asset.state} · {asset.size} bytes</p>
        <code>SHA-256 {asset.sha256}</code>
        {writer && release.state === 'draft' && asset.state === 'waiting' && <button disabled={busy} onClick={() => void cancel(asset)}>Cancel waiting asset</button>}
      </div>)}
      {release.state === 'withdrawn' && <p>This release was withdrawn. Its claims and history remain available; assets are no longer downloadable.</p>}
      {writer && release.state === 'draft' && <><label>Release asset<input aria-label="Release asset" type="file" disabled={busy} onChange={e => {setFile(e.target.files?.[0] ?? null); setAssetKey(crypto.randomUUID()); setError('')}}/></label><p>Up to 8 assets, each at most 16 MiB. Names use letters, numbers, dots, dashes and underscores.</p>
        <button disabled={busy || !file} onClick={() => void upload()}>Attach asset</button>
        <button disabled={busy || !!pending || !release.assets.length || release.assets.some(a => a.state !== 'ready')}
          onClick={() => request(base + '/releases/' + release.id + '/actions', {kind: 'publish', version: release.version, notes_digest: release.notes_digest})}>Publish reviewed release</button>
      </>}
      {writer && release.state !== 'withdrawn' && <details><summary>{release.state === 'draft' ? 'Edit draft notes' : 'Correct or withdraw release'}</summary>
        <form onSubmit={e => {e.preventDefault(); request(base + '/releases/' + release.id + '/actions', {kind: release.state === 'draft' ? 'revise' : 'correct', version: release.version, title: editTitle, notes: editNotes, ...(release.state === 'published' ? {reason} : {})})}}>
          <label>Updated release title<input value={editTitle} onChange={e => setEditTitle(e.target.value)} required maxLength={200}/></label>
          <label>Updated release notes<textarea value={editNotes} onChange={e => setEditNotes(e.target.value)} required maxLength={16384}/></label>
          {release.state === 'published' && <label>Correction or withdrawal reason<textarea value={reason} onChange={e => setReason(e.target.value)} required maxLength={2048}/></label>}
          <button disabled={busy || !!pending}>{release.state === 'draft' ? 'Save revised draft' : 'Record correction'}</button>
          {release.state === 'published' && <button type="button" disabled={busy || !!pending || !reason.trim()} onClick={() =>
            request(base + '/releases/' + release.id + '/actions', {kind: 'withdraw', version: release.version, reason})}>Withdraw release</button>}
        </form>
      </details>}
      <details><summary>Release history</summary><p>Most recent 100 events. Earlier events are retained in storage.</p>{detail.data?.events.map(event => <div className="review-event" key={event.id}>
        <p>{event.kind.replaceAll('_', ' ')} · actor {event.actor_id} · <time>{event.inserted_at}</time></p>{event.reason && <p>{event.reason}</p>}
        <p>Revision {event.snapshot.version} · {event.snapshot.state}</p><pre>{event.snapshot.notes}</pre>
      </div>)}</details>
    </article> : <p>Loading release...</p>)}
  </section>
}
