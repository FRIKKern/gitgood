import {useRef, useState, type FormEvent} from 'react'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {api, type Session} from './api'
type Key = {id: number; credential_id: number; label: string; fingerprint: string; expires_at: string; revoked: boolean}
type Transport = {enabled: false} | {enabled: true; host: string; port: number; public_key: string; fingerprint: string}
export function SSHAccess({session}: {session: Session}) {
  const client = useQueryClient()
  const queryKey = ['ssh-keys', session.user.id]
  const keys = useQuery({queryKey, queryFn: () => api<{keys: Key[]; transport: Transport}>('/ssh-keys')})
  const registration = useRef<{body: string; key: string} | null>(null)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const form=event.currentTarget,body=JSON.stringify(Object.fromEntries(new FormData(form)))
    if (registration.current?.body!==body) registration.current={body,key:crypto.randomUUID()}
    try {
      await api<Key>('/ssh-keys',{method:'POST',headers:{'x-gitgood-csrf':session.csrf,'idempotency-key':registration.current.key},body})
      registration.current=null; form.reset(); await client.invalidateQueries({queryKey})
    } catch(e) {setError(e instanceof Error?e.message:'Could not add SSH key')} finally {setBusy(false)}
  }
  async function revoke(key: Key) {
    setBusy(true);setError('')
    try {
      await api('/credentials/'+key.credential_id,{method:'DELETE',headers:{'x-gitgood-csrf':session.csrf}})
      await client.invalidateQueries({queryKey})
    } catch(e) {setError(e instanceof Error?e.message:'Could not revoke SSH key')} finally {setBusy(false)}
  }
  return <section className="panel ssh-panel"><h2>SSH access</h2>
    <p>Add an Ed25519 public key for your account. Repository permissions still apply. Keys expire after one year.</p>
    {keys.data?.transport.enabled ? <p>Verify the host fingerprint before connecting: <code>{keys.data.transport.fingerprint}</code></p> : keys.data && <p>SSH is unavailable on this installation. An operator must configure its host key and endpoint.</p>}
    {keys.error && <p role="alert">Could not load SSH keys. <button onClick={()=>void keys.refetch()}>Retry SSH keys</button></p>}
    {error && <p role="alert" className="error">{error.replaceAll('_',' ')}</p>}
    <form onSubmit={register}><label>SSH key label<input name="label" required maxLength={80} placeholder="My workstation" /></label>
      <label>SSH public key<textarea name="public_key" required maxLength={1024} placeholder="ssh-ed25519 AAAA..." rows={3} /></label>
      <button disabled={busy}>{busy?'Saving...':'Add SSH key'}</button></form>
    {keys.data?.keys.map(key=><article key={key.id}><h3>{key.label}</h3><p><code>{key.fingerprint}</code></p>
      <p>{key.revoked?'Revoked':Date.parse(key.expires_at)<=Date.now()?'Expired':'Expires '+new Date(key.expires_at).toLocaleDateString()}</p>
      {!key.revoked && <button className="subtle" disabled={busy} onClick={()=>void revoke(key)}>Revoke {key.label}</button>}
    </article>)}
  </section>
}
