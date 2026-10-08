import {createHmac,timingSafeEqual} from 'node:crypto'
import {isIP} from 'node:net'

const edgeNames=['x-gitgood-edge-key','x-gitgood-edge-client']
const signedNames=['x-gitgood-client-address','x-gitgood-client-time','x-gitgood-client-signature']
export const clientAddressHeaders=Object.freeze([...edgeNames,...signedNames])

export function decodeProxyKey(encoded) {
  if(typeof encoded!=='string'|| !/^[A-Za-z0-9+/]{43}=$/.test(encoded))throw new Error('GITGOOD_PROXY_KEY must encode 32 random bytes')
  const key=Buffer.from(encoded,'base64')
  if(key.length!==32||key.toString('base64')!==encoded)throw new Error('GITGOOD_PROXY_KEY must encode 32 random bytes')
  return key
}
const loopback=peer=>peer==='::1'||(typeof peer==='string'&&/^127\./.test(peer)&&isIP(peer)===4)||
  (typeof peer==='string'&&peer.startsWith('::ffff:127.')&&isIP(peer)===6)
const equal=(a,b)=>a.length===b.length&&timingSafeEqual(a,b)
export function prepareClientAddress(request,key,now=Math.floor(Date.now()/1000)) {
  const url=new URL(request.url)
  const supplied=request.headers.get('x-gitgood-edge-key')??''
  const address=request.headers.get('x-gitgood-edge-client')??''
  for(const name of clientAddressHeaders)request.headers.delete(name)
  const login=request.method==='POST'&&url.pathname==='/api/session'
  if(login&&key) {
    const peer=request.runtime?.node?.req?.socket?.remoteAddress
    if(!loopback(peer)||!equal(Buffer.from(supplied),Buffer.from(key.toString('base64')))||!isIP(address))
      return {error:Response.json({error:'client_address_unverified'},{status:403,headers:{'cache-control':'no-store'}})}
    const stamp=String(now)
    const path=url.pathname+url.search
    const frame=['gitgood-login-origin-v1',address,stamp,request.method,path].join('\n')
    request.headers.set('x-gitgood-client-address',address)
    request.headers.set('x-gitgood-client-time',stamp)
    request.headers.set('x-gitgood-client-signature',createHmac('sha256',key).update(frame).digest('hex'))
  }
  // Keep the original body/abort stream and srvx socket context; the edge secret is consumed.
  return {request}
}
