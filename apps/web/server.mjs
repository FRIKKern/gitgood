import app from './dist/server/server.js'
import {readFileSync} from 'node:fs'
import {decodeProxyKey,prepareClientAddress} from './client-address.mjs'
const proxyKey=process.env.GITGOOD_PROXY_KEY ? decodeProxyKey(process.env.GITGOOD_PROXY_KEY) : null
if(process.env.NODE_ENV==='production'&&!proxyKey)throw new Error('Production web requires GITGOOD_PROXY_KEY')
const identity=JSON.parse(readFileSync(new URL('./dist/build-identity.json',import.meta.url),'utf8'))
const api=new URL(process.env.GITGOOD_API_URL ?? 'http://127.0.0.1:47841')
if(!['127.0.0.1','localhost','[::1]'].includes(api.hostname) || api.protocol!=='http:' || api.username || api.password || api.pathname!=='/' || api.search || api.hash)throw new Error('The production forge upstream must be a fixed loopback HTTP origin')
export default {
  hostname:'127.0.0.1',port:Number(process.env.PORT ?? 47840),
  async fetch(request) {
    const pathname=new URL(request.url).pathname
    if(pathname==='/health/live')return Response.json({service:'gitgood-web',...identity},{headers:{'cache-control':'no-store'}})
    if(pathname==='/health/ready') {
      try {
        const result=await fetch(new URL('/health/ready',api),{signal:AbortSignal.timeout(3000)})
        const forge=await result.json()
        const ready=result.ok && !identity.dirty && forge.candidate===identity.candidate && forge.status==='ready'
        return Response.json({service:'gitgood-web',status:ready?'ready':'unavailable',candidate:identity.candidate,forge_candidate:forge.candidate,dirty:identity.dirty},{status:ready?200:503,headers:{'cache-control':'no-store'}})
      }catch{return Response.json({status:'unavailable',candidate:identity.candidate},{status:503,headers:{'cache-control':'no-store'}})}
    }
    const prepared=prepareClientAddress(request,proxyKey)
    if(prepared.error)return prepared.error
    const response=await app.fetch(prepared.request)
    response.headers.set('x-content-type-options','nosniff')
    response.headers.set('referrer-policy','same-origin')
    response.headers.set('content-security-policy',"base-uri 'self'; object-src 'none'; frame-ancestors 'none'")
    return response
  }
}
