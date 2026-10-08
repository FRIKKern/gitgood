import {useEffect, useRef, useState, type FormEvent} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api, type Session} from './api'
import {accessStore} from './access-state'
import {SourceReturnPointers} from './source-return-pointers'
import {CriterionEvidence} from './criterion-evidence'

type Link = {id: string; generation: string; state: 'active' | 'removed'}
type Connection = {state: 'connected' | 'disconnected' | 'unconfigured'; generation: string}
type Source = Link & {source_state: string; title?: string; summary?: string; revision?: string;
  studio_url?: string; connection_generation?: string; source_actor?: {label: string};
  locator?: {document_id: string; type: string}}
const messages: Record<string, string> = {
  denied: 'Barkpark refused source access for your connection.',
  missing_or_inaccessible: 'This record could not be found with your source access. It may be missing or inaccessible.',
  connection_changed: 'Your source connection changed. Refresh its saved state.',
  unavailable: 'Barkpark context is unavailable. Your Gitgood change remains accessible.',
  removed: 'This native link was removed.',
  access_changed: 'Your access changed. Refresh to check it again.',
}

export function SourceLinks({base, pullId, session, writer}: {base: string; pullId: string; session: Session; writer: boolean}) {
  const endpoint = base + '/pulls/' + pullId + '/links'
  const mounted = useRef(true)
  useEffect(() => {mounted.current = true; return () => {mounted.current = false}}, [])
  const links = useQuery({queryKey: ['source-links', session.user.id, endpoint],
    queryFn: ({signal}) => api<{links: Link[]}>(endpoint, {signal}),
    refetchInterval: 5000, refetchIntervalInBackground: false, retry: false})
  const connection = useQuery({queryKey: ['barkpark-account', session.user.id],
    queryFn: ({signal}) => api<Connection>('/connections/barkpark', {signal}),
    refetchInterval: 5000, refetchIntervalInBackground: false, retry: false})
  const current = connection.isError ? undefined : connection.data
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('')
  const intent = useRef<{body: string; endpoint: string; key: string} | null>(null)
  async function mutate(path: string, body: string) {
    if (busy) return
    const store = accessStore(), ticket = store?.ticket()
    const active = () => mounted.current && !!store && !!ticket && store.valid(ticket)
    if (intent.current?.body !== body || intent.current.endpoint !== path)
      intent.current = {body, endpoint: path, key: crypto.randomUUID()}
    setBusy(true); setMessage('')
    try {
      if (!active()) return
      await api(path, {method: 'POST', headers: {'x-gitgood-csrf': session.csrf,
        'idempotency-key': intent.current.key}, body})
      if (active()) {intent.current = null; setMessage('Link request confirmed. Current links are shown below.')}
    } catch {
      if (active()) setMessage('The link request could not be confirmed. Refresh current links before retrying.')
    } finally {
      if (active()) {await links.refetch(); if (active()) setBusy(false)}
    }
  }
  function attach(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (current?.state !== 'connected') return
    const values = Object.fromEntries(new FormData(event.currentTarget))
    void mutate(endpoint, JSON.stringify({...values, connection_generation: current.generation}))
  }
  return <section className="collaboration-panel" aria-label="Linked Barkpark records">
    <h2>Linked tasks and specifications</h2>
    <p>Barkpark owns these records. Source context uses your own connection and its current permissions.</p>
    <p><a href="/">Manage your Barkpark connection</a></p>
    {message && <p role="status">{message}</p>}
    {links.isError ? <p role="alert">Linked records unavailable. <button onClick={() => void links.refetch()}>Refresh linked records</button></p> :
      links.isPending ? <p role="status">Loading linked records…</p> :
      links.data?.links.length === 0 ? <p>No linked records.</p> :
      links.data?.links.map(link => <SourceLink key={link.id + ':' + link.generation + ':' + (current?.generation ?? 'unavailable')}
        link={link} endpoint={endpoint} connection={current} actor={session.user.id} session={session} writer={writer} busy={busy}
        remove={() => void mutate(endpoint + '/' + link.id + '/remove', JSON.stringify({generation: link.generation}))}
        refreshConnection={() => void connection.refetch()} />)}
    {connection.isError && <p role="alert">Connection state unavailable. <button onClick={() => void connection.refetch()}>Refresh connection state</button></p>}
    {writer && current?.state === 'connected' && <form onSubmit={attach}>
      <h3>Attach a Barkpark record</h3>
      <label>Record type<select name="type" defaultValue="paper"><option value="paper">Paper specification</option><option value="task">Task</option></select></label>
      <label>Barkpark document ID<input name="document_id" required maxLength={256} pattern="[a-zA-Z0-9][a-zA-Z0-9_.-]*" /></label>
      <p>Use the exact ID from the selected workspace, project and dataset. Include the drafts. prefix when selecting a draft.</p>
      <button disabled={busy || links.isError}>{busy ? 'Updating native link…' : 'Attach source record'}</button>
      <p>This attaches the Barkpark record to this change.</p>
    </form>}
    {writer && current && current.state !== 'connected' && <p>Connect Barkpark from your account to attach a record.</p>}
  </section>
}

function SourceLink({link, endpoint, connection, actor, session, writer, busy, remove, refreshConnection}: {
  link: Link; endpoint: string; connection?: Connection; actor: number; session: Session; writer: boolean; busy: boolean;
  remove: () => void; refreshConnection: () => void
}) {
  const [opened, setOpened] = useState(false)
  const generation = connection?.state === 'connected' ? connection.generation : undefined
  const source = useQuery({queryKey: ['source-context', actor, endpoint, link.id, link.generation, generation],
    enabled: opened && link.state === 'active' && !!generation,
    queryFn: ({signal}) => api<Source>(endpoint + '/' + link.id + '?connection_generation=' + encodeURIComponent(generation!), {signal}),
    refetchInterval: opened ? 5000 : false, refetchIntervalInBackground: false, retry: false})
  const current = !source.isError && source.data?.generation === link.generation &&
    source.data.connection_generation === generation && source.data.source_state === 'available' ? source.data : undefined
  const sourceUrl = current?.studio_url && /^https?:\/\//.test(current.studio_url) ? current.studio_url : undefined
  return <article className="review-event" aria-label="Linked Barkpark record">
    <p>Linked record · {link.state === 'active' ? 'attached' : 'removed'}</p>
    {link.state === 'active' && <>
      {!generation ? <p>Source context requires your current Barkpark connection.</p> :
        <button className="subtle" onClick={() => setOpened(value => !value)}>{opened ? 'Hide source context' : 'Open source context'}</button>}
      {opened && generation && (source.isError ? <p role="alert">Source context could not be confirmed. <button onClick={() => void source.refetch()}>Retry source context</button></p> :
        current ? <div><h3>{current.title || current.locator?.document_id}</h3><p>{current.summary}</p>
          <p>{current.locator?.type} · {current.locator?.document_id} · source revision {current.revision}</p>
          <p>Read through API service {current.source_actor?.label}.</p>
          {sourceUrl && <a href={sourceUrl} target="_blank" rel="noopener noreferrer">Open in Barkpark Studio</a>}
        </div> : source.data ? <p role="alert">{messages[source.data.source_state] ?? 'Source context could not be confirmed.'}
          <button onClick={() => void source.refetch()}>Retry source context</button>
          {source.data.source_state === 'connection_changed' && <button onClick={refreshConnection}>Refresh source connection</button>}
        </p> : <p role="status">Checking your source access…</p>)}
      {writer && <button className="subtle" disabled={busy} onClick={remove}>Remove linked record</button>}
    </>}
    <SourceReturnPointers endpoint={endpoint} link={link} connectionGeneration={generation}
      sourcePaperAvailable={!!current && current.locator?.type === 'paper'} writer={writer}
      session={session} disabled={busy} />
    {current?.locator?.type === 'task' && generation && <CriterionEvidence endpoint={endpoint}
      link={link} generation={generation} session={session} writer={writer} />}
  </article>
}
