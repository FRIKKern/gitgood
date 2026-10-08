// The browser cannot select an upstream or acquire a service credential.
export async function proxy(request: Request): Promise<Response> {
  const incoming=new URL(request.url)
  const base=new URL(process.env.GITGOOD_API_URL ?? 'http://127.0.0.1:47841')
  const target=new URL(incoming.pathname+incoming.search,base)
  if(target.origin!==base.origin || !target.pathname.startsWith('/api/'))return Response.json({error:'invalid_api_path'},{status:400})
  const headers=new Headers()
  for(const name of ['cookie','authorization','content-type','x-gitgood-csrf','idempotency-key','origin']) {
    const value=request.headers.get(name);if(value)headers.set(name,value)
  }
  headers.set('accept','application/json')
  const controller=new AbortController()
  const abort=()=>controller.abort()
  request.signal.addEventListener('abort',abort,{once:true})
  const timeout=setTimeout(abort,30000)
  let reader:ReadableStreamDefaultReader<Uint8Array> | undefined
  const cancel=()=>{void reader?.cancel()}
  controller.signal.addEventListener('abort',cancel,{once:true})
  try {
    let body:ArrayBuffer | undefined
    if(!['GET','HEAD'].includes(request.method) && request.body) {
      reader=request.body.getReader()
      const chunks:Uint8Array[]=[]
      let bytes=0
      while(true) {
        const next=await reader.read()
        controller.signal.throwIfAborted()
        if(next.done)break
        bytes+=next.value.byteLength
        if(bytes>1048576){await reader.cancel();return Response.json({error:'api_body_limit'},{status:413})}
        chunks.push(next.value)
      }
      const joined=new Uint8Array(bytes)
      let offset=0
      for(const chunk of chunks){joined.set(chunk,offset);offset+=chunk.byteLength}
      body=joined.buffer
    }
    const result=await fetch(target,{method:request.method,headers,body,redirect:'manual',signal:controller.signal})
    const responseHeaders=new Headers({'content-type':'application/json','cache-control':'no-store'})
    for(const cookie of result.headers.getSetCookie())responseHeaders.append('set-cookie',cookie)
    return new Response(result.body,{status:result.status,headers:responseHeaders})
  }catch{return Response.json({error:'forge_unavailable_retry'},{status:503,headers:{'cache-control':'no-store'}})}
  finally{clearTimeout(timeout);request.signal.removeEventListener('abort',abort);controller.signal.removeEventListener('abort',cancel);reader?.releaseLock()}
}
