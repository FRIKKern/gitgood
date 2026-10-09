import {createServer} from 'node:net'
import {randomInt} from 'node:crypto'
import {readFile} from 'node:fs/promises'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'

async function ephemeralStart() {
  if(process.platform==='linux') {
    const fields=(await readFile('/proc/sys/net/ipv4/ip_local_port_range','utf8')).trim().split(/\s+/).map(Number)
    if(fields.length===2&&fields.every(Number.isInteger)&&fields[0]>10000&&fields[1]>=fields[0])return fields[0]
  }else if(process.platform==='win32') {
    const {stdout}=await promisify(execFile)('netsh',['int','ipv4','show','dynamicport','tcp'],{windowsHide:true,timeout:5000,maxBuffer:8192})
    // Numeric line endings survive localized labels; require exactly start/count.
    const fields=[...stdout.matchAll(/(\d+)\s*$/gm)].map(match=>Number(match[1]))
    if(fields.length===2&&fields[0]>10000&&fields[1]>0&&fields[0]+fields[1]<=65536)return fields[0]
  }
  throw new Error('Cannot establish the supported fixture TCP ephemeral range')
}

// These are disposable verifier endpoints, not production installation ports.
// Reserve the three sockets together, then release them for the real services.
// Defaults stay below the observed outbound ephemeral range so recent local
// database-client sockets cannot accidentally consume a fixture service port.
export async function selectComponentPorts(overrides={},options={}) {
  const names=['forge','web','ssh']
  if(Object.keys(overrides).some(name=>!names.includes(name))||
     Object.values(overrides).some(value=>!Number.isInteger(value)||value<1024||value>65535)||
     new Set(Object.values(overrides)).size!==Object.values(overrides).length)
    throw new Error('Invalid configured verification component ports')
  const attempts=options.attempts??32
  if(!Number.isInteger(attempts)||attempts<1||attempts>64)throw new Error('Invalid fixture port attempts')
  const start=names.some(name=>overrides[name]===undefined)?options.ephemeralStart??await ephemeralStart():null
  const upper=start===null?null:Math.min(start,32768)
  if(upper!==null&&(!Number.isInteger(upper)||upper<=10000))throw new Error('Unsupported fixture TCP range')
  const choose=options.choose??(()=>randomInt(10000,upper))
  const reserved=[],selected={}
  try {
    for(const name of names) {
      let last
      for(let attempt=0;attempt<attempts;attempt++) {
        const explicit=overrides[name]!==undefined
        const port=explicit?overrides[name]:choose()
        if(!Number.isInteger(port)||port<1024||port>65535||(!explicit&&(port<10000||port>=upper)))throw new Error('Invalid fixture TCP candidate')
        if(Object.values(selected).includes(port))continue
        const server=createServer()
        try {
          await new Promise((resolve,reject)=>{
            server.once('error',reject)
            server.listen({host:'127.0.0.1',port,exclusive:true},resolve)
          })
          reserved.push(server);selected[name]=port;break
        }catch(error) {
          if(server.listening)await new Promise(resolve=>server.close(resolve))
          if(explicit||!['EADDRINUSE','EACCES'].includes(error.code))throw error
          last=error
        }
      }
      if(selected[name]===undefined)throw new Error('No usable private fixture '+name+' port',{cause:last})
    }
    return selected
  }finally {
    await Promise.all(reserved.map(server=>new Promise(resolve=>server.close(resolve))))
  }
}
