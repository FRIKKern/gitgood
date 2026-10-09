import test from 'node:test'
import assert from 'node:assert/strict'
import {mkdtemp,mkdir,writeFile,readFile,readdir,rm,chmod} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {randomBytes,randomUUID} from 'node:crypto'
import {spawnSync} from 'node:child_process'
import {packRecovery} from '../../priv/operations/recovery-bundle.mjs'
import {provisionConfiguration} from '../../priv/operations/recovery-configuration.mjs'
import {fingerprintDatabase,dumpDatabase,query} from '../../priv/operations/recovery-database.mjs'
import {inspectInstallationExport} from '../../priv/operations/installation-export.mjs'

test('installation export inspects real Git and a real database dump without changing either store',
  {skip:process.env.GITGOOD_TEST_DATABASE_LOCALE!=='true'},async t=>{
    const root=await mkdtemp(join(tmpdir(),'gitgood-export-test-')),prior=process.env.PGDATABASE
    const database='gitgood_export_test_'+randomBytes(6).toString('hex'),candidate='a'.repeat(40)
    const command=(tool,args,input)=>{
      const result=spawnSync(tool,args,{env:process.env,input,encoding:'utf8'})
      assert.equal(result.status,0,'Owned export fixture command failed');return result.stdout.trim()
    }
    command('createdb',['--template=template0','--encoding=UTF8','--locale=C.UTF-8','--locale-provider=libc',database])
    t.after(async()=>{if(prior===undefined)delete process.env.PGDATABASE;else process.env.PGDATABASE=prior;command('dropdb',[database]);await rm(root,{recursive:true,force:true})})
    process.env.PGDATABASE=database
    await query("CREATE TABLE public.export_fixture(id integer PRIMARY KEY, value text NOT NULL); INSERT INTO public.export_fixture VALUES (1,'private collaboration fixture')")
    const git=join(root,'git'),ssh=join(root,'ssh'),configuration=join(root,'configuration'),scratch=join(root,'scratch')
    for(const path of [git,ssh,scratch])await mkdir(path,{mode:0o700})
    const storage_key=randomUUID(),repository=join(git,storage_key+'.git'),gitTool=process.env.GITGOOD_GIT??'git'
    command(gitTool,['init','--bare','--template=',repository])
    const gitCall=(args,input)=>command(gitTool,['--git-dir',repository,...args],input)
    for(const [name,value] of Object.entries({'receive.fsckObjects':'true','transfer.fsckObjects':'true','receive.denyNonFastForwards':'true','receive.denyDeletes':'true','receive.maxInputSize':'33554432','http.getAnyFile':'false','http.maxRequestBuffer':'33554432'}))gitCall(['config',name,value])
    const tree=gitCall(['hash-object','-w','-t','tree','--stdin'],'')
    const sha=gitCall(['-c','user.name=Export fixture','-c','user.email=export@example.invalid','commit-tree',tree], 'Export fixture\n')
    gitCall(['update-ref','refs/heads/main',sha])
    const refs=gitCall(['for-each-ref','--format=%(refname) %(objectname)'])
    const certificate=join(root,'certificate'),tlsKey=join(root,'tls-key')
    for(const path of [certificate,tlsKey])await writeFile(path,'synthetic private fixture',{mode:0o600})
    await writeFile(join(ssh,'ssh_host_ed25519_key'),'synthetic private host material',{mode:0o600})
    const proxy=randomBytes(32).toString('base64')
    const installation=await provisionConfiguration({directory:configuration,certificate,tlsKey,
      forge:{DATABASE_URL:'postgresql://fixture@127.0.0.1/'+database,SECRET_KEY_BASE:randomBytes(64).toString('base64'),PHX_HOST:'localhost',GITGOOD_PUBLIC_URL:'https://localhost',GITGOOD_WEB_ORIGIN:'https://localhost',GITGOOD_PROXY_KEY:proxy,GITGOOD_STORAGE:git,PORT:'49991',GITGOOD_SSH_PORT:'49992',GITGOOD_SSH_HOST_KEY_DIRECTORY:ssh,GITGOOD_SSH_PUBLIC_HOST:'localhost',GITGOOD_SSH_PUBLIC_PORT:'49992'},
      web:{PORT:'49990',GITGOOD_API_URL:'http://127.0.0.1:49991',GITGOOD_PROXY_KEY:proxy,NODE_ENV:'production'}})
    const before=await fingerprintDatabase(),descriptor={protocol:1,installation,database:structuredClone(before),repositories:[{storage_key,status:'ready',refs}],interrupted_git_locks:[]}
    await writeFile(join(configuration,'recovery.json'),JSON.stringify(descriptor),{mode:0o600})
    const dump=join(root,'database.dump');await dumpDatabase(dump)
    const key=randomBytes(32),keyPath=join(root,'external-key'),source=join(root,'export.ggbackup')
    await writeFile(keyPath,key,{mode:0o600})
    const metadata={candidate,postgres:'18.4',recovery_point:new Date().toISOString(),migrations:[]}
    const roots={git,ssh,configuration,'database.dump':dump}
    await packRecovery({destination:source,key,metadata,roots})
    const options={source,keyPath,scratchDirectory:scratch,expectedCandidate:candidate,expectedInstallation:installation}
    await writeFile(join(scratch,'unrelated'),'retain unrelated private entry',{mode:0o600})
    const receipt=await inspectInstallationExport(options)
    assert.equal(receipt.repositories,1);assert.equal(receipt.tables,1);assert.equal(receipt.checks.length,4)
    assert.equal(receipt.installation,installation)
    assert(!JSON.stringify(receipt).includes('private collaboration fixture'))
    assert.deepEqual(await fingerprintDatabase(),before);assert.equal(gitCall(['for-each-ref','--format=%(refname) %(objectname)']),refs)
    for(const invalid of [{expectedCandidate:'b'.repeat(40)},{expectedInstallation:randomUUID()},{expectedInstallation:'../foreign'},{keyPath:join(root,'wrong-key')},{source:join(root,'corrupt')}]){
      if(invalid.keyPath)await writeFile(invalid.keyPath,randomBytes(32),{mode:0o600})
      if(invalid.source){const bytes=await readFile(source);bytes[100]^=1;await writeFile(invalid.source,bytes,{mode:0o600})}
      await assert.rejects(inspectInstallationExport({...options,...invalid}))
      assert.deepEqual(await readdir(scratch),['unrelated'])
    }
    descriptor.repositories[0].refs='refs/heads/main '+'0'.repeat(40)
    await writeFile(join(configuration,'recovery.json'),JSON.stringify(descriptor),{mode:0o600})
    const mismatch=join(root,'mismatched.ggbackup');await packRecovery({destination:mismatch,key,metadata,roots})
    await assert.rejects(inspectInstallationExport({...options,source:mismatch}))
    assert.deepEqual(await readdir(scratch),['unrelated'])
    descriptor.repositories[0].refs=refs
    descriptor.database.tables=[]
    await writeFile(join(configuration,'recovery.json'),JSON.stringify(descriptor),{mode:0o600})
    const wrongDump=join(root,'wrong-inventory.ggbackup');await packRecovery({destination:wrongDump,key,metadata,roots})
    await assert.rejects(inspectInstallationExport({...options,source:wrongDump}))
    assert.deepEqual(await readdir(scratch),['unrelated'])
    assert.equal(await readFile(join(scratch,'unrelated'),'utf8'),'retain unrelated private entry')
    await chmod(scratch,0o755);await assert.rejects(inspectInstallationExport(options));await chmod(scratch,0o700)
    assert.deepEqual(await fingerprintDatabase(),before)
  })
