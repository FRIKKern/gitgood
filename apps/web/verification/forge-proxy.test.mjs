import test from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'node:http'
import {createHash} from 'node:crypto'
import {proxy} from '../src/server/forge.ts'

test('canonical evidence downloads retain exact bytes and identity; denied and unrelated responses lose artifact headers',async()=>{
 const artifact=Buffer.from('Protected UTF-8 artifact · exact bytes\n'),digest=createHash('sha256').update(artifact).digest('hex')
 const evidence='/api/repos/team/project/pulls/11111111-1111-4111-8111-111111111111/links/22222222-2222-4222-8222-222222222222/evidence/33333333-3333-4333-8333-333333333333/download'
 const observed=[]
 const server=createServer((request,response)=>{
  observed.push({url:request.url,encoding:request.headers['accept-encoding'],authorization:request.headers.authorization})
  const refused=request.url.includes('denied=1')
  response.writeHead(refused?403:200,{'content-type':refused?'application/json':'application/octet-stream',
   'content-disposition':'attachment; filename="proof.txt"','x-gitgood-sha256':digest,'x-gitgood-access-context':'synthetic-context','content-length':refused?27:artifact.length})
  response.end(refused?'{"error":"source_denied"}   ':artifact)
 })
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
 const previous=process.env.GITGOOD_API_URL
 process.env.GITGOOD_API_URL='http://127.0.0.1:'+server.address().port
 try{
  const download=await proxy(new Request('http://web.example.invalid'+evidence+'?connection_generation=44444444-4444-4444-8444-444444444444',{headers:{authorization:'Bearer synthetic-session'}}))
  assert.equal(download.status,200);assert.equal(download.headers.get('content-type'),'application/octet-stream')
  assert.equal(download.headers.get('content-disposition'),'attachment; filename="proof.txt"')
  assert.equal(download.headers.get('x-gitgood-sha256'),digest);assert.equal(download.headers.get('x-content-type-options'),'nosniff')
  assert.equal(download.headers.get('cache-control'),'no-store');assert.equal(download.headers.get('x-gitgood-access-context'),'synthetic-context')
  assert.equal(download.headers.get('content-length'),null)
  assert.deepEqual(Buffer.from(await download.arrayBuffer()),artifact)
  assert.equal(observed[0].encoding,'identity');assert.equal(observed[0].authorization,'Bearer synthetic-session')
  assert(observed[0].url.endsWith('?connection_generation=44444444-4444-4444-8444-444444444444'))
  for(const [path,expected] of [[evidence+'?denied=1',403],[evidence+'/extra',200]]){
   const response=await proxy(new Request('http://web.example.invalid'+path))
   assert.equal(response.status,expected);assert.equal(response.headers.get('content-type'),'application/json')
   assert.equal(response.headers.get('content-disposition'),null);assert.equal(response.headers.get('x-gitgood-sha256'),null)
   assert.equal(response.headers.get('cache-control'),'no-store')
   await response.arrayBuffer()
  }
 }finally{
  if(previous===undefined)delete process.env.GITGOOD_API_URL;else process.env.GITGOOD_API_URL=previous
  server.closeAllConnections();await new Promise(resolve=>server.close(resolve))
 }
})
