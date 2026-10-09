import {createFileRoute, Outlet, useRouterState} from '@tanstack/react-router'
import {useEffect, useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api, type Repository, type Session} from '../../../lib/api'
import {PullRequests, PolicySettings} from '../../../lib/collaboration'
import {RepositoryImport} from '../../../lib/repository-import'
import {Releases} from '../../../lib/releases'
import {useSession} from '../../../lib/access-boundary'
import {Discovery} from '../../../lib/discovery'
type Branch = {name: string; sha: string}
type Entry = {name: string; kind: string; sha: string; unsupported_encoding: boolean}
type Commit = {sha: string; author: string; date: string; subject: string}
type Snapshot = {sha: string; path: string; kind: string; entries?: Entry[]; history?: Commit[]; content?: string; size?: number; limit?: number}
export const Route = createFileRoute('/repos/$team/$name')({
  validateSearch: (search: Record<string, unknown>) => ({sha: typeof search.sha === 'string' ? search.sha : '', path: typeof search.path === 'string' ? search.path : '', view: search.view === 'diff' ? 'diff' as const : 'code' as const}),
  component: RepositoryLayout,
})
function RepositoryLayout() {
  const pathname = useRouterState({select: state => state.location.pathname})
  return pathname.includes('/pulls/') || pathname.includes('/operations/') ? <Outlet /> : <RepositoryPage />
}
function RepositoryPage() {
  const {team, name} = Route.useParams()
  const search = Route.useSearch()
  const navigate = Route.useNavigate()
  const [ready, setReady] = useState(false)
  const [credential, setCredential] = useState<{id: number; token: string} | null>(null)
  const [credentialError, setCredentialError] = useState('')
  useEffect(() => {setReady(true); setCredential(null)}, [team, name])
  const base = '/repos/' + encodeURIComponent(team) + '/' + encodeURIComponent(name)
  const session = useSession()
  const repository = useQuery({queryKey: ['repository', team, name], queryFn: () => api<Repository>(base), enabled: ready})
  const branches = useQuery({queryKey: ['branches', team, name], queryFn: () => api<{branches: Branch[]}>(base + '/branches'), enabled: !!repository.data})
  useEffect(() => {
    if (!search.sha && branches.data?.branches.length) {
      const initial = branches.data.branches.find(b => b.name === 'main') ?? branches.data.branches[0]
      void navigate({search: {...search, sha: initial.sha}, replace: true})
    }
  }, [branches.data, search, navigate])
  const browseReady = !!repository.data && !!branches.data && !branches.isFetching && !branches.error && !!search.sha
  const snapshot = useQuery({queryKey: ['snapshot', team, name, search.sha, search.path], queryFn: () => api<Snapshot>(base + '/snapshot?' + new URLSearchParams({sha: search.sha, path: search.path})), enabled: browseReady && search.view === 'code', retry: false})
  const diff = useQuery({queryKey: ['diff', team, name, search.sha], queryFn: () => api<{text: string; base: string}>(base + '/diff?sha=' + search.sha), enabled: browseReady && search.view === 'diff', retry: false})
  const link = (sha: string, path = '', view = 'code') => repository.data!.url + '?' + new URLSearchParams({sha, path, view})
  const selected = branches.data?.branches.find(b => b.sha === search.sha)
  async function issue() {
    setCredentialError('')
    try {setCredential(await api(base + '/credentials', {method: 'POST', headers: {'x-gitgood-csrf': session.data!.csrf}}))}
    catch (e) {setCredentialError(e instanceof Error ? e.message : 'Credential unavailable')}
  }
  async function revoke() {
    try {await api('/credentials/' + credential!.id, {method: 'DELETE', headers: {'x-gitgood-csrf': session.data!.csrf}}); setCredential(null)}
    catch (e) {setCredentialError(e instanceof Error ? e.message : 'Revocation failed')}
  }
  return <div className="shell"><header><a className="brand" href="/">gitgood<span className="dot">●</span></a><a href="/">Your repositories</a></header><main>
    {repository.data && !repository.error ? <><p className="eyebrow">Private repository</p><h1>{team} / {name}</h1>
      <section className="repository-tools"><label>Clone URL<input value={repository.data.clone_url} readOnly onFocus={e => e.target.select()} /></label>
        {session.data && <div>{credential ? <><label>Git token · shown once<input aria-label="Git token" type="password" value={credential.token} readOnly onFocus={e => e.target.select()} /></label><p>Use your username and this token in Git's credential prompt. It expires after 30 days.</p><button onClick={() => void revoke()}>Revoke this token</button></> : <button onClick={() => void issue()}>Create Git token</button>}</div>}
        {credentialError && <p role="alert">{credentialError}</p>}
      </section>
      {branches.error ? <p role="alert">Branches unavailable. <button onClick={() => void branches.refetch()}>Retry branches</button></p> : branches.data?.branches.length === 0 ? <section className="panel"><h2>Repository initialized</h2><p>Clone this repository, commit your files and push main to get started.</p></section> : <section className="code-panel">
        <div className="code-toolbar"><label>Branch<select aria-label="Branch" disabled={branches.isFetching} value={selected?.name ?? ''} onChange={e => {const branch = branches.data!.branches.find(b => b.name === e.target.value)!; void navigate({search: {sha: branch.sha, path: '', view: 'code'}})}}>
          {!selected && <option value="">Viewed commit</option>}{branches.data?.branches.map(b => <option key={b.name}>{b.name}</option>)}</select></label>
          <span title={search.sha}>Commit {search.sha.slice(0, 12)}</span><a href={link(search.sha)}>Files</a><a href={link(search.sha, '', 'diff')}>Commit diff</a><button className="subtle" onClick={() => void branches.refetch()}>Refresh branches</button></div>
        <p className="context-note">This view stays on its commit when a branch advances. Choose a branch to view its current tip.</p>
        {search.view === 'diff' ? diff.error ? <p role="alert">{diff.error.message.replaceAll('_',' ')} <button onClick={() => void diff.refetch()}>Retry diff</button></p> : diff.data ? <><p>Compared with {diff.data.base.slice(0,12)}</p><pre className="source">{diff.data.text || 'No changes'}</pre></> : <p>Loading diff…</p> :
        snapshot.error ? <p role="alert">{snapshot.error.message.replaceAll('_',' ')} <button onClick={() => void snapshot.refetch()}>Retry this view</button></p> : snapshot.data ? <>
          <nav aria-label="File path"><a href={link(search.sha)}>Root</a>{search.path.split('/').filter(Boolean).map((part, index, parts) => <span key={index}> / <a href={link(search.sha, parts.slice(0,index+1).join('/'))}>{part}</a></span>)}</nav>
          {snapshot.data.kind === 'tree' ? <><ul className="file-list">{snapshot.data.entries?.map(entry => <li key={entry.name}><span>{entry.kind === 'tree' ? 'Directory' : entry.kind === 'commit' ? 'Submodule' : 'File'}</span>{entry.unsupported_encoding ? <span>{entry.name} · unsupported filename encoding</span> : <a href={link(search.sha, [search.path,entry.name].filter(Boolean).join('/'))}>{entry.name}</a>}</li>)}</ul>
            <h2>Commit history</h2><ol className="history">{snapshot.data.history?.map(commit => <li key={commit.sha}><a href={link(commit.sha)}>{commit.subject}</a><span>{commit.author} · {commit.date} · {commit.sha.slice(0,12)}</span></li>)}</ol><p>Showing at most 50 commits.</p></> :
          snapshot.data.kind === 'text' ? <pre className="source">{snapshot.data.content}</pre> : <p>{snapshot.data.kind === 'binary' ? 'Binary file. A text preview is unavailable.' : snapshot.data.kind === 'large_file' ? 'File exceeds the 256 KiB preview limit.' : 'Submodule reference. Its content is in a separate repository.'} {snapshot.data.size !== undefined && `${snapshot.data.size} bytes.`}</p>}
        </> : <p>Loading commit…</p>}
      </section>}
      <RepositoryImport base={base} repository={repository.data} session={session.data} empty={branches.data?.branches.length === 0}/>
      <Releases base={base} session={session.data}/>
      <PullRequests base={base} session={session.data} branches={branches.data?.branches ?? []}/><PolicySettings base={base} session={session.data}/>
      {session.data && <Discovery base={base}/>}
    </> : repository.error ? <p role="alert">This repository is unavailable to your identity. <button onClick={() => void repository.refetch()}>Retry repository</button> <a href="/">Return to your repositories</a></p> : <p>Loading repository…</p>}
  </main></div>
}
