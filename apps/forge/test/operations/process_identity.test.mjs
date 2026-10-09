import test from 'node:test'
import assert from 'node:assert/strict'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {mkdtemp,writeFile,rm} from 'node:fs/promises'
import {tmpdir,hostname} from 'node:os'
import {join} from 'node:path'
import {fileURLToPath} from 'node:url'
const exec=promisify(execFile),python=process.env.GITGOOD_PYTHON??(process.platform==='win32'?'python':'python3')
const operations=fileURLToPath(new URL('../../priv/operations/',import.meta.url))
test('kernel creation identity distinguishes a live owner from another PID lifetime',async t=>{
  const root=await mkdtemp(join(tmpdir(),'gitgood-process-identity-'));t.after(()=>rm(root,{recursive:true,force:true}))
  const born=(await exec(python,['-I',join(operations,'process_birth.py'),String(process.pid)])).stdout.trim()
  assert(/^[1-9][0-9]{0,19}$/.test(born))
  const marker=join(root,'marker.json'),record={protocol:1,host:hostname(),owners:[process.pid],owner_births:{[process.pid]:born}}
  await writeFile(marker,JSON.stringify(record),{mode:0o600})
  await assert.rejects(exec(python,['-I',join(operations,'process_status.py'),marker]),error=>error.stdout.trim()==='busy')
  record.owner_births[process.pid]=(BigInt(born)+1n).toString()
  await writeFile(marker,JSON.stringify(record))
  assert.equal((await exec(python,['-I',join(operations,'process_status.py'),marker])).stdout.trim(),'clear')
  record.owner_births[process.pid]=123
  await writeFile(marker,JSON.stringify(record))
  await assert.rejects(exec(python,['-I',join(operations,'process_status.py'),marker]),error=>error.stdout.trim()==='invalid')
})
test('legacy PID-only records conservatively refuse the live owner',async t=>{
  const root=await mkdtemp(join(tmpdir(),'gitgood-process-legacy-'));t.after(()=>rm(root,{recursive:true,force:true}))
  const marker=join(root,'marker.json')
  await writeFile(marker,JSON.stringify({protocol:1,host:hostname(),owners:[process.pid]}),{mode:0o600})
  await assert.rejects(exec(python,['-I',join(operations,'process_status.py'),marker]),error=>error.stdout.trim()==='busy')
})
