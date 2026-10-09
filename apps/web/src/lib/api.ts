import {accessStore} from './access-state'
export type Session = {user: {id: number; username: string}; csrf: string; teams: {team: string; role: string}[]; access_context: string}
export type Repository = {id: number; team: string; name: string; status: string; url: string; clone_url: string; ssh_clone_url: string | null; owner_id: number}
export class ApiError extends Error {constructor(public status: number, message: string, public details: Record<string,unknown> = {}) {super(message)}}
export async function privateRequest<T>(path: string, init: RequestInit, consume: (response: Response) => Promise<T>): Promise<T> {
  const store = accessStore(), ticket = store?.ticket()
  const sessionRequest = path === '/session'
  const method = init.method ?? 'GET'
  const headers = new Headers(init.headers)
  if (!headers.has('content-type')) headers.set('content-type', 'application/json')
  if (!sessionRequest && ticket?.context) headers.set('x-gitgood-access-context', ticket.context)
  let intent: {digest: string; key: string} | undefined
  if (!sessionRequest && store && ticket && typeof init.body === 'string' && headers.has('idempotency-key')) {
    intent = await store.intent(ticket, path, init.body, headers.get('idempotency-key')!)
    headers.set('idempotency-key', intent.key)
  }
  const current = () => !store || !ticket || store.valid(ticket)
  if (!current()) throw new ApiError(409, 'access_changed_refetch')
  let response: Response
  try {response = await fetch('/api' + path, {...init, headers})}
  catch (error) {if (!init.signal?.aborted && sessionRequest && method === 'GET' && store && ticket) store.unavailable(ticket); throw error}
  const context = response.headers.get('x-gitgood-access-context')
  if (!current()) {await response.body?.cancel(); throw new ApiError(409, 'access_changed_refetch')}
  if (!sessionRequest && store && ticket) {
    if (response.status === 401) store.anonymous(ticket)
    else if (!store.observe(ticket, context)) {await response.body?.cancel(); throw new ApiError(409, 'access_changed_refetch')}
  }
  const result = await consume(response)
  if (sessionRequest && store && ticket) {
    if (method === 'DELETE' && response.ok) store.anonymous(ticket, true)
    else if (response.ok) {
      if (!store.acceptSession(ticket, result as Session, context)) throw new ApiError(409, 'access_changed_refetch')
    }
  } else if (!current()) throw new ApiError(409, 'access_changed_refetch')
  if (response.ok && intent) store?.settled(intent.digest)
  return result
}
async function json<T>(response: Response): Promise<T> {
  let result: Record<string,unknown>
  try {result = await response.json()}
  catch {throw new ApiError(response.status, 'forge_response_unavailable')}
  if (!response.ok) throw new ApiError(response.status, typeof result.error === 'string' ? result.error : 'Request failed', result)
  return result as T
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const store = accessStore(), ticket = store?.ticket()
  try {return await privateRequest<T>(path, init, json<T>)}
  catch (error) {
    if (!init.signal?.aborted && path === '/session' && (!init.method || init.method === 'GET') && store && ticket) {
      if (error instanceof ApiError && error.status === 401) store.anonymous(ticket)
      else if (!(error instanceof ApiError && error.message === 'access_changed_refetch')) store.unavailable(ticket)
    }
    throw error
  }
}
