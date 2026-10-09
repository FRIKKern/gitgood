import test from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'node:net'
import {selectComponentPorts} from './verification-component-ports.mjs'

async function occupiedLowPort() {
  for(let port=10000;port<10100;port++) {
    const server=createServer(socket=>socket.end('controlled listener'))
    try {
      await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',resolve)})
      return {server,port}
    }catch(error){if(error.code!=='EADDRINUSE'&&error.code!=='EACCES')throw error}
  }
  throw new Error('No controlled low port available')
}

test('default component sockets skip actual occupied ports and stay outside ephemeral range',async()=>{
  const {server,port}=await occupiedLowPort()
  let candidate=port
  try {
    const ports=await selectComponentPorts({}, {ephemeralStart:32768,choose:()=>candidate++})
    assert.equal(new Set(Object.values(ports)).size,3)
    assert(Object.values(ports).every(value=>value>port&&value<32768))
    assert(server.listening,'Existing listener must survive fixture selection')
    const probes=[]
    try {
      for(const value of Object.values(ports)) {
        const probe=createServer();await new Promise((resolve,reject)=>{probe.once('error',reject);probe.listen(value,'127.0.0.1',resolve)});probes.push(probe)
      }
    }finally{await Promise.all(probes.map(probe=>new Promise(resolve=>probe.close(resolve))))}
  }finally{await new Promise(resolve=>server.close(resolve))}
})

test('explicit occupied fixture ports refuse without changing another listener',async()=>{
  const {server,port}=await occupiedLowPort()
  try {
    await assert.rejects(selectComponentPorts({forge:port,web:port+1,ssh:port+2}),{code:'EADDRINUSE'})
    assert(server.listening)
  }finally{await new Promise(resolve=>server.close(resolve))}
})

test('malformed or aliased component descriptors refuse before choosing sockets',async()=>{
  let calls=0
  const options={ephemeralStart:32768,choose:()=>{calls++;return 20000}}
  for(const ports of [{forge:0},{web:NaN},{ssh:65536},{forge:20000,web:20000},{command:20000}])
    await assert.rejects(selectComponentPorts(ports,options))
  assert.equal(calls,0)
})
