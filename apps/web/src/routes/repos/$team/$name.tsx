import {createFileRoute} from '@tanstack/react-router'
import {useEffect, useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api, type Repository} from '../../../lib/api'
export const Route = createFileRoute('/repos/$team/$name')({component: RepositoryPage})
function RepositoryPage() {
  const {team, name} = Route.useParams()
  const [ready, setReady] = useState(false)
  useEffect(() => setReady(true), [])
  const repository = useQuery({queryKey: ['repository', team, name], queryFn: () => api<Repository>('/repos/' + encodeURIComponent(team) + '/' + encodeURIComponent(name)), enabled: ready})
  return <div className="shell"><header><a className="brand" href="/">gitgood<span className="dot">●</span></a><a href="/">Your repositories</a></header><main>
    {repository.data ? <><p className="eyebrow">Private repository</p><h1>{team} / {name}</h1><section className="panel"><h2>{repository.data.status === 'ready' ? 'Repository initialized' : 'Creation pending'}</h2><p>Git transport and commit browsing are the next part of this foundation.</p><label>Clone URL<input value={repository.data.clone_url} readOnly onFocus={e => e.target.select()} /></label></section></> : repository.error ? <p role="alert">This repository is unavailable to your identity. <a href="/">Return to your repositories</a></p> : <p>Loading repository…</p>}
  </main></div>
}
