import {useEffect, useRef, useState, type FormEvent} from 'react'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {Link} from '@tanstack/react-router'
import {api, type Session} from './api'
type Policy = {version: number; approvals: number; required_checks: {provider_id: number; name: string}[]}
type Provider = {id: number; name: string; credential_id: number}
export function PullRequests({base, team, name, session, branches}: {base: string; team: string; name: string; session?: Session; branches: {name: string}[]}) {
  const query = useQuery({queryKey: ['pulls',base],queryFn: () => api<{pull_requests: {id: string; title: string; state: string}[]}>(base + '/pulls')})
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  const request = useRef<{body: string; key: string} | null>(null)
  const writer = session?.teams.some(t => base.startsWith('/repos/' + encodeURIComponent(t.team) + '/') && t.role !== 'reader')
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))
    if (request.current?.body !== body) request.current = {body,key: crypto.randomUUID()}
    setBusy(true);setError('')
    try {
      const result = await api<{id: string}>(base + '/pulls',{method:'POST',headers:{'x-gitgood-csrf':session!.csrf,'idempotency-key':request.current.key},body})
      window.location.assign(base + '/pulls/' + result.id)
    } catch (e) {setError(e instanceof Error ? e.message : 'Creation failed')} finally {setBusy(false)}
  }
  return <section className="collaboration-panel"><h2>Pull requests</h2>
    {query.error ? <p role="alert">Pull requests unavailable. <button onClick={() => void query.refetch()}>Retry pull requests</button></p> : <ul className="history">{query.data?.pull_requests.map(pull => <li key={pull.id}><Link to="/repos/$team/$name/pulls/$id" params={{team, name, id: pull.id}} search={{sha: '', path: '', view: 'code'}} preload={false}>{pull.title}</Link><span>{pull.state}</span></li>)}</ul>}
    {writer && <details><summary>Open a pull request</summary><form onSubmit={create}><label>Source branch<select name="source" required>{branches.filter(b => b.name !== 'main').map(b => <option key={b.name}>{b.name}</option>)}</select></label><label>Title<input name="title" maxLength={200} required /></label><label>Description<textarea name="body" maxLength={16384} /></label>{error && <p role="alert">{error.replaceAll('_',' ')}</p>}<button disabled={busy || !branches.some(b => b.name !== 'main')}>{busy ? 'Opening…' : 'Open pull request'}</button><p>Target: main · fast-forward merge after current approvals and checks.</p></form></details>}
  </section>
}
export function PolicySettings({base,session}: {base: string; session?: Session}) {
  const client = useQueryClient()
  const query = useQuery({queryKey:['policy',base],queryFn:()=>api<{policy: Policy;providers: Provider[]}>(base+'/policy')})
  const [error,setError] = useState('')
  const [token,setToken] = useState<{token: string;credential_id: number} | null>(null)
  const [required,setRequired] = useState<Policy['required_checks']>([])
  useEffect(()=>{if(query.data)setRequired(query.data.policy.required_checks)},[query.data])
  const owner = session?.teams.some(t => base.startsWith('/repos/'+encodeURIComponent(t.team)+'/') && t.role === 'owner')
  async function provider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();setError('')
    try {setToken(await api(base+'/providers',{method:'POST',headers:{'x-gitgood-csrf':session!.csrf},body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))}));await client.invalidateQueries({queryKey:['policy',base]})}
    catch(e){setError(e instanceof Error?e.message:'Provider creation failed')}
  }
  async function policy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();setError('')
    const approvals = Number(new FormData(event.currentTarget).get('approvals'))
    try {await api(base+'/policy',{method:'PUT',headers:{'x-gitgood-csrf':session!.csrf},body:JSON.stringify({version:query.data!.policy.version,approvals,required_checks:required})});await client.invalidateQueries({queryKey:['policy',base]})}
    catch(e){setError(e instanceof Error?e.message:'Policy update failed')}
  }
  async function revoke(id:number) {
    try {await api('/credentials/'+id,{method:'DELETE',headers:{'x-gitgood-csrf':session!.csrf}});setToken(null);await query.refetch()}
    catch(e){setError(e instanceof Error?e.message:'Revocation failed')}
  }
  async function rotate(id:number) {
    try {setToken(await api(base+'/providers/'+id+'/rotate',{method:'POST',headers:{'x-gitgood-csrf':session!.csrf}}));await query.refetch()}
    catch(e){setError(e instanceof Error?e.message:'Rotation failed')}
  }
  return <section className="collaboration-panel"><details><summary>Branch policy and check providers</summary>
    {error && <p role="alert">{error.replaceAll('_',' ')}</p>}
    {query.data ? <><p>Main requires {query.data.policy.approvals} independent approval(s). Policy version {query.data.policy.version}.</p>
      {owner ? <><form onSubmit={policy}><label>Required approvals<input name="approvals" type="number" min={1} max={10} defaultValue={query.data.policy.approvals} key={query.data.policy.version} required /></label>
        {required.map((item,index)=><div className="requirement" key={index}><label>Provider<select value={item.provider_id} onChange={e=>setRequired(rows=>rows.map((row,i)=>i===index?{...row,provider_id:Number(e.target.value)}:row))}>{query.data!.providers.map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select></label><label>Required check<input value={item.name} required maxLength={64} onChange={e=>setRequired(rows=>rows.map((row,i)=>i===index?{...row,name:e.target.value}:row))} /></label><button type="button" className="subtle" onClick={()=>setRequired(rows=>rows.filter((_,i)=>i!==index))}>Remove</button></div>)}
        <button type="button" className="subtle" disabled={!query.data.providers.length || required.length>=16} onClick={()=>setRequired(rows=>[...rows,{provider_id:query.data!.providers[0].id,name:'build'}])}>Add required check</button><button>Save branch policy</button></form>
        <h3>Check providers</h3><ul>{query.data.providers.map(provider=><li key={provider.id}>{provider.name} <button className="subtle" onClick={()=>void rotate(provider.id)}>Rotate provider token</button> <button className="subtle" onClick={()=>void revoke(provider.credential_id)}>Revoke provider token</button></li>)}</ul>
        <form onSubmit={provider}><label>New provider name<input name="name" pattern="[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}" required maxLength={64}/></label><button>Create check provider</button></form>
        {token && <label>Provider token · shown once<input type="password" value={token.token} readOnly onFocus={e=>e.target.select()}/></label>}
        <p>Providers report to /api/checks/TEAM/REPOSITORY using their scoped bearer token. Configure your CI to send its commit, check name, attempt, sequence and result.</p></> :
      <ul>{query.data.policy.required_checks.map((item,index)=><li key={index}>Provider {item.provider_id}: {item.name}</li>)}</ul>}</> :
      query.error ? <p role="alert">Policy unavailable. <button onClick={()=>void query.refetch()}>Retry policy</button></p> : <p>Loading policy…</p>}
  </details></section>
}
