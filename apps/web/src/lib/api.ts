export type Session = {user: {id: number; username: string}; csrf: string; teams: {team: string; role: string}[]}
export type Repository = {id: number; team: string; name: string; status: string; url: string; clone_url: string; ssh_clone_url: string | null; owner_id: number}
export class ApiError extends Error {constructor(public status: number, message: string, public details: Record<string,unknown> = {}) {super(message)}}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch('/api' + path, {...init, headers: {'content-type': 'application/json', ...init.headers}})
  const result = await response.json()
  if (!response.ok) throw new ApiError(response.status, result.error ?? 'Request failed', result)
  return result as T
}
