import {useEffect, useRef, useState, type FormEvent} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api, privateRequest, ApiError, type Session} from './api'
import {accessStore} from './access-state'

type Criterion = {index: number; text: string; sha256: string; state: string; evidence_id: string | null}
type EvidenceEvent = {kind: string; reason: string; actor_id: number; recorded_at: string}
type Record = {id: string; criterion_index: number; criterion_sha256: string; source_revision: string;
  source_sha: string; target_sha: string; outcome: string; state: string; actor_id: number; recorded_at: string;
  manifest: {commands: string[]; environment: {[key: string]: string}; producer: string; observed_at: string};
  artifact: {name: string; size: number; sha256: string; available: boolean};
  events: EvidenceEvent[]; events_total: number; events_next_cursor: string | null}
type View = {source: {id: string; generation: string; connection_generation?: string; source_state: string; revision?: string};
  source_sha?: string; target_sha?: string; criteria: Criterion[]; records: Record[]; observed_at?: string; profile?: string;
  history?: {total: number; next_cursor: string | null}}
const states: {[key: string]: string} = {passed: 'Passed · producer result', failed: 'Failed', inconclusive: 'Inconclusive',
  absent: 'Absent · no evidence', stale: 'Stale · reassessment needed', unavailable: 'Unavailable · artifact withdrawn'}
const digest = async (bytes: ArrayBuffer) => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), value => value.toString(16).padStart(2, '0')).join('')

export function CriterionEvidence({endpoint, link, generation, session, writer, recoveryOnly = false}: {
  endpoint: string; link: {id: string; generation: string}; generation: string; session: Session; writer: boolean; recoveryOnly?: boolean
}) {
  const path = endpoint + '/' + link.id + '/evidence'
  const mounted = useRef(true)
  useEffect(() => {mounted.current = true; return () => {mounted.current = false}}, [])
  const [historyCursor, setHistoryCursor] = useState<string | null>(null)
  const [historyStack, setHistoryStack] = useState<(string | null)[]>([])
  const [historyExpanded, setHistoryExpanded] = useState(false)
  const query = useQuery({queryKey: ['criterion-evidence', session.user.id, path, link.generation, generation, historyCursor],
    enabled: !recoveryOnly,
    queryFn: ({signal}) => api<View>(path + '?connection_generation=' + encodeURIComponent(generation) +
      (historyCursor ? '&cursor=' + encodeURIComponent(historyCursor) : ''), {signal}),
    refetchInterval: 5000, refetchIntervalInBackground: false, retry: false})
  const view = !query.isError && query.data?.source.generation === link.generation &&
    query.data.source.connection_generation === generation && query.data.source.source_state === 'available' ? query.data : undefined
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('')
  type Intent = {path: string; body: string; key: string; id?: string}
  const intent = useRef<Intent | null>(null), inFlight = useRef(false), preparing = useRef(false)
  const [pending, setPending] = useState<Intent | null>(null)
  const requests = useQuery({queryKey: ['evidence-intents', session.user.id, path], enabled: writer,
    queryFn: ({signal}) => api<{intents: {id: string; state: string}[]}>(path + '/intents', {signal}),
    retry: false, refetchInterval: 5000, refetchIntervalInBackground: false})
  const durable = !requests.isError ? requests.data?.intents[0] : undefined
  const unresolved = !!pending || !!durable || (writer && (requests.isPending || requests.isError))
  const uuid = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(value)

  async function nativeReceipt(id: string, active: () => boolean, retiring = false) {
    const receipt = await privateRequest(path + '/intents/' + id + (retiring ? '/retire' : '/retry'), {
      method: 'POST', body: '{}', headers: {'x-gitgood-csrf': session.csrf}}, async response => {
      let receipt: {id?: unknown; intent_id?: unknown; recorded?: unknown; artifact_unavailable_recorded?: unknown; retired?: unknown; error?: unknown}
      try {receipt = await response.json()}
      catch {throw new ApiError(response.status, 'forge_response_unavailable')}
      if (!response.ok) throw new ApiError(response.status, typeof receipt?.error === 'string' ? receipt.error : 'Request failed')
      if (!receipt || !uuid(receipt.id) || receipt.intent_id !== id ||
        [receipt.recorded === true, receipt.artifact_unavailable_recorded === true, retiring && receipt.retired === true].filter(Boolean).length !== 1)
        throw new ApiError(response.status, 'evidence_receipt_unavailable')
      return receipt
    })
    if (!active()) throw new ApiError(409, 'access_changed_refetch')
    if (!receipt.retired) await privateRequest(path + '/intents/' + id + '/acknowledge', {
      method: 'POST', body: '{}', headers: {'x-gitgood-csrf': session.csrf}}, async response => {
      let acknowledged: {id?: unknown; acknowledged?: unknown; error?: unknown}
      try {acknowledged = await response.json()} catch {throw new ApiError(response.status, 'forge_response_unavailable')}
      if (!response.ok || acknowledged?.id !== id || acknowledged.acknowledged !== true)
        throw new ApiError(response.status, 'evidence_receipt_unavailable')
      return acknowledged
    })
    return receipt
  }

  async function recover(id: string, retiring = false) {
    const store = accessStore(), ticket = store?.ticket()
    const active = () => mounted.current && !!store && !!ticket && store.valid(ticket)
    if (!active() || inFlight.current) return
    inFlight.current = true; setBusy(true); setMessage('')
    try {
      const receipt = await nativeReceipt(id, active, retiring)
      if (active()) {
        intent.current = null; setPending(null)
        setMessage(receipt.retired ? 'The original request was not applied and has been retired.' : 'Request recorded. Current evidence is shown below.')
        await requests.refetch().catch(() => undefined)
        await query.refetch().catch(() => undefined)
      }
    } catch {if (active()) setMessage('The request could not be confirmed. Retry the original request to confirm its outcome.')}
    finally {inFlight.current = false; if (active()) setBusy(false)}
  }

  async function mutate(destination: string, body: string) {
    const store = accessStore(), ticket = store?.ticket()
    const active = () => mounted.current && !!store && !!ticket && store.valid(ticket)
    if (!active() || inFlight.current || (!intent.current && unresolved)) return false
    if (intent.current && (intent.current.body !== body || intent.current.path !== destination)) {
      setMessage('Confirm the original evidence request before starting another result or withdrawal.')
      return false
    }
    const requested = intent.current ?? {path: destination, body, key: crypto.randomUUID()}
    intent.current = requested; setPending(requested); inFlight.current = true
    setBusy(true); setMessage('')
    try {
      if (!requested.id) requested.id = await privateRequest(path + '/intents', {method: 'POST',
        body: JSON.stringify(destination === path ? {kind: 'attach', body} :
          {kind: 'unavailable', evidence_id: destination.slice(path.length + 1, -'/unavailable'.length), body}),
        headers: {'x-gitgood-csrf': session.csrf, 'idempotency-key': requested.key}}, async response => {
        let receipt: {id?: unknown; state?: unknown; error?: unknown}
        try {receipt = await response.json()}
        catch {throw new ApiError(response.status, 'forge_response_unavailable')}
        if (!response.ok) throw new ApiError(response.status, typeof receipt?.error === 'string' ? receipt.error : 'Request failed')
        if (!receipt || !uuid(receipt.id) || !['pending', 'confirmed', 'acknowledged'].includes(String(receipt.state)))
          throw new ApiError(response.status, 'evidence_receipt_unavailable')
        return receipt.id
      })
      await nativeReceipt(requested.id, active)
      if (active()) {
        intent.current = null; setPending(null)
        setMessage('Request recorded. Current evidence is shown below.')
        // A later read failure cannot make the confirmed write uncertain again.
        await requests.refetch().catch(() => undefined)
        await query.refetch().catch(() => undefined)
      }
      return active()
    } catch (error) {
      if (active()) {
        if (!requested.id && error instanceof ApiError && error.status === 422 && error.message === 'invalid_evidence') {
          intent.current = null; setPending(null)
          setMessage('The request was refused as invalid evidence. Correct the fields before submitting a new request.')
        } else setMessage('The request could not be confirmed. Retry the original request to confirm its outcome.')
      }
      return false
    } finally {inFlight.current = false; if (active()) setBusy(false)}
  }

  async function attach(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    if (!view?.source.revision || !view.source_sha || !view.target_sha || inFlight.current || preparing.current || intent.current || unresolved) return
    const store = accessStore(), ticket = store?.ticket()
    const active = () => mounted.current && !!store && !!ticket && store.valid(ticket)
    const fields = new FormData(form), index = Number(fields.get('criterion'))
    const criterion = view.criteria.find(value => value.index === index), file = fields.get('artifact')
    if (!criterion || !(file instanceof File)) return
    preparing.current = true
    try {
      if (file.size < 1 || file.size > 65536) throw new Error('Use a UTF-8 text artifact between 1 byte and 64 KiB.')
      const bytes = await file.arrayBuffer()
      const content = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(bytes)
      if (content.includes('\0')) throw new Error('Use UTF-8 text without NUL bytes; binary artifacts are not supported.')
      const sha256 = await digest(bytes)
      if (!active()) return
      const environment = JSON.parse(String(fields.get('environment')))
      const body = JSON.stringify({connection_generation: generation, link_generation: link.generation,
        source_revision: view.source.revision, source_sha: view.source_sha, target_sha: view.target_sha,
        criterion_index: criterion.index, criterion_sha256: criterion.sha256, outcome: fields.get('outcome'),
        manifest: {commands: String(fields.get('commands')).split(/\r?\n/).map(value => value.trim()).filter(Boolean),
          environment, producer: fields.get('producer'), observed_at: fields.get('observed_at')},
        artifact: {name: file.name, content, sha256}})
      if (await mutate(path, body)) form.reset()
    } catch (error) {if (active()) setMessage(error instanceof Error ? error.message : 'Artifact could not be prepared.')}
    finally {preparing.current = false}
  }

  async function download(record: Record) {
    const store = accessStore(), ticket = store?.ticket()
    const active = () => mounted.current && !!store && !!ticket && store.valid(ticket)
    if (!active()) return
    try {
      const blob = await privateRequest(path + '/' + record.id + '/download?connection_generation=' + encodeURIComponent(generation), {}, async response => {
        if (!response.ok) {await response.body?.cancel(); throw new ApiError(response.status, 'Artifact unavailable for current access.')}
        if (response.headers.get('x-gitgood-sha256') !== record.artifact.sha256) {await response.body?.cancel(); throw new Error('Artifact identity changed.')}
        const bytes = await response.arrayBuffer()
        if (bytes.byteLength !== record.artifact.size || await digest(bytes) !== record.artifact.sha256) throw new Error('Artifact checksum did not match.')
        return new Blob([bytes], {type: 'application/octet-stream'})
      })
      if (!active()) return
      const url = URL.createObjectURL(blob), anchor = document.createElement('a')
      try {anchor.href = url; anchor.download = record.artifact.name; anchor.click()}
      finally {URL.revokeObjectURL(url)}
    } catch {if (active()) setMessage('Artifact could not be downloaded with current permissions and identity. Refresh its status.')}
  }

  const recovery = <>
    {writer && (pending || durable) && <div>
      <p>The original request keeps its exact artifact, observation time and revision binding. Confirm it before reassessing against a newer revision.</p>
      <button type="button" disabled={busy} onClick={() => {
        const id = pending?.id ?? durable?.id
        if (id) void recover(id)
        else if (pending) void mutate(pending.path, pending.body)
      }}>Retry original evidence request</button>
      {(pending?.id || durable?.id) && <button type="button" disabled={busy} onClick={() => void recover((pending?.id ?? durable?.id)!, true)}>Resolve or retire original request</button>}
    </div>}
    {writer && requests.isError && <p role="alert">Saved evidence requests could not be confirmed. <button type="button" onClick={() => void requests.refetch()}>Refresh saved requests</button></p>}
  </>
  if (recoveryOnly) return writer && (pending || durable || requests.isError || message) ?
    <section aria-label="Saved evidence requests" className="collaboration-panel">
      <h3>Saved evidence requests</h3>{message && <p role="status">{message}</p>}{recovery}
      <p>Only your saved request status is shown. Source-bound artifact and requirement details require current source access.</p>
    </section> : null

  return <section aria-label="Criterion evidence" className="collaboration-panel evidence-panel">
    <h3>Criterion evidence</h3>
    <p>Producer results are bound to this task revision and both Git commits. They do not change protected merge policy.</p>
    {message && <p role="status">{message}</p>}{recovery}
    {historyCursor && <button type="button" onClick={() => {setHistoryCursor(null); setHistoryStack([])}}>Show newest evidence</button>}
    {query.isError ? <p role="alert">Evidence could not be confirmed. <button onClick={() => void query.refetch()}>Refresh evidence</button></p> :
      query.isPending ? <p role="status">Loading evidence…</p> : !view ?
      <p>{query.data?.profile === 'unsupported_criteria' ? 'This source record has unsupported task criteria; evidence cannot be assessed.' : 'Source-bound evidence is hidden while your task access is unavailable. Native history is retained.'}</p> : <>
        <p>Task revision {view.source.revision} · observed {view.observed_at}</p>
        {!view.criteria.length && <p>This source record has no supported task acceptance criteria. Retained evidence history remains below.</p>}
        <ul>{view.criteria.map(criterion => <li key={criterion.index}><strong>{states[criterion.state] ?? criterion.state}</strong> — {criterion.text}</li>)}</ul>
        <details open={historyExpanded} onToggle={event => setHistoryExpanded(event.currentTarget.open)}><summary>Evidence history ({view.history?.total ?? view.records.length})</summary>
          <p>Current criterion states above always use the newest result across the whole history.</p>
          {(historyStack.length > 0 || view.history?.next_cursor) && <nav aria-label="Evidence history pages">
            <button type="button" disabled={historyStack.length === 0} onClick={() => {
              setHistoryCursor(historyStack.at(-1) ?? null); setHistoryStack(historyStack.slice(0, -1))
            }}>Newer evidence</button>
            <button type="button" disabled={!view.history?.next_cursor} onClick={() => {
              setHistoryStack([...historyStack, historyCursor]); setHistoryCursor(view.history?.next_cursor ?? null)
            }}>Older evidence</button>
          </nav>}
          {view.records.length === 0 ? <p>No attached results.</p> : view.records.map(record => <article key={record.id} className="review-event" aria-label="Evidence record">
            <h4>Criterion {record.criterion_index + 1} · {states[record.state] ?? record.state}</h4>
            <p>Original outcome: {record.outcome} · attached by native actor {record.actor_id} at {record.recorded_at}</p>
            <p>Producer: {record.manifest.producer} · observed {record.manifest.observed_at}</p>
            <p>Requirement revision {record.source_revision}</p>
            <p>Source {record.source_sha} · target {record.target_sha}</p>
            <pre>{record.manifest.commands.join('\n')}</pre><pre>{JSON.stringify(record.manifest.environment, null, 2)}</pre>
            <p>{record.artifact.name} · {record.artifact.size} bytes · SHA256 {record.artifact.sha256}</p>
            {record.artifact.available && <button type="button" onClick={() => void download(record)}>Download protected artifact</button>}
            <AvailabilityHistory record={record} endpoint={path} generation={generation} session={session}/>
            {writer && record.artifact.available && <form onSubmit={event => {
              event.preventDefault()
              void mutate(path + '/' + record.id + '/unavailable', JSON.stringify({reason: new FormData(event.currentTarget).get('reason')}))
            }}><label>Reason artifact is unavailable<input name="reason" required maxLength={1000}/></label>
              <button disabled={busy || unresolved}>Mark artifact unavailable</button></form>}
          </article>)}
        </details>
        {writer && view.criteria.length > 0 && <details><summary>Attach evidence or reassess a result</summary><form onSubmit={event => void attach(event)}><fieldset disabled={busy || unresolved}>
          <label>Criterion<select name="criterion" required>{view.criteria.map(criterion => <option key={criterion.index} value={criterion.index}>{criterion.index + 1}. {criterion.text}</option>)}</select></label>
          <label>Producer outcome<select name="outcome" defaultValue="inconclusive"><option value="passed">Passed</option><option value="failed">Failed</option><option value="inconclusive">Inconclusive</option></select></label>
          <label>Producer label<input name="producer" required maxLength={128}/></label>
          <label>Observation time in UTC<input name="observed_at" required maxLength={64} defaultValue={new Date().toISOString()}/></label>
          <label>Reproduction commands · one per line<textarea name="commands" required maxLength={16384}/></label>
          <label>Environment as a JSON object<textarea name="environment" required maxLength={10240} defaultValue={'{"runtime":"","fixture":""}'}/></label>
          <label>UTF-8 artifact · up to 64 KiB<input name="artifact" type="file" required accept="text/plain,application/json,.txt,.json,.log"/></label>
          <p>Include the runtime versions, actors, relevant configuration and reproducible observations in the artifact.</p>
          <button disabled={busy}>{busy ? 'Recording evidence…' : 'Attach immutable result'}</button>
        </fieldset></form></details>}
      </>}
  </section>
}

function AvailabilityHistory({record, endpoint, generation, session}: {
  record: Record; endpoint: string; generation: string; session: Session
}) {
  const [cursor, setCursor] = useState<string | null>(null)
  const [stack, setStack] = useState<(string | null)[]>([])
  const query = useQuery({queryKey: ['criterion-evidence-events', session.user.id, endpoint, generation, record.id, cursor],
    enabled: cursor !== null,
    queryFn: ({signal}) => api<{events: EvidenceEvent[]; total: number; next_cursor: string | null}>(
      endpoint + '/' + record.id + '/events?connection_generation=' + encodeURIComponent(generation) +
      '&cursor=' + encodeURIComponent(cursor ?? ''), {signal}), retry: false, refetchInterval: 5000, refetchIntervalInBackground: false})
  const current = cursor === null ? {events: record.events, total: record.events_total, next_cursor: record.events_next_cursor} :
    !query.isError ? query.data : undefined
  if (!record.events_total) return null
  return <section aria-label="Artifact availability history">
    <p>Availability events ({record.events_total})</p>
    {cursor && <button type="button" onClick={() => {setCursor(stack.at(-1) ?? null); setStack(stack.slice(0, -1))}}>Earlier availability events</button>}
    {query.isError && cursor ? <p role="alert">Availability history could not be confirmed. <button type="button" onClick={() => void query.refetch()}>Retry availability history</button></p> :
      !current ? <p role="status">Loading availability history…</p> : <>
        {current.events.map((event, index) => <p key={index}>{event.kind}: {event.reason} · actor {event.actor_id} · {event.recorded_at}</p>)}
        {current.next_cursor && <button type="button" onClick={() => {
          setStack([...stack, cursor]); setCursor(current.next_cursor)
        }}>Later availability events</button>}
      </>}
  </section>
}
