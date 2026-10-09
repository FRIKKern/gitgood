import {createFileRoute} from '@tanstack/react-router'
import {useQuery} from '@tanstack/react-query'
import {api} from '../../../../../lib/api'
import {useSession} from '../../../../../lib/access-boundary'
type Operation = {id: string; kind: string; state: string; inserted_at: string; updated_at: string; updates: {ref: string; old: string; new: string}[]; metadata: {target_ref?: string; target_sha?: string; source_sha?: string; policy?: {version: number}}; outcome: {error?: string; merge_sha?: string}}
export const Route = createFileRoute('/repos/$team/$name/operations/$id')({component: OperationPage})
function OperationPage() {
  const {team, name, id} = Route.useParams(), session = useSession()
  const base = '/repos/' + encodeURIComponent(team) + '/' + encodeURIComponent(name)
  const result = useQuery({queryKey: ['operation', base, id], enabled: !!session.data, retry: false,
    queryFn: ({signal}) => api<{operation: Operation}>(base + '/operations/' + encodeURIComponent(id), {signal}),
    refetchInterval: query => ['started', 'validated', 'uncertain'].includes(query.state.data?.operation.state ?? '') ? 5000 : false})
  const operation = result.data?.operation
  const updates = operation?.kind === 'merge' && operation.metadata.target_ref && operation.metadata.target_sha && operation.metadata.source_sha ?
    [{ref: operation.metadata.target_ref, old: operation.metadata.target_sha, new: operation.metadata.source_sha}] : operation?.updates ?? []
  return <div className="shell"><header><a className="brand" href="/">gitgood<span className="dot">●</span></a><a href={base}>Repository</a></header><main>
    <h1>Code operation</h1>
    {result.error ? <p role="alert">This operation is unavailable to your identity. <button onClick={() => void result.refetch()}>Retry operation</button></p> :
      operation ? <section className="panel"><h2>{operation.kind} · {operation.state}</h2><p>Operation <code>{operation.id}</code></p>
        <p>Recorded <time>{operation.inserted_at}</time> · updated <time>{operation.updated_at}</time></p>
        {operation.state === 'uncertain' && <p role="alert">Recovery is required before more writes. This operation is retained for reconciliation.</p>}
        {operation.outcome.error && <p>Outcome: {operation.outcome.error.replaceAll('_', ' ')}</p>}
        {operation.outcome.merge_sha && <p>Applied commit <code>{operation.outcome.merge_sha}</code></p>}
        {operation.metadata.policy && <p>Evaluated under policy revision {operation.metadata.policy.version}.</p>}
        <h3>Requested reference changes</h3>{updates.length === 0 && <p>No reference changes recorded.</p>}<ul className="operation-updates">{updates.map(update => <li key={update.ref}><strong>{update.ref}</strong><p>Before <code>{update.old}</code></p><p>After <code>{update.new}</code></p></li>)}</ul>
        <button onClick={() => void result.refetch()}>Refresh operation</button>
      </section> : <p role="status">Loading operation…</p>}
  </main></div>
}
