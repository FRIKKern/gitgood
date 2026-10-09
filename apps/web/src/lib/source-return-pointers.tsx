import {useEffect, useRef, useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api, type Session} from './api'
import {accessStore} from './access-state'

type Operation = {id: string; link_id: string; state: string; actor_id: number; actor: string; attempts: number; reason?: string; link_generation: string; connection_generation: string; automatic_retry: boolean}
const states: Record<string, string> = {
  queued: 'Return link queued.',
  paused: 'Automatic attempts paused after repeated source failures. Retry when source access recovers.',
  prepared: 'Return link prepared for Barkpark.',
  sending: 'Waiting for the Barkpark write result.',
  unknown: 'The write result is uncertain. Check the source before requesting another write.',
  applied: 'Barkpark confirmed the return-link write.',
  observed: 'The return link was observed in Barkpark. The original write receipt remains unknown.',
  denied: 'Barkpark refused this request.',
  conflict: 'The Paper changed or its owned return-link block conflicts. Check the Paper before another request.',
  unsupported: 'This Paper shape could not be updated safely.',
  stopped: 'This request stopped because its originating access or native link changed.',
}

export function SourceReturnPointers({endpoint, link, connectionGeneration, sourcePaperAvailable, writer, session, disabled}: {
  endpoint: string; link: {id: string; generation: string; state: string}; connectionGeneration?: string;
  sourcePaperAvailable: boolean; writer: boolean; session: Session; disabled: boolean
}) {
  const base = endpoint + '/' + link.id + '/return-pointers'
  const mounted = useRef(true)
  useEffect(() => {mounted.current = true; return () => {mounted.current = false}}, [])
  const operations = useQuery({queryKey: ['source-return-operations', session.user.id, base, link.generation],
    queryFn: ({signal}) => api<{operations: Operation[]}>(base, {signal}),
    refetchInterval: 3000, refetchIntervalInBackground: false, retry: false})
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('')
  const intent = useRef<{path: string; body: string; key: string} | null>(null)
  async function act(path: string, body: string) {
    if (busy || disabled) return
    const store = accessStore(), ticket = store?.ticket()
    const active = () => mounted.current && !!store && !!ticket && store.valid(ticket)
    if (intent.current?.path !== path || intent.current.body !== body)
      intent.current = {path, body, key: crypto.randomUUID()}
    setBusy(true); setMessage('')
    try {
      if (!active()) return
      await api(path, {method: 'POST', headers: {'x-gitgood-csrf': session.csrf,
        'idempotency-key': intent.current.key}, body})
      if (active()) {intent.current = null; setMessage('Request confirmed. Current source responsibility is shown below.')}
    } catch {
      if (active()) setMessage('The request could not be confirmed. Refresh its current state; changed originating access requires a new request.')
    } finally {
      if (active()) {await operations.refetch(); if (active()) setBusy(false)}
    }
  }
  const values = !operations.isError ? operations.data?.operations : undefined
  return <section aria-label="Barkpark return link">
    {writer && link.state === 'active' && sourcePaperAvailable && connectionGeneration &&
      <button disabled={busy || disabled || operations.isError} onClick={() => void act(base,
        JSON.stringify({generation: link.generation, connection_generation: connectionGeneration}))}>Add return link to Paper</button>}
    {message && <p role="status">{message}</p>}
    {operations.isError && <p role="alert">Return-link responsibility unavailable. <button onClick={() => void operations.refetch()}>Refresh return-link state</button></p>}
    {!!values?.length && <>
      <h4>Return link in Barkpark</h4>
      <p>Removing this native link preserves any return link already written in Barkpark.</p>
      {values.map(value => <div key={value.id}>
        <p>Requested by {value.actor}.</p>
        <p role="status">{states[value.state] ?? 'Return-link state could not be confirmed.'}</p>
        {writer && value.actor_id === session.user.id && !value.automatic_retry &&
          ['paused', 'unknown'].includes(value.state) && value.link_generation === link.generation &&
          value.connection_generation === connectionGeneration && sourcePaperAvailable &&
          <button className="subtle" disabled={busy || disabled} onClick={() => void act(base + '/' + value.id + '/retry',
            JSON.stringify({generation: link.generation, connection_generation: connectionGeneration}))}>Retry original return-link request</button>}
        {['unknown', 'sending', 'stopped', 'conflict'].includes(value.state) && sourcePaperAvailable && connectionGeneration &&
          <button className="subtle" disabled={busy || disabled} onClick={() => void act(base + '/' + value.id + '/observe',
            JSON.stringify({connection_generation: connectionGeneration}))}>Check return link in Barkpark</button>}
      </div>)}
    </>}
  </section>
}
