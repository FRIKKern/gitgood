import test from 'node:test'
import assert from 'node:assert/strict'
import {mkdtemp,writeFile,readFile,chmod,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {randomBytes} from 'node:crypto'
import {provisionConfiguration,readConfiguration,validateConfiguration,privateFile} from '../../priv/operations/recovery-configuration.mjs'
import {RecoveryError} from '../../priv/operations/recovery-bundle.mjs'
async function fixture(t){
  const root=await mkdtemp(join(tmpdir(),'gitgood-recovery-config-'))
  t.after(()=>rm(root,{recursive:true,force:true}))
  const certificate=join(root,'certificate'),tlsKey=join(root,'key'),sourceCa=join(root,'source-ca')
  for(const path of [certificate,tlsKey,sourceCa])await writeFile(path,'synthetic-material')
  const proxy=randomBytes(32).toString('base64'),directory=join(root,'configuration')
  const forge={DATABASE_URL:'postgresql://synthetic:synthetic@127.0.0.1:55432/synthetic',
    SECRET_KEY_BASE:randomBytes(64).toString('base64'),PHX_HOST:'localhost',GITGOOD_PUBLIC_URL:'https://localhost:443',
    GITGOOD_WEB_ORIGIN:'https://localhost:443',GITGOOD_PROXY_KEY:proxy,GITGOOD_CONNECTION_KEY:randomBytes(32).toString('base64'),
    GITGOOD_BARKPARK_ORIGIN:'https://localhost:444',GITGOOD_BARKPARK_CA:sourceCa,GITGOOD_STORAGE:join(root,'git'),PORT:'47841',
    GITGOOD_SSH_PORT:'47842',GITGOOD_SSH_HOST_KEY_DIRECTORY:join(root,'ssh'),GITGOOD_SSH_PUBLIC_HOST:'localhost',GITGOOD_SSH_PUBLIC_PORT:'47842',
    UNRELATED_SECRET:'must-never-be-copied',GITGOOD_BOOTSTRAP_PASSWORD:'must-never-be-copied'}
  const web={PORT:'47840',GITGOOD_API_URL:'http://127.0.0.1:47841',GITGOOD_PROXY_KEY:proxy,NODE_ENV:'production',UNRELATED_SECRET:'must-never-be-copied'}
  await provisionConfiguration({directory,forge,web,certificate,tlsKey,sourceCa})
  return {root,directory,forge,web}
}
test('configuration retains required custody and only explicit native settings',async t=>{
  const f=await fixture(t),config=await readConfiguration(f.directory)
  assert.equal(config.forge.GITGOOD_CONNECTION_KEY,f.forge.GITGOOD_CONNECTION_KEY)
  assert.equal(config.web.GITGOOD_PROXY_KEY,f.web.GITGOOD_PROXY_KEY)
  assert.equal(config.forge.GITGOOD_BOOTSTRAP_PASSWORD,undefined)
  assert(!(await readFile(join(f.directory,'installation.json'),'utf8')).includes('must-never-be-copied'))
  await assert.rejects(provisionConfiguration({directory:f.directory,forge:f.forge,web:f.web,certificate:'unused',tlsKey:'unused'}))
})
test('missing custody, mismatched edge key and unknown configuration reject',async t=>{
  const f=await fixture(t),config=await readConfiguration(f.directory)
  for(const mutate of [c=>delete c.forge.GITGOOD_CONNECTION_KEY,c=>c.web.GITGOOD_PROXY_KEY=randomBytes(32).toString('base64'),
    c=>c.forge.UNKNOWN='untracked',c=>c.edge.tls_key='../elsewhere']){
    const copy=structuredClone(config);mutate(copy);assert.throws(()=>validateConfiguration(copy),RecoveryError)
  }
})
test('group-readable key material refuses on the supported Linux profile',async t=>{
  if(process.platform!=='linux')return
  const f=await fixture(t),path=join(f.directory,'tls-key.pem')
  await chmod(path,0o644)
  await assert.rejects(privateFile(path),RecoveryError)
  await assert.rejects(readConfiguration(f.directory),RecoveryError)
})
