import {createFileRoute} from '@tanstack/react-router'
import {useEffect, useRef, useState, type FormEvent} from 'react'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {api, ApiError, type Repository, type Session} from '../lib/api'
import {SSHAccess} from '../lib/ssh-access'
import {useSession} from '../lib/access-boundary'
import {Discovery} from '../lib/discovery'
import {TeamMembers} from '../lib/team-members'
import {BarkparkAccount} from '../lib/barkpark-account'
export const Route = createFileRoute('/')({component: Home, validateSearch: (search: Record<string, unknown>) => ({
  change: typeof search.change === 'string' && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(search.change) ? search.change : undefined,
})})
function Home() {
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const queryClient = useQueryClient()
  const creation = useRef<{key: string; body: string} | null>(null)
  useEffect(() => setReady(true), [])
  const session = useSession()
  const {change} = Route.useSearch()
  useEffect(() => {if (session.data && change) window.location.replace('/changes/' + change)}, [session.data, change])
  const repos = useQuery({queryKey: ['repos'], queryFn: () => api<{repositories: Repository[]}>('/repos'), enabled: !!session.data})
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const form = new FormData(event.currentTarget)
    try {
      await api<Session>('/session', {method: 'POST', body: JSON.stringify(Object.fromEntries(form))})
    } catch (e) {setError(e instanceof Error ? e.message : 'Could not sign in')} finally {setBusy(false)}
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const form = event.currentTarget
    const body = JSON.stringify(Object.fromEntries(new FormData(form)))
    if (creation.current?.body !== body) creation.current = {key: crypto.randomUUID(), body}
    try {
      await api<Repository>('/repos', {method: 'POST', headers: {'x-gitgood-csrf': session.data!.csrf, 'idempotency-key': creation.current.key}, body})
      creation.current = null; form.reset(); await queryClient.invalidateQueries({queryKey: ['repos']})
    } catch (e) {setError(e instanceof Error ? e.message : 'Could not create repository')} finally {setBusy(false)}
  }
  async function logout() {
    try {await api('/session', {method: 'DELETE', headers: {'x-gitgood-csrf': session.data!.csrf}})}
    catch (e) {setError(e instanceof Error ? e.message : 'Could not sign out')}
  }
  const signedOut = !session.data && !session.error && !session.isPending
  return <div className="shell">
    <header><a className="brand" href="/">gitgood<span className="dot">●</span></a><div>{session.data ? <><span>{session.data.user.username}</span><button className="subtle" onClick={logout}>Sign out</button></> : <span>Private team forge</span>}</div></header>
    <main><p className="eyebrow">A good place for your code</p><h1>{session.data ? 'Your repositories' : 'Build something good.'}</h1>
      <p className="intro">{session.data ? 'Private by default. Owned by your team.' : 'Code, collaboration, and a clear path from change to delivery.'}</p>
      {error && <p role="alert" className="error">{error.replaceAll('_', ' ')}</p>}
      {!ready || session.isPending ? <p>Connecting to Gitgood…</p> : session.data ? <>
        <section className="grid">{!repos.error && repos.data?.repositories.map(repo => <article key={repo.id}><span className="badge">Private</span><h2><a href={repo.url}>{repo.team} / {repo.name}</a></h2><p>{repo.status === 'ready' ? 'Ready for your first commit.' : 'Creation pending. Retry with the original request.'}</p><label>Clone URL<input readOnly value={repo.clone_url} onFocus={e => e.target.select()} /></label>{repo.ssh_clone_url && <label>SSH clone URL<input readOnly value={repo.ssh_clone_url} onFocus={e => e.target.select()} /></label>}</article>)}</section>
        {repos.error && <p role="alert">Could not load repositories. <button onClick={() => void repos.refetch()}>Retry</button></p>}
        <section className="panel"><h2>Create a repository</h2><form onSubmit={create}><label>Team<select name="team">{session.data.teams.filter(t => t.role !== 'reader').map(t => <option key={t.team}>{t.team}</option>)}</select></label><label>Repository name<input name="name" required pattern="[a-z][a-z0-9-]{1,63}" placeholder="my-project" /></label><button disabled={busy || !session.data.teams.some(t => t.role !== 'reader')}>{busy ? 'Creating…' : 'Create private repository'}</button></form></section>
        <Discovery />
        {session.data.teams.filter(team => team.role === 'owner').map(team => <TeamMembers key={team.team} team={team.team} session={session.data!}/>)}
        <SSHAccess key={'ssh-access:' + session.data.user.id} session={session.data} />
        <BarkparkAccount key={'barkpark-account:' + session.data.user.id} session={session.data} />
      </> : signedOut ? <section className="panel login"><h2>Sign in to your installation</h2><form onSubmit={login}><label>Username<input name="username" autoComplete="username" required /></label><label>Password<input name="password" type="password" autoComplete="current-password" required /></label><button disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></form></section> : <p role="alert">The forge is unavailable. <button onClick={() => void session.refetch()}>Try again</button></p>}
    </main><footer>Gitgood · Native forge foundation</footer>
  </div>
}
