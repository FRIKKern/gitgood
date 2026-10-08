// Fixed upstream: the browser cannot choose a destination or acquire a service credential.
export async function proxy(request: Request): Promise<Response> {
  const incoming = new URL(request.url)
  const base = new URL(process.env.GITGOOD_API_URL ?? 'http://127.0.0.1:47841')
  const target = new URL(incoming.pathname + incoming.search, base)
  if (target.origin !== base.origin || !target.pathname.startsWith('/api/')) return new Response(null, {status: 400})
  const headers = new Headers()
  for (const name of ['cookie', 'authorization', 'content-type', 'x-gitgood-csrf', 'idempotency-key', 'origin']) {
    const value = request.headers.get(name)
    if (value) headers.set(name, value)
  }
  headers.set('accept', 'application/json')
  const controller = new AbortController()
  request.signal.addEventListener('abort', () => controller.abort(), {once: true})
  const timeout = setTimeout(() => controller.abort(), 30_000)
  try {
    const body = ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer()
    if (body && body.byteLength > 1_048_576) return new Response(null, {status: 413})
    const result = await fetch(target, {method: request.method, headers, body, redirect: 'manual', signal: controller.signal})
    const responseHeaders = new Headers({'content-type': 'application/json', 'cache-control': 'no-store'})
    for (const cookie of result.headers.getSetCookie()) responseHeaders.append('set-cookie', cookie)
    return new Response(result.body, {status: result.status, headers: responseHeaders})
  } catch {
    return Response.json({error: 'forge_unavailable_retry'}, {status: 503, headers: {'cache-control': 'no-store'}})
  } finally {clearTimeout(timeout)}
}
