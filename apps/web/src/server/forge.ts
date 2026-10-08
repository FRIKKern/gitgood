// The browser cannot select an upstream or acquire a service credential.
export async function proxy(request: Request): Promise<Response> {
  const incoming = new URL(request.url)
  const base = new URL(process.env.GITGOOD_API_URL ?? 'http://127.0.0.1:47841')
  const target = new URL(incoming.pathname + incoming.search, base)
  if (target.origin !== base.origin || !target.pathname.startsWith('/api/'))
    return Response.json({error: 'invalid_api_path'}, {status: 400})
  const bundleUpload = request.method === 'PUT' &&
    /^\/api\/repos\/[a-z0-9-]+\/[a-z0-9-]+\/imports\/[0-9a-f-]{36}\/source$/.test(target.pathname)
  const assetUpload = request.method === 'PUT' &&
    /^\/api\/repos\/[a-z0-9-]+\/[a-z0-9-]+\/releases\/[0-9a-f-]{36}\/assets\/[0-9a-f-]{36}\/source$/.test(target.pathname)
  const assetDownload = request.method === 'GET' &&
    /^\/api\/repos\/[a-z0-9-]+\/[a-z0-9-]+\/releases\/[0-9a-f-]{36}\/assets\/[0-9a-f-]{36}\/download$/.test(target.pathname)
  const upload = bundleUpload || assetUpload
  const limit = bundleUpload ? 33_554_432 : assetUpload ? 16_777_216 : 1_048_576
  const declared = request.headers.get('content-length')
  if (declared && /^\d+$/.test(declared) && Number(declared) > limit)
    return Response.json({error: 'api_body_limit'}, {status: 413})
  const headers = new Headers()
  for (const name of ['cookie', 'authorization', 'content-type', 'x-gitgood-csrf', 'x-gitgood-access-context', 'idempotency-key', 'origin']) {
    const value = request.headers.get(name)
    if (value) headers.set(name, value)
  }
  headers.set('accept', 'application/json')
  if (assetDownload) headers.set('accept-encoding', 'identity')
  const controller = new AbortController()
  const abort = () => controller.abort()
  request.signal.addEventListener('abort', abort, {once: true})
  if (request.signal.aborted) abort()
  const timeout = setTimeout(abort, upload ? 20_000 : 30_000)
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  let exceeded = false
  const cancel = () => {void reader?.cancel().catch(() => {})}
  controller.signal.addEventListener('abort', cancel, {once: true})
  try {
    let body: ArrayBuffer | ReadableStream<Uint8Array> | undefined
    if (!['GET', 'HEAD'].includes(request.method) && request.body) {
      reader = request.body.getReader()
      let bytes = 0
      if (upload) {
        // Preserve streaming backpressure at the proxy; forge bounds asset buffering.
        body = new ReadableStream<Uint8Array>({
          async pull(stream) {
            try {
              controller.signal.throwIfAborted()
              const next = await reader!.read()
              controller.signal.throwIfAborted()
              if (next.done) {stream.close(); return}
              bytes += next.value.byteLength
              if (bytes > limit) {
                exceeded = true
                await reader!.cancel()
                stream.error(new Error('api_body_limit'))
                controller.abort()
                return
              }
              stream.enqueue(next.value)
            } catch (error) {stream.error(error)}
          },
          async cancel() {await reader?.cancel()},
        }, {highWaterMark: 1})
      } else {
        const chunks: Uint8Array[] = []
        while (true) {
          const next = await reader.read()
          controller.signal.throwIfAborted()
          if (next.done) break
          bytes += next.value.byteLength
          if (bytes > limit) {await reader.cancel(); return Response.json({error: 'api_body_limit'}, {status: 413})}
          chunks.push(next.value)
        }
        const joined = new Uint8Array(bytes)
        let offset = 0
        for (const chunk of chunks) {joined.set(chunk, offset); offset += chunk.byteLength}
        body = joined.buffer
      }
    }
    const options: RequestInit & {duplex?: 'half'} = {
      method: request.method, headers, body, redirect: 'manual', signal: controller.signal,
      ...(upload && body ? {duplex: 'half' as const} : {}),
    }
    const result = await fetch(target, options)
    const responseHeaders = new Headers({'content-type': 'application/json', 'cache-control': 'no-store'})
    const accessContext = result.headers.get('x-gitgood-access-context')
    if (accessContext) responseHeaders.set('x-gitgood-access-context', accessContext)
    if (assetDownload && result.ok) {
      responseHeaders.set('content-type', 'application/octet-stream')
      responseHeaders.set('x-content-type-options', 'nosniff')
      // Fetch may decompress an upstream response; its wire length is not the
      // length of this stream. Let the response server frame the actual body.
      for (const name of ['content-disposition', 'x-gitgood-sha256']) {
        const value = result.headers.get(name)
        if (value) responseHeaders.set(name, value)
      }
    }
    for (const cookie of result.headers.getSetCookie()) responseHeaders.append('set-cookie', cookie)
    return new Response(result.body, {status: result.status, headers: responseHeaders})
  } catch {
    return Response.json({error: exceeded ? 'api_body_limit' : 'forge_unavailable_retry'},
      {status: exceeded ? 413 : 503, headers: {'cache-control': 'no-store'}})
  } finally {
    clearTimeout(timeout)
    request.signal.removeEventListener('abort', abort)
    controller.signal.removeEventListener('abort', cancel)
    await reader?.cancel().catch(() => {})
    reader?.releaseLock()
  }
}
