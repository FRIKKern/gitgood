import {expect} from '@playwright/test'
const upstream = process.env.GITGOOD_TEST_API_URL ?? 'http://127.0.0.1:47841'
type Actor = 'owner' | 'reviewer' | 'reader' | 'outsider'
type Headers = {authorization: string; 'content-type': string}
// One API session per synthetic actor in this worker. Browser sign-in still
// executes through the actual UI. Tokens live only in this test process.
const sessions = new Map<Actor, Promise<Headers>>()
export function fixtureSession(actor: Actor): Promise<Headers> {
  let pending = sessions.get(actor)
  if (!pending) {
    pending = (async () => {
      const response = await fetch(upstream + '/api/session', {method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({username: actor, password: 'synthetic-password'})})
      expect(response.status).toBe(200)
      const token = /gitgood_session=([^;]+)/.exec(response.headers.getSetCookie()[0])![1]
      return {authorization: 'Bearer ' + token, 'content-type': 'application/json'}
    })()
    sessions.set(actor, pending)
    void pending.catch(() => sessions.delete(actor))
  }
  return pending
}
