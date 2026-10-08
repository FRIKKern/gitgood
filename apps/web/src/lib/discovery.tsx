import {useState, type FormEvent} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api, ApiError} from './api'
type Record = {id: string; kind: string; team: string; name: string; title: string; snippet: string; state: string; actor: string; occurred_at: string; url: string}
type Snapshot = {records: Record[]; next_cursor: string | null; has_more: boolean; recorded_at: string; source: 'native'; snapshot: string}
export function Discovery({base}: {base?: string}) {
  const [input, setInput] = useState(''), [query, setQuery] = useState(''), [cursor, setCursor] = useState('')
  const mode = query ? 'search' : 'activity'
  const endpoint = mode === 'activity' && base ? base + '/activity' : '/' + mode
  const params = new URLSearchParams()
  if (query) params.set('q', query)
  if (cursor) params.set('cursor', cursor)
  if (base && mode === 'search') {
    params.set('team', decodeURIComponent(base.split('/')[2]))
    params.set('name', decodeURIComponent(base.split('/')[3]))
  }
  const result = useQuery({queryKey: ['discovery', base ?? 'all', mode, query, cursor], retry: false,
    queryFn: ({signal}) => api<Snapshot>(endpoint + (params.size ? '?' + params : ''), {signal}),
    refetchInterval: !cursor && mode === 'activity' ? 5000 : false})
  function search(event: FormEvent) {event.preventDefault(); setCursor(''); setQuery(input.trim())}
  function restart() {setCursor(''); void result.refetch()}
  const reset = result.error instanceof ApiError && ['discovery_reset_required', 'authorization_changed'].includes(result.error.message)
  return <section className="panel discovery-panel" aria-label={base ? 'Repository activity and search' : 'Search and activity'}>
    <h2>{base ? 'Repository activity' : 'Find work and follow activity'}</h2>
    <form onSubmit={search} className="discovery-search"><label>Search permitted records<input aria-label="Search permitted records" value={input} maxLength={256} onChange={event => setInput(event.target.value)} placeholder="Repository, pull request or release"/></label>
      <button>Search</button>{query && <button type="button" className="subtle" onClick={() => {setInput(''); setQuery(''); setCursor('')}}>Show recent activity</button>}</form>
    <p>Native records you can access. Recent activity refreshes every five seconds while this tab is visible.</p>
    <button className="subtle" onClick={restart}>{cursor ? 'Return to recent records' : 'Refresh records'}</button>
    {result.error ? <p role="alert">{reset ? 'Access or cursor changed. Restart this view.' : 'Records unavailable. The source could not be read.'} <button onClick={restart}>Retry records</button></p> :
      result.data ? <>
        <p className="context-note">{query ? 'Search results' : cursor ? 'Older activity' : 'Recent activity'} · observed <time dateTime={result.data.recorded_at}>{new Date(result.data.recorded_at).toLocaleString()}</time></p>
        {result.data.records.length === 0 ? <p>{query ? 'No matching permitted records.' : 'No permitted activity recorded.'}</p> :
          <ol className="discovery-records">{result.data.records.map(record => <li key={record.id}>
            <p><span className="badge">{record.kind.replaceAll('_', ' ')}</span> <a href={record.url}>{record.title}</a></p>
            {record.snippet && <p className="discovery-snippet">{record.snippet}</p>}
            <small>{record.team} / {record.name} · {record.actor} · {record.state.replaceAll('_', ' ')} · <time dateTime={record.occurred_at}>{new Date(record.occurred_at).toLocaleString()}</time></small>
          </li>)}</ol>}
        {result.data.has_more && <button disabled={result.isFetching} onClick={() => setCursor(result.data!.next_cursor!)}>Older records</button>}
        <p className="context-note">Up to 50 records per page. Refresh replaces the recent snapshot; older pages are a live view and may move when records change.</p>
      </> : <p role="status">Loading permitted records…</p>}
  </section>
}
