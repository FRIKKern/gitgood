import test from 'node:test'
import assert from 'node:assert/strict'
import {randomBytes,createHmac} from 'node:crypto'
import {decodeProxyKey,prepareClientAddress,clientAddressHeaders} from '../client-address.mjs'
const key=randomBytes(32)
const request=(headers={},peer='127.0.0.1',path='/api/session',method='POST')=>{
 const req=new Request('http://localhost:47840'+path,{method,headers})
 req.runtime={node:{req:{socket:{remoteAddress:peer}}}}
 return req
}
const edge=(address='198.51.100.17')=>({'x-gitgood-edge-key':key.toString('base64'),'x-gitgood-edge-client':address})
test('configuration requires canonical 32-byte secret encoding',()=>{
 assert.deepEqual(decodeProxyKey(key.toString('base64')),key)
 for(const value of [undefined,'short',randomBytes(31).toString('base64'),key.toString('base64')+'\n'])
   assert.throws(()=>decodeProxyKey(value))
})
test('web derives fresh path-bound MAC and removes edge secret and all caller assertions',()=>{
 const req=request({...edge(),'x-gitgood-client-address':'9.9.9.9','x-gitgood-client-time':'0',
   'x-gitgood-client-signature':'fake','x-forwarded-for':'1.2.3.4','forwarded':'for=5.6.7.8'},
   '::ffff:127.0.0.1','/api/session?attempt=1')
 const out=prepareClientAddress(req,key,1791484000)
 assert.equal(out.request,req)
 assert.equal(req.headers.get('x-gitgood-edge-key'),null)
 assert.equal(req.headers.get('x-gitgood-edge-client'),null)
 assert.equal(req.headers.get('x-gitgood-client-address'),'198.51.100.17')
 const frame=['gitgood-login-origin-v1','198.51.100.17','1791484000','POST','/api/session?attempt=1'].join('\n')
 assert.equal(req.headers.get('x-gitgood-client-signature'),createHmac('sha256',key).update(frame).digest('hex'))
})
test('a caller cannot manufacture an edge, socket peer or malformed address',()=>{
 for(const [headers,peer] of [[{},'127.0.0.1'],[{...edge(),'x-gitgood-edge-key':'fake'},'127.0.0.1'],
     [edge(),'198.51.100.18'],[edge(),''],[edge('198.51.100.17, 9.9.9.9'),'127.0.0.1'],
     [edge('127.0.0.1%zone'),'127.0.0.1']]) {
   assert.equal(prepareClientAddress(request(headers,peer),key).error.status,403)
 }
})
test('non-login and development requests remove untrusted assertions without signing',()=>{
 for(const [path,configured] of [['/api/repos',key],['/api/session',null]]) {
   const req=request(Object.fromEntries(clientAddressHeaders.map(name=>[name,'caller-value'])),'127.0.0.1',path)
   assert.equal(prepareClientAddress(req,configured).request,req)
   for(const name of clientAddressHeaders)assert.equal(req.headers.get(name),null)
 }
})
