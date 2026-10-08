import test from 'node:test'
import assert from 'node:assert/strict'
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {inspectRepositories,rebindRepositories} from '../../priv/operations/recovery-git.mjs'
import {RecoveryError} from '../../priv/operations/recovery-bundle.mjs'
const command=promisify(execFile),storage_key='d5e74fd0-1bcb-49d9-bf37-e3a0b69325c2'
async function fixture(t){
  const root=await mkdtemp(join(tmpdir(),'gitgood-recovery-git-')),path=join(root,storage_key+'.git')
  t.after(()=>rm(root,{recursive:true,force:true}))
  const git=args=>command(process.env.GITGOOD_GIT??'git',args,{maxBuffer:1048576})
  await git(['init','--bare','--template=','--object-format=sha1','--initial-branch=main',path])
  for(const [name,value] of [['receive.fsckObjects','true'],['transfer.fsckObjects','true'],['receive.denyNonFastForwards','true'],
    ['receive.denyDeletes','true'],['receive.maxInputSize','33554432'],['http.getanyfile','false'],['http.maxRequestBuffer','33554432'],
    ['transfer.hideRefs','refs/gitgood/'],['core.hooksPath',join(path,'hooks')]])await git(['--git-dir',path,'config',name,value])
  await mkdir(join(path,'hooks'),{recursive:true})
  await writeFile(join(path,'hooks/pre-receive'),'old-hook',{mode:0o700})
  return {root,path,git,rows:[{storage_key,status:'ready'}]}
}
test('real native bare repository passes and hook rebinding preserves refs',async t=>{
  const f=await fixture(t),before=await inspectRepositories(f.root,f.rows)
  assert.equal(before[0].refs,'')
  await rebindRepositories(f.root,join(f.root,'replacement'),before)
  assert.deepEqual(await inspectRepositories(f.root,f.rows),before)
  assert.equal((await f.git(['--git-dir',f.path,'config','core.hooksPath'])).stdout.trim(),join(f.root,'replacement',storage_key+'.git/hooks'))
  assert((await readFile(join(f.path,'hooks/pre-receive'),'utf8')).includes('GITGOOD_HOOK_SCRIPT'))
})
test('missing ready storage refuses while unfinished missing storage remains explicit',async t=>{
  const f=await fixture(t)
  await rm(f.path,{recursive:true})
  await assert.rejects(inspectRepositories(f.root,f.rows),RecoveryError)
  assert.deepEqual(await inspectRepositories(f.root,[{storage_key,status:'creating'}]),[{storage_key,status:'creating',refs:null}])
})
test('external object dependencies and unsupported Git configuration refuse',async t=>{
  const f=await fixture(t)
  await writeFile(join(f.path,'objects/info/alternates'),'/outside-owned-store\n')
  await assert.rejects(inspectRepositories(f.root,f.rows),RecoveryError)
  await rm(join(f.path,'objects/info/alternates'))
  await f.git(['--git-dir',f.path,'config','include.path','/outside-owned-config'])
  await assert.rejects(inspectRepositories(f.root,f.rows),RecoveryError)
})
test('real fsck refuses a corrupt referenced object',async t=>{
  const f=await fixture(t)
  await mkdir(join(f.path,'objects/aa'))
  await writeFile(join(f.path,'objects/aa','a'.repeat(38)),'not-a-git-object')
  await assert.rejects(inspectRepositories(f.root,f.rows),RecoveryError)
})
