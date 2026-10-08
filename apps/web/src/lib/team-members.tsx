import {useRef, useState, type FormEvent} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api, type Session} from './api'
type Member = {username: string; role: string}
type Event = {id: string; actor: string; username: string; previous_role: string; role: string; inserted_at: string}
export function TeamMembers({team, session}: {team: string; session: Session}) {
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const pending = useRef<{body: string; key: string} | null>(null)
  const result = useQuery({queryKey: ['members', team], retry: false,
    queryFn: ({signal}) => api<{members: Member[]; events: Event[]}>('/teams/' + encodeURIComponent(team) + '/members', {signal})})
  async function change(username: string, role: string, expectedRole: string) {
    const body = JSON.stringify({username, role, expected_role: expectedRole})
    if (pending.current?.body !== body) pending.current = {body, key: crypto.randomUUID()}
    setBusy(true); setError('')
    try {
      await api('/teams/' + encodeURIComponent(team) + '/members', {method: 'POST',
        headers: {'x-gitgood-csrf': session.csrf, 'idempotency-key': pending.current.key}, body})
      pending.current = null
    } catch (e) {setError(e instanceof Error ? e.message.replaceAll('_', ' ') : 'Membership change unavailable')}
    finally {setBusy(false); await result.refetch()}
  }
  function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    void change(String(data.get('username')), String(data.get('role')), 'absent')
  }
  return <section className="panel team-panel" aria-label={'Team members ' + team}>
    <h2>{team} · Members</h2><p>Owners manage existing installation accounts. The last owner is protected. Changes are audited and take effect in current access checks.</p>
    {error && <p role="alert">{error}</p>}
    {result.error ? <p role="alert">Team members unavailable. <button onClick={() => void result.refetch()}>Retry members</button></p> : result.data ? <>
      <ul className="member-list">{result.data.members.map(member => <li key={member.username}><strong>{member.username}</strong>
        <label>Role for {member.username}<select aria-label={'Role for ' + member.username} disabled={busy} value={member.role} onChange={event => void change(member.username, event.target.value, member.role)}>
          <option value="owner">Owner</option><option value="writer">Writer</option><option value="reader">Reader</option></select></label>
        <button className="subtle" disabled={busy} onClick={() => void change(member.username, 'absent', member.role)}>Remove {member.username}</button>
      </li>)}</ul>
      <form onSubmit={add}><h3>Add an installation account</h3><label>Member username<input name="username" required autoComplete="off" maxLength={64}/></label>
        <label>Member role<select aria-label="Member role" name="role" defaultValue="reader"><option value="reader">Reader</option><option value="writer">Writer</option><option value="owner">Owner</option></select></label>
        <button disabled={busy}>Add member</button></form>
      <details><summary>Membership history</summary><p>Most recent 100 changes. Earlier records remain in storage.</p>{result.data.events.map(event => <p key={event.id}>
        {event.actor} changed {event.username}: {event.previous_role} → {event.role} · <time>{event.inserted_at}</time></p>)}</details>
    </> : <p role="status">Loading team members…</p>}
  </section>
}
