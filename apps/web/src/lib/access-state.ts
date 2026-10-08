import type {Session} from './api'
export type AccessState = {generation: number; status: 'checking' | 'authorized' | 'anonymous' | 'unavailable' | 'suspended'; context: string | null; session?: Session}
export type Ticket = {generation: number; context: string | null; actor: number | null}
type Notice = {reset: boolean; refresh: boolean; purgeDrafts: boolean}
export class BrowserAccess {
  private state: AccessState = {generation: 0, status: 'checking', context: null}
  private lastActor: number | null = null
  private listeners = new Set<() => void>()
  private notices = new Set<(notice: Notice) => void>()
  private channel: BroadcastChannel | null = null
  private pending = new Map<string, {key: string; expires: number}>()
  private intentSecret = crypto.subtle.generateKey({name: 'HMAC', hash: 'SHA-256'}, false, ['sign'])
  constructor() {
    // This marker only decides whether to discard a revision-bound local draft
    // after reload. It grants no access: the page remains checking until GET session.
    try {
      const previous = JSON.parse(sessionStorage.getItem('gitgood-access-marker') ?? 'null')
      if (/^[A-Za-z0-9_-]{43}$/.test(previous?.context) && Number.isSafeInteger(previous?.actor)) {
        this.state = {...this.state, context: previous.context}
        this.lastActor = previous.actor
      }
    } catch { /* Disabled browser storage does not prevent current access checks. */ }
    if (typeof BroadcastChannel !== 'undefined') {
      this.channel = new BroadcastChannel('gitgood-access-v1')
      this.channel.onmessage = () => this.invalidate(true)
    }
  }
  snapshot = () => this.state
  subscribe = (listener: () => void) => {this.listeners.add(listener); return () => {this.listeners.delete(listener)}}
  onNotice = (listener: (notice: Notice) => void) => {this.notices.add(listener); return () => {this.notices.delete(listener)}}
  ticket(): Ticket {return {generation: this.state.generation, context: this.state.context, actor: this.state.session?.user.id ?? null}}
  valid(ticket: Ticket) {return ticket.generation === this.state.generation}
  private emit(notice: Notice) {for (const listener of this.notices) listener(notice); for (const listener of this.listeners) listener()}
  invalidate(purgeDrafts = false) {
    const hidden = document.visibilityState === 'hidden'
    this.state = {...this.state, generation: this.state.generation + 1, status: hidden ? 'suspended' : 'checking', session: undefined}
    this.emit({reset: true, refresh: !hidden, purgeDrafts})
  }
  suspend() {
    this.state = {...this.state, generation: this.state.generation + 1, status: 'suspended', session: undefined}
    this.emit({reset: true, refresh: false, purgeDrafts: false})
  }
  unavailable(ticket: Ticket) {
    if (!this.valid(ticket)) return
    this.state = {...this.state, generation: this.state.generation + 1, status: 'unavailable', session: undefined}
    this.emit({reset: true, refresh: false, purgeDrafts: false})
  }
  anonymous(ticket: Ticket, explicit = false) {
    if (!this.valid(ticket)) return false
    if (this.state.status === 'anonymous' && !explicit) return true
    this.state = {generation: this.state.generation + 1, status: 'anonymous', context: null}
    try {sessionStorage.removeItem('gitgood-access-marker')} catch {}
    // Opaque unknown-outcome nonces are retained for the same actor's recovery,
    // but never carried to a different verified actor.
    this.emit({reset: true, refresh: false, purgeDrafts: true})
    if (explicit) this.channel?.postMessage('changed')
    return true
  }
  observe(ticket: Ticket, context: string | null): boolean {
    if (!this.valid(ticket)) return false
    if (!context || !/^[A-Za-z0-9_-]{43}$/.test(context)) {
      this.unavailable(ticket)
      return false
    }
    if (context !== this.state.context) {
      this.state = {...this.state, generation: this.state.generation + 1, status: 'checking', context, session: undefined}
      this.emit({reset: true, refresh: true, purgeDrafts: true})
      this.channel?.postMessage('changed')
      return false
    }
    return true
  }
  acceptSession(ticket: Ticket, session: Session, context: string | null) {
    if (!this.valid(ticket)) return false
    if (!context || context !== session?.access_context || !/^[A-Za-z0-9_-]{43}$/.test(context) ||
      !session.user || !Number.isSafeInteger(session.user.id) || !Array.isArray(session.teams)) {
      this.unavailable(ticket)
      return false
    }
    const changed = context !== this.state.context
    if (this.lastActor !== null && this.lastActor !== session.user.id) this.pending.clear()
    this.lastActor = session.user.id
    this.state = {generation: this.state.generation + (changed ? 1 : 0), status: 'authorized', context, session}
    try {sessionStorage.setItem('gitgood-access-marker', JSON.stringify({context, actor: session.user.id}))} catch {}
    this.emit({reset: changed, refresh: false, purgeDrafts: changed})
    if (changed) this.channel?.postMessage('changed')
    return true
  }
  async intent(ticket: Ticket, path: string, body: string, proposed: string) {
    // A non-extractable ephemeral HMAC key prevents private request fingerprints
    // from becoming a dictionary of titles or comments. No payload is retained.
    const now = Date.now()
    for (const [digest, value] of this.pending) if (value.expires <= now) this.pending.delete(digest)
    const bytes = await crypto.subtle.sign('HMAC', await this.intentSecret, new TextEncoder().encode(JSON.stringify([ticket.actor, path, body])))
    const digest = Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join('')
    if (!this.pending.has(digest) && this.pending.size >= 128) throw new Error('Too many unresolved requests. Reconcile their outcomes before continuing.')
    const key = this.pending.get(digest)?.key ?? proposed
    this.pending.set(digest, {key, expires: now + 86_400_000})
    return {digest, key}
  }
  settled(digest: string) {this.pending.delete(digest)}
}
let instance: BrowserAccess | null = null
export function accessStore() {
  if (typeof window === 'undefined') return null
  return instance ??= new BrowserAccess()
}
