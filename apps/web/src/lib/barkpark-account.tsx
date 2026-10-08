import {useEffect, useRef, useState, type FormEvent} from 'react'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {api, ApiError, type Session} from './api'
import {accessStore} from './access-state'

type Connection = {
  state: 'unconfigured' | 'connected' | 'disconnected'; generation: string
  id?: string; origin?: string; workspace?: string; project?: string; dataset?: string
  source_identity?: {token_id: string; kind: string; label: string; permissions: string[];
    expires_at: string; verified_at: string}
}
function explanation(error: unknown) {
  if (!(error instanceof ApiError)) return 'The connection request could not be confirmed. Refresh its state before retrying.'
  const messages: Record<string, string> = {
    barkpark_unconfigured: 'Barkpark is not configured on this installation.',
    connection_key_unconfigured: 'This installation is not ready to store Barkpark credentials.',
    barkpark_scope_denied: 'Use a private API service credential with read access, a future expiry, and membership in only the selected workspace.',
    barkpark_access_denied: 'Barkpark refused access with this credential.',
    barkpark_scope_missing: 'The selected Barkpark workspace, project or dataset could not be found.',
    barkpark_contract_unavailable: 'Barkpark could not confirm a supported connection.',
    barkpark_unavailable: 'Barkpark is unavailable. Refresh your saved connection before retrying.',
    barkpark_busy: 'Barkpark requests are busy. Refresh the connection state before retrying.',
    connection_changed: 'The connection changed. Refresh its state before retrying.',
    idempotency_conflict: 'This request conflicts with an earlier operation. Refresh the connection state.',
    authorization_changed: 'Sign in again to manage your connection.',
    credential_scope_denied: 'This session cannot manage account connections.',
    invalid_connection_request: 'Check the workspace, project, dataset and credential.',
  }
  return messages[error.message] ?? 'The connection request could not be confirmed. Refresh its state before retrying.'
}
export function BarkparkAccount({session}: {session: Session}) {
  const client = useQueryClient()
  const mounted = useRef(true)
  useEffect(() => {mounted.current = true; return () => {mounted.current = false}}, [])
  const queryKey = ['barkpark-account', session.user.id]
  const connection = useQuery({queryKey, queryFn: ({signal}) => api<Connection>('/connections/barkpark', {signal}),
    refetchInterval: 5000, refetchIntervalInBackground: false, retry: false})
  const current = connection.isError ? undefined : connection.data
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!current || busy) return
    const store = accessStore(), ticket = store?.ticket()
    const active = () => mounted.current && !!store && !!ticket && store.valid(ticket)
    const form = event.currentTarget
    const values = Object.fromEntries(new FormData(form))
    const body = JSON.stringify({...values, expected_generation: current.generation})
    // Never retain a raw credential in intent refs, storage or connection query data.
    const secret = form.elements.namedItem('token')
    if (secret instanceof HTMLInputElement) secret.value = ''
    setBusy(true); setMessage('')
    await client.cancelQueries({queryKey})
    try {
      if (!active()) return
      await api('/connections/barkpark', {method: 'POST',
        headers: {'x-gitgood-csrf': session.csrf, 'idempotency-key': crypto.randomUUID()}, body})
      if (active()) setMessage('Connection request confirmed. Current saved state is shown below.')
    } catch (error) {if (active()) setMessage(explanation(error))}
    finally {
      if (active()) {await connection.refetch(); if (active()) setBusy(false)}
    }
  }
  async function disconnect() {
    if (!current || current.state !== 'connected' || busy) return
    const store = accessStore(), ticket = store?.ticket()
    const active = () => mounted.current && !!store && !!ticket && store.valid(ticket)
    setBusy(true); setMessage('')
    await client.cancelQueries({queryKey})
    try {
      if (!active()) return
      await api('/connections/barkpark/disconnect', {method: 'POST',
        headers: {'x-gitgood-csrf': session.csrf, 'idempotency-key': crypto.randomUUID()},
        body: JSON.stringify({expected_generation: current.generation})})
      if (active()) setMessage('Disconnect request confirmed. Current saved state is shown below.')
    } catch (error) {if (active()) setMessage(explanation(error))}
    finally {
      if (active()) {await connection.refetch(); if (active()) setBusy(false)}
    }
  }
  return <section className="panel" aria-label="Barkpark connection">
    <h2>Barkpark connection</h2>
    <p>Your connection is private to your account. Repository permissions still apply independently.</p>
    {connection.isPending && <p role="status">Loading your connection…</p>}
    {connection.isError && <p role="alert">Connection state unavailable. <button disabled={busy} onClick={() => void connection.refetch()}>Refresh connection</button></p>}
    {message && <p role="status">{message}</p>}
    {current && <div>
      <p>{current.state === 'connected' ? 'Saved connection' : current.state === 'disconnected' ? 'Disconnected' : 'No saved connection'}</p>
      {current.state === 'connected' && current.source_identity && <>
        <p style={{overflowWrap: 'anywhere'}}>{current.origin} · {current.workspace} / {current.project} / {current.dataset}</p>
        <p>API service: {current.source_identity.label || current.source_identity.token_id}. Permissions: {current.source_identity.permissions.join(', ')}.</p>
        <p>Expires {new Date(current.source_identity.expires_at).toLocaleString()}. Verified {new Date(current.source_identity.verified_at).toLocaleString()}.</p>
        <button className="subtle" disabled={busy} onClick={() => void disconnect()}>Disconnect Barkpark</button>
      </>}
      <form key={current.generation} onSubmit={connect}>
        <p>Use a private API service credential with read access, an expiry, and one workspace. Linked records are checked with Barkpark when read.</p>
        <label>Barkpark workspace<input name="workspace" required pattern="[a-z][a-z0-9-]{0,63}" defaultValue={current.workspace ?? ''} maxLength={64} /></label>
        <label>Barkpark project<input name="project" required pattern="[a-z][a-z0-9-]{0,63}" defaultValue={current.project ?? 'default'} maxLength={64} /></label>
        <label>Barkpark dataset<input name="dataset" required pattern="[a-z][a-z0-9-]{0,63}" defaultValue={current.dataset ?? 'production'} maxLength={64} /></label>
        <label>Barkpark API credential<input name="token" type="password" autoComplete="off" required minLength={16} maxLength={512} /></label>
        <button disabled={busy}>{busy ? 'Updating connection…' : current.state === 'connected' ? 'Replace Barkpark credential' : 'Connect Barkpark'}</button>
      </form>
    </div>}
  </section>
}
