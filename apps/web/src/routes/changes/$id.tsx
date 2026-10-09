import {createFileRoute} from '@tanstack/react-router'
import {useEffect} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api, ApiError} from '../../lib/api'
import {useSession} from '../../lib/access-boundary'

export const Route = createFileRoute('/changes/$id')({component: ChangeLanding})
function ChangeLanding() {
  const {id} = Route.useParams(), session = useSession()
  const change = useQuery({queryKey: ['native-change', id], enabled: !!session.data, retry: false,
    queryFn: ({signal}) => api<{id: string; title: string; url: string}>('/changes/' + encodeURIComponent(id), {signal})})
  const target = !change.error && change.data &&
    /^\/repos\/[a-z][a-z0-9-]{1,39}\/[a-z][a-z0-9-]{1,63}\/pulls\/[0-9a-f-]{36}$/.test(change.data.url) ? change.data.url : null
  useEffect(() => {if (target) window.location.replace(target)}, [target])
  const valid = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)
  return <div className="shell"><header><a className="brand" href="/">gitgood<span className="dot">●</span></a></header>
    <main><h1>Linked change</h1>
      {!valid ? <p role="alert">This change address is unavailable.</p> : !session.data ?
        <p>Sign in to check your access to this private change. <a href={'/?change=' + encodeURIComponent(id)}>Sign in to Gitgood</a></p> :
        change.error ? <p role="alert">{change.error instanceof ApiError && change.error.status === 404 ?
          'This change is unavailable for your account.' : 'Change access could not be confirmed.'}
          <button onClick={() => void change.refetch()}>Retry change access</button></p> :
        target ? <p>Opening your permitted change. <a href={target}>Open change</a></p> : <p role="status">Checking change access…</p>}
      <p><a href="/">Your repositories</a></p>
    </main></div>
}
