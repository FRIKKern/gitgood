import test from 'node:test'
import assert from 'node:assert/strict'
import {mkdtemp,mkdir,writeFile,readFile,readdir,rm,symlink,link,stat} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {randomBytes,createCipheriv,createHash} from 'node:crypto'
import {packRecovery,unpackRecovery,RecoveryError} from '../../priv/operations/recovery-bundle.mjs'
const candidate='a'.repeat(40)
const metadata=()=>({candidate,postgres:'18.4',recovery_point:new Date().toISOString(),migrations:['20261008172326']})
async function fixture(t){
  const root=await mkdtemp(join(tmpdir(),'gitgood-recovery-test-'))
  t.after(()=>rm(root,{recursive:true,force:true}))
  const roots={git:join(root,'git'),ssh:join(root,'ssh'),configuration:join(root,'configuration'),'database.dump':join(root,'database.dump')}
  for(const name of ['git','ssh','configuration'])await mkdir(roots[name],{mode:0o700})
  await mkdir(join(roots.git,'opaque.git'),{mode:0o700})
  await writeFile(join(roots.git,'opaque.git','objects.pack'),randomBytes(1048576))
  await writeFile(join(roots.git,'empty'),Buffer.alloc(0))
  await writeFile(join(roots.ssh,'ssh_host_ed25519_key'),'synthetic-host-identity')
  await writeFile(join(roots.configuration,'installation.json'),JSON.stringify({fixture:'synthetic-configuration-value'}))
  await writeFile(roots['database.dump'],Buffer.concat([Buffer.from('PGDMP'),randomBytes(4096)]))
  return {root,roots,key:randomBytes(32),destination:join(root,'backup.ggbackup')}
}
const refuse=async promise=>assert.rejects(promise,error=>error instanceof RecoveryError)
async function malformed(file,key,manifest,contents=Buffer.alloc(0)){
  const header=Buffer.concat([Buffer.from('GitgoodRecovery1\n'),randomBytes(12)])
  const json=Buffer.from(JSON.stringify(manifest)),size=Buffer.alloc(4);size.writeUInt32BE(json.length)
  const plain=Buffer.concat([Buffer.from('GGpack01'),size,json,contents])
  const cipher=createCipheriv('aes-256-gcm',key,header.subarray(header.length-12));cipher.setAAD(header)
  await writeFile(file,Buffer.concat([header,cipher.update(plain),cipher.final(),cipher.getAuthTag()]))
}

// These tests exercise the actual encrypted file boundary; no stream, crypto or filesystem mocks.
test('authenticated bundle preserves exact stores and owner-only files',async t=>{
  const f=await fixture(t),receipt=await packRecovery({...f,metadata:metadata()})
  const restored=await unpackRecovery({source:f.destination,key:f.key,target:join(f.root,'verified'),expectedCandidate:candidate})
  assert.equal(receipt.candidate,candidate)
  for(const path of ['git/opaque.git/objects.pack','git/empty','ssh/ssh_host_ed25519_key','configuration/installation.json','database.dump']){
    assert.deepEqual(await readFile(join(restored.verified_directory,path)),await readFile(join(f.root,path)))
    if(process.platform==='linux')assert.equal((await stat(join(restored.verified_directory,path))).mode&0o777,0o600)
  }
  assert.equal(restored.ciphertext_sha256,receipt.ciphertext_sha256)
  assert(! (await readFile(f.destination)).includes(Buffer.from('synthetic-configuration-value')))
})

test('wrong key, altered ciphertext and truncation never publish plaintext',async t=>{
  const f=await fixture(t);await packRecovery({...f,metadata:metadata()})
  const before=(await readdir(f.root)).sort(),original=await readFile(f.destination)
  await refuse(unpackRecovery({source:f.destination,key:randomBytes(32),target:join(f.root,'wrong-key')}))
  const altered=Buffer.from(original);altered[100]^=1;await writeFile(join(f.root,'altered'),altered)
  await refuse(unpackRecovery({source:join(f.root,'altered'),key:f.key,target:join(f.root,'corrupt')}))
  await writeFile(join(f.root,'truncated'),original.subarray(0,original.length-3))
  await refuse(unpackRecovery({source:join(f.root,'truncated'),key:f.key,target:join(f.root,'short')}))
  assert.deepEqual((await readdir(f.root)).filter(x=>!['altered','truncated'].includes(x)).sort(),before)
})

test('candidate and database compatibility refuse before destination creation',async t=>{
  const f=await fixture(t);await packRecovery({...f,metadata:metadata()})
  await refuse(unpackRecovery({source:f.destination,key:f.key,target:join(f.root,'other-candidate'),expectedCandidate:'b'.repeat(40)}))
  await refuse(unpackRecovery({source:f.destination,key:f.key,target:join(f.root,'other-postgres'),expectedPostgres:'18.5'}))
  assert(!(await readdir(f.root)).some(x=>x.startsWith('.gitgood-verified-')||x.startsWith('other-')))
})

test('authenticated hostile inventories reject traversal, duplicates, missing stores, digest changes and trailing bytes',async t=>{
  const f=await fixture(t);await packRecovery({...f,metadata:metadata()})
  const good=await unpackRecovery({source:f.destination,key:f.key,target:join(f.root,'baseline')})
  const contents=Buffer.concat(await Promise.all(good.manifest.entries.filter(e=>e.type==='file').map(e=>readFile(join(f.root,e.path)))))
  const cases=[
    m=>{m.entries.find(e=>e.path==='git/empty').path='git/../escape'},
    m=>{m.entries.push({...m.entries.at(-1)})},
    m=>{m.entries=m.entries.filter(e=>e.path!=='ssh/ssh_host_ed25519_key')},
    m=>{m.entries.find(e=>e.path==='git/opaque.git/objects.pack').sha256='0'.repeat(64)},
    m=>{m.entries.find(e=>e.path==='git/empty').bytes=17179869185}
  ]
  for(let i=0;i<cases.length;i++){
    const manifest=structuredClone(good.manifest);cases[i](manifest)
    const file=join(f.root,'hostile-'+i);await malformed(file,f.key,manifest,contents)
    await refuse(unpackRecovery({source:file,key:f.key,target:join(f.root,'unsafe-'+i)}))
  }
  const extra=join(f.root,'extra');await malformed(extra,f.key,good.manifest,Buffer.concat([contents,Buffer.from('extra')]))
  await refuse(unpackRecovery({source:extra,key:f.key,target:join(f.root,'unsafe-extra')}))
  assert(!(await readdir(f.root)).some(x=>x==='escape'||x.startsWith('unsafe-')||x.startsWith('.gitgood-verified-')))
})

test('existing file and directory destinations remain intact',async t=>{
  const f=await fixture(t);await writeFile(f.destination,'existing-private-file')
  await refuse(packRecovery({...f,metadata:metadata()}));assert.equal(await readFile(f.destination,'utf8'),'existing-private-file')
  const bundle=join(f.root,'new-bundle');await packRecovery({...f,destination:bundle,metadata:metadata()})
  const target=join(f.root,'existing');await mkdir(target);await writeFile(join(target,'sentinel'),'unrelated')
  await refuse(unpackRecovery({source:bundle,key:f.key,target}));assert.equal(await readFile(join(target,'sentinel'),'utf8'),'unrelated')
})

test('failed final quiescence check leaves no published or partial backup',async t=>{
  const f=await fixture(t)
  await refuse(packRecovery({...f,metadata:metadata(),beforePublish:async()=>{throw new RecoveryError('installation_not_quiescent')}}))
  assert(!(await readdir(f.root)).some(x=>x==='backup.ggbackup'||x.endsWith('.partial')))
})

test('concurrent backup publication selects one complete bundle without overwriting',async t=>{
  const f=await fixture(t),other=randomBytes(32)
  const results=await Promise.allSettled([packRecovery({...f,metadata:metadata()}),packRecovery({...f,key:other,metadata:metadata()})])
  assert.equal(results.filter(x=>x.status==='fulfilled').length,1)
  const winner=results[0].status==='fulfilled'?f.key:other
  await unpackRecovery({source:f.destination,key:winner,target:join(f.root,'winner')})
  assert(!(await readdir(f.root)).some(x=>x.endsWith('.partial')))
})

test('symlink and hard-linked source files cannot escape the declared inventory',async t=>{
  const f=await fixture(t),outside=join(f.root,'outside');await writeFile(outside,'unrelated')
  await symlink(outside,join(f.roots.git,'link'))
  await refuse(packRecovery({...f,metadata:metadata()}));await rm(join(f.roots.git,'link'))
  await link(outside,join(f.roots.git,'hardlink'))
  await refuse(packRecovery({...f,metadata:metadata()}))
  assert.equal(await readFile(outside,'utf8'),'unrelated')
})
