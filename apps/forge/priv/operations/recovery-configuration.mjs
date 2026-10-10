import {readFile,writeFile,mkdir,lstat,realpath} from 'node:fs/promises'
import {join,resolve} from 'node:path'
import {randomUUID} from 'node:crypto'
import {RecoveryError} from './recovery-bundle.mjs'

export const forgeKeys=['DATABASE_URL','SECRET_KEY_BASE','PHX_HOST','GITGOOD_PUBLIC_URL','GITGOOD_WEB_ORIGIN','GITGOOD_PROXY_KEY',
  'GITGOOD_CONNECTION_KEY','GITGOOD_BARKPARK_ORIGIN','GITGOOD_BARKPARK_CA','GITGOOD_INSTALLATION_ID','GITGOOD_STORAGE','PORT',
  'GITGOOD_SSH_PORT','GITGOOD_SSH_HOST_KEY_DIRECTORY','GITGOOD_SSH_PUBLIC_HOST','GITGOOD_SSH_PUBLIC_PORT']
const webKeys=['PORT','GITGOOD_API_URL','GITGOOD_PROXY_KEY','NODE_ENV']
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/
const check=(condition)=>{if(!condition)throw new RecoveryError('configuration_invalid')}
const pick=(env,keys)=>Object.fromEntries(keys.filter(key=>env[key]!==undefined).map(key=>[key,env[key]]))
export function validateConfiguration(config){
  check(config&&Object.keys(config).sort().join(',')==='edge,forge,installation,protocol,web')
  check(config.protocol===1&&typeof config.installation==='string'&&uuid.test(config.installation))
  if(Object.hasOwn(config.forge??{},'GITGOOD_INSTALLATION_ID'))
    check(config.forge.GITGOOD_INSTALLATION_ID===config.installation)
  for(const [env,keys] of [[config.forge,forgeKeys],[config.web,webKeys]]){
    check(env&&Object.getPrototypeOf(env)===Object.prototype&&Object.keys(env).every(key=>keys.includes(key)))
    check(Object.values(env).every(value=>typeof value==='string'&&value.length>0&&Buffer.byteLength(value)<=8192&&!value.includes('\0')))
  }
  for(const key of ['DATABASE_URL','SECRET_KEY_BASE','PHX_HOST','GITGOOD_PUBLIC_URL','GITGOOD_WEB_ORIGIN','GITGOOD_PROXY_KEY',
    'GITGOOD_STORAGE','PORT','GITGOOD_SSH_PORT','GITGOOD_SSH_HOST_KEY_DIRECTORY','GITGOOD_SSH_PUBLIC_HOST','GITGOOD_SSH_PUBLIC_PORT'])check(Boolean(config.forge[key]))
  check(config.forge.SECRET_KEY_BASE.length>=64)
  for(const key of ['GITGOOD_PROXY_KEY',...(config.forge.GITGOOD_BARKPARK_ORIGIN?['GITGOOD_CONNECTION_KEY']:[])])
    check(Buffer.from(config.forge[key]??'','base64').length===32&&Buffer.from(config.forge[key],'base64').toString('base64')===config.forge[key])
  check(config.web.NODE_ENV==='production'&&config.web.GITGOOD_PROXY_KEY===config.forge.GITGOOD_PROXY_KEY)
  for(const key of ['GITGOOD_PUBLIC_URL','GITGOOD_WEB_ORIGIN',...(config.forge.GITGOOD_BARKPARK_ORIGIN?['GITGOOD_BARKPARK_ORIGIN']:[])])
    check(new URL(config.forge[key]).protocol==='https:')
  check(config.edge&&Object.keys(config.edge).sort().join(',')===(config.forge.GITGOOD_BARKPARK_CA?'source_ca,tls_certificate,tls_key':'tls_certificate,tls_key'))
  check(config.edge.tls_certificate==='tls-certificate.pem'&&config.edge.tls_key==='tls-key.pem')
  if(config.forge.GITGOOD_BARKPARK_CA)check(config.edge.source_ca==='source-ca.pem')
  return config
}
export async function privateFile(path,maximum=1048576){
  path=resolve(path)
  const stat=await lstat(path)
  check(stat.isFile()&&stat.nlink===1&&stat.size<=maximum&&(stat.mode&0o077)===0&&(await realpath(path))===path)
  return readFile(path)
}
export async function readConfiguration(directory){
  directory=resolve(directory)
  const stat=await lstat(directory)
  check(stat.isDirectory()&&(stat.mode&0o077)===0&&(await realpath(directory))===directory)
  const config=validateConfiguration(JSON.parse((await privateFile(join(directory,'installation.json'))).toString('utf8')))
  for(const file of Object.values(config.edge))await privateFile(join(directory,file))
  return config
}
export async function provisionConfiguration({directory,forge,web,certificate,tlsKey,sourceCa,installation=randomUUID()}){
  const config=validateConfiguration({protocol:1,installation,forge:pick(forge,forgeKeys),web:pick(web,webKeys),
    edge:{tls_certificate:'tls-certificate.pem',tls_key:'tls-key.pem',...(forge.GITGOOD_BARKPARK_CA?{source_ca:'source-ca.pem'}:{})}})
  await mkdir(directory,{mode:0o700})
  await writeFile(join(directory,'installation.json'),JSON.stringify(config)+'\n',{flag:'wx',mode:0o600})
  for(const [name,path] of [['tls-certificate.pem',certificate],['tls-key.pem',tlsKey],...(forge.GITGOOD_BARKPARK_CA?[['source-ca.pem',sourceCa]]:[])])
    await writeFile(join(directory,name),await readFile(path),{flag:'wx',mode:0o600})
  return config.installation
}
