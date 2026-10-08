import {createFileRoute} from '@tanstack/react-router'
import {useEffect, useRef, useState, type FormEvent} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api, ApiError, type Session} from '../../../../../lib/api'
type Event = {id: number; actor: string; kind: string; body: string; source_sha: string; target_sha: string; path: string | null; line: number | null; side: string | null; excerpt: string | null; outdated: boolean}
type Pull = {id: number; title: string; body: string; state: string; author_id: number; source_ref: string; target_ref: string; source_sha: string; target_sha: string; policy: {version: number; approvals: number; required_checks: {provider_id: number; name: string}[]}; events: Event[]; checks: {id: number; provider: string; name: string; sha: string; attempt: number; sequence: number; status: string}[]}
type Operation = {id: string; state: string; outcome: {merge_sha?: string}}
export const Route = createFileRoute('/repos/$team/$name/pulls/$id')({component: PullPage})
function PullPage() {
  const {team,name,id} = Route.useParams()
  const base = '/repos/'+encodeURIComponent(team)+'/'+encodeURIComponent(name)
  const [ready,setReady] = useState(false)
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  const [operation,setOperation] = useState<Operation | null>(null)
  const mergeRequest = useRef<{body:string;key:string} | null>(null)
  const reviewRequest = useRef<{body:string;key:string} | null>(null)
  useEffect(()=>setReady(true),[])
  const session = useQuery({queryKey:['session'],queryFn:()=>api<Session>('/session'),enabled:ready})
  const pull = useQuery({queryKey:['pull',base,id],queryFn:()=>api<Pull>(base+'/pulls/'+id),enabled:ready,retry:false})
  const diff = useQuery({queryKey:['pull-diff',base,id,pull.data?.source_sha,pull.data?.target_sha],queryFn:()=>api<{text:string}>(base+'/pulls/'+id+'/diff'),enabled:!!pull.data,retry:false})
  const writer = session.data?.teams.some(t=>t.team===team && t.role!=='reader')
  async function review(kind:string) {
    setBusy(true);setError('')
    const body = JSON.stringify({kind,source_sha:pull.data!.source_sha,target_sha:pull.data!.target_sha})
    if(reviewRequest.current?.body!==body)reviewRequest.current={body,key:crypto.randomUUID()}
    try {await api(base+'/pulls/'+id+'/reviews',{method:'POST',headers:{'x-gitgood-csrf':session.data!.csrf,'idempotency-key':reviewRequest.current.key},body});reviewRequest.current=null;await pull.refetch()}
    catch(e){setError(e instanceof Error?e.message:'Review failed')}finally{setBusy(false)}
  }
  async function merge() {
    setBusy(true);setError('')
    const body = JSON.stringify({source_sha:pull.data!.source_sha,target_sha:pull.data!.target_sha,policy_version:pull.data!.policy.version})
    if(mergeRequest.current?.body!==body)mergeRequest.current={body,key:crypto.randomUUID()}
    try {
      const result = await api<{operation:Operation}>(base+'/pulls/'+id+'/merge',{method:'POST',headers:{'x-gitgood-csrf':session.data!.csrf,'idempotency-key':mergeRequest.current.key},body})
      setOperation(result.operation);await pull.refetch()
    }catch(e){if(e instanceof ApiError && e.details.operation)setOperation(e.details.operation as Operation);setError(e instanceof Error?e.message:'Merge response unavailable. Refresh durable operations before retrying.')}finally{setBusy(false)}
  }
  async function operations() {
    try {const result=await api<{operations:Operation[]}>(base+'/operations?pull_request_id='+id);setOperation(result.operations[0]??null);await pull.refetch()}
    catch(e){setError(e instanceof Error?e.message:'Operations unavailable')}
  }
  return <div className="shell"><header><a className="brand" href="/">gitgood<span className="dot">●</span></a><a href={base}>Repository</a></header><main>
    {pull.data ? <><p className="eyebrow">Pull request #{id} · {pull.data.state}</p><h1>{pull.data.title}</h1><p className="intro">{pull.data.source_ref.replace('refs/heads/','')} → main · fast-forward</p><p>{pull.data.body}</p>
      <p>Source {pull.data.source_sha.slice(0,12)} · target {pull.data.target_sha.slice(0,12)} · policy {pull.data.policy.version}</p>
      <button className="subtle" onClick={()=>void pull.refetch()}>Refresh pull request</button>
      {error && <p role="alert" className="error">{error.replaceAll('_',' ')}</p>}
      <section className="code-panel"><h2>Changes</h2>{diff.data ? <pre className="source">{diff.data.text || 'No changes'}</pre> : diff.error ? <p role="alert">{diff.error.message.replaceAll('_',' ')} <button onClick={()=>void diff.refetch()}>Retry changes</button></p> : <p>Loading changes…</p>}</section>
      <section className="collaboration-panel"><h2>Conversation and reviews</h2>
        {pull.data.events.map(event=><article className="review-event" key={event.id}><strong>{event.actor} · {event.kind.replaceAll('_',' ')}</strong>{event.outdated && <span className="badge">Outdated revision</span>}
          <p>{event.body}</p>{event.path && <><small>{event.path} · {event.side} line {event.line} · commit {event.source_sha.slice(0,12)}</small><pre>{event.excerpt}</pre></>}
        </article>)}
        {writer && pull.data.state==='open' && <><CommentDraft key={session.data!.user.id+':'+pull.data.source_sha+':'+pull.data.target_sha} actor={session.data!.user.id} csrf={session.data!.csrf} base={base} pull={pull.data} onSaved={()=>pull.refetch()}/>
          <div className="merge-controls"><button disabled={busy || session.data!.user.id===pull.data.author_id} onClick={()=>void review('approve')}>Approve current revision</button><button disabled={busy} onClick={()=>void review('changes_requested')}>Request changes</button></div></>}
      </section>
      <section className="collaboration-panel"><h2>Checks and merge</h2><p>Requires {pull.data.policy.approvals} independent approval(s) for this exact source and target.</p>
        <ul>{pull.data.policy.required_checks.map((item,index)=><li key={index}>Required: provider {item.provider_id} / {item.name}</li>)}</ul>
        <ul>{pull.data.checks.map(check=><li key={check.id}>{check.provider} / {check.name} · attempt {check.attempt} · {check.status}</li>)}</ul>
        <div className="merge-controls">{writer && pull.data.state==='open' && <button disabled={busy} onClick={()=>void merge()}>{busy?'Evaluating…':'Merge under current policy'}</button>}<button className="subtle" onClick={()=>void operations()}>Refresh durable operations</button></div>
        {operation?.state === 'failed' && <button className="subtle" onClick={()=>{mergeRequest.current=null;setOperation(null);setError('');void pull.refetch()}}>Start a new merge attempt</button>}
        {operation && <p role="status">Operation {operation.id}: {operation.state}{operation.outcome.merge_sha && ' · '+operation.outcome.merge_sha.slice(0,12)}</p>}
        {pull.data.state==='merged' && <p role="status">Pull request merged.</p>}
      </section>
    </> : pull.error ? <p role="alert">Pull request unavailable. <button onClick={()=>void pull.refetch()}>Retry pull request</button></p> : <p>Loading pull request…</p>}
  </main></div>
}
type Draft = {path:string;line:string;side:string;body:string;key:string}
function CommentDraft({actor,csrf,base,pull,onSaved}:{actor:number;csrf:string;base:string;pull:Pull;onSaved:()=>Promise<unknown>}) {
  const storage = 'gitgood-comment:'+actor+':'+base+':'+pull.id+':'+pull.source_sha+':'+pull.target_sha
  const empty = ():Draft=>({path:'',line:'1',side:'new',body:'',key:crypto.randomUUID()})
  const [draft,setDraft] = useState<Draft>(()=>{try {const value=JSON.parse(sessionStorage.getItem(storage)??'null');return value && typeof value.body==='string' && typeof value.key==='string'?value:empty()}catch{return empty()}})
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  useEffect(()=>{try{sessionStorage.setItem(storage,JSON.stringify(draft))}catch{setError('This browser cannot save a local draft. Keep this tab open.')}},[draft,storage])
  const change = (field:keyof Draft,value:string)=>setDraft(previous=>({...previous,[field]:value,key:crypto.randomUUID()}))
  async function submit(event:FormEvent) {
    event.preventDefault();setBusy(true);setError('')
    try {
      await api(base+'/pulls/'+pull.id+'/reviews',{method:'POST',headers:{'x-gitgood-csrf':csrf,'idempotency-key':draft.key},
        body:JSON.stringify({kind:'comment',source_sha:pull.source_sha,target_sha:pull.target_sha,path:draft.path,line:Number(draft.line),side:draft.side,body:draft.body})})
      setDraft(empty());await onSaved()
    }catch(e){setError(e instanceof Error?e.message:'Comment failed. Your draft is preserved.')}finally{setBusy(false)}
  }
  return <form onSubmit={submit}><h3>Comment on an exact diff line</h3><label>File path<input value={draft.path} required onChange={e=>change('path',e.target.value)}/></label><div className="requirement"><label>Side<select value={draft.side} onChange={e=>change('side',e.target.value)}><option value="new">New file</option><option value="old">Old file</option></select></label><label>Line<input type="number" min={1} max={1000000} value={draft.line} required onChange={e=>change('line',e.target.value)}/></label></div><label>Comment<textarea value={draft.body} required maxLength={16384} onChange={e=>change('body',e.target.value)}/></label>{error && <p role="alert">{error.replaceAll('_',' ')} Your draft is preserved.</p>}<button disabled={busy}>{busy?'Submitting…':'Submit line comment'}</button><p>Drafts stay in this browser session, bound to your identity and these exact revisions.</p></form>
}
