import {useEffect, useState} from 'react'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {api, type Repository, type Session} from './api'

type ImportOperation = {
  id: string; actor_id: number; credential_id: number; kind: string; state: string
  updates: {ref: string; new: string}[]
  metadata: {phase: string; source_name: string; source_sha256: string; source_bytes: number; warnings: string[]}
  outcome: {error?: string}; inserted_at: string
}

export function RepositoryImport({base, repository, session, empty}: {
  base: string; repository: Repository; session?: Session; empty: boolean
}) {
  const client = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const operations = useQuery({
    queryKey: ['import-operations', base, session?.user.id],
    queryFn: async () => (await api<{operations: ImportOperation[]}>(base + '/operations?kind=import')).operations,
    enabled: !!session,
    refetchInterval: query => query.state.data?.some(o => ['started', 'validated', 'uncertain'].includes(o.state)) ? 2000 : false,
  })
  const pending = operations.data?.find(o => ['started', 'validated', 'uncertain'].includes(o.state))
  const role = session?.teams.find(t => t.team === repository.team)?.role
  const allowed = repository.owner_id === session?.user.id && ['owner', 'writer'].includes(role ?? '')
  useEffect(() => {
    if (operations.data?.some(o => o.state === 'applied')) {
      void client.invalidateQueries({queryKey: ['branches', repository.team, repository.name]})
    }
  }, [operations.data, client, repository.team, repository.name])

  async function submit() {
    if (!file || !session) return
    setBusy(true); setError('')
    try {
      if (file.size < 1 || file.size > 33_554_432) throw new Error('Choose a bundle up to 32 MiB.')
      const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
      const sha = [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('')
      let operation = pending
      if (operation && (operation.metadata.source_sha256 !== sha ||
        operation.metadata.source_bytes !== file.size || operation.metadata.source_name !== file.name))
        throw new Error('This repository has a pending import for a different source. Cancel the waiting import before choosing another source.')
      if (!operation) {
        const result = await api<{operation: ImportOperation}>(base + '/imports', {
          method: 'POST', headers: {'x-gitgood-csrf': session.csrf, 'idempotency-key': key},
          body: JSON.stringify({source_name: file.name, source_sha256: sha, source_bytes: file.size}),
        })
        operation = result.operation
      }
      if (operation.state === 'started' && operation.metadata.phase === 'waiting_source') {
        await api(base + '/imports/' + operation.id + '/source', {
          method: 'PUT', headers: {'content-type': 'application/octet-stream', 'x-gitgood-csrf': session.csrf},
          body: file,
        })
      }
      setFile(null)
    } catch (e) {setError(e instanceof Error ? e.message.replaceAll('_', ' ') : 'Import unavailable. Retry to query the original operation.')}
    finally {setBusy(false); await operations.refetch()}
  }

  async function cancel() {
    if (!pending || !session) return
    setBusy(true); setError('')
    try {
      await api(base + '/imports/' + pending.id, {method: 'DELETE', headers: {'x-gitgood-csrf': session.csrf}})
      setKey(crypto.randomUUID()); setFile(null)
    } catch (e) {setError(e instanceof Error ? e.message.replaceAll('_', ' ') : 'Cancellation unavailable')}
    finally {setBusy(false); await operations.refetch()}
  }

  if (!empty && !operations.data?.length && !operations.error) return null
  return <section className="panel import-panel" aria-label="Repository import">
    <h2>Repository import</h2>
    {empty && <><p>Import a full SHA-1 Git bundle into this empty repository. It must include main, with up to 64 branches and tags and a 32 MiB file limit.</p>
      <p>Prepare it from a source you can read: <code>git bundle create source.bundle --branches --tags</code></p>
      <p>Only Git history is transferred. LFS objects, submodule repositories, issues, reviews, CI, credentials and forge settings are not imported. LFS pointers and .gitmodules remain source files.</p>
      {allowed ? <><label>Git bundle file<input aria-label="Git bundle file" type="file" accept=".bundle,application/octet-stream" disabled={busy || (!!pending && pending.metadata.phase !== 'waiting_source')} onChange={e => {
        setFile(e.target.files?.[0] ?? null); setKey(crypto.randomUUID()); setError('')
      }}/></label>
        <button disabled={!file || busy} onClick={() => void submit()}>{busy ? 'Checking import...' : 'Import bundle'}</button>
      </> : <p>The repository creator with write access can import a bundle.</p>}
    </>}
    {allowed && pending?.state === 'started' && pending.metadata.phase === 'waiting_source' && <button disabled={busy} onClick={() => void cancel()}>Cancel waiting import</button>}
    {error && <p role="alert">{error} <button disabled={busy || !file} onClick={() => void submit()}>Retry import</button></p>}
    {operations.error && <p role="alert">Import activity unavailable. <button onClick={() => void operations.refetch()}>Retry import activity</button></p>}
    {operations.data?.slice(0, 10).map(operation => <article className="import-operation" key={operation.id}>
      <h3>{operation.metadata.source_name}</h3>
      <p role="status">Import {operation.state === 'started' ? operation.metadata.phase.replaceAll('_', ' ') : operation.state}</p>
      <p>{operation.state === 'applied' ? operation.updates.length + ' branches and tags imported.' :
        operation.state === 'uncertain' ? 'Recovery is required before more repository writes.' :
        operation.state === 'failed' ? 'No import was published. ' + (operation.outcome.error ?? 'Query the outcome before retrying.').replaceAll('_', ' ') :
        operation.metadata.phase === 'waiting_source' ? 'Choose the same source file to resume this operation.' : 'The server will finish this operation even if this page closes.'}</p>
      <details><summary>Import record</summary><p>Operation {operation.id}</p><p>Source SHA-256 {operation.metadata.source_sha256}</p><p>{operation.metadata.source_bytes} bytes</p>
        {operation.updates.map(update => <p key={update.ref}>{update.ref} · {update.new}</p>)}
      </details>
    </article>)}
    {!!operations.data?.length && <button className="subtle" onClick={() => void operations.refetch()}>Refresh import activity</button>}
  </section>
}
