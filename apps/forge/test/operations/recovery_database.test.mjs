import test from 'node:test'
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
import {randomBytes} from 'node:crypto'
import {databaseProfile,assertDatabaseProfile,fingerprintDatabase,query} from '../../priv/operations/recovery-database.mjs'

// Requires the explicitly provisioned PostgreSQL 18.4 operational profile.
test('equal stored rows and DDL cannot hide different native text semantics',
  {skip:process.env.GITGOOD_TEST_DATABASE_LOCALE!=='true'},async t=>{
    const prior=process.env.PGDATABASE,databases=[]
    const tool=(name,args)=>{
      const child=spawnSync(name,args,{env:process.env,encoding:'utf8'})
      assert.equal(child.status,0,'Owned database fixture command failed')
    }
    t.after(()=>{
      if(prior===undefined)delete process.env.PGDATABASE;else process.env.PGDATABASE=prior
      for(const name of databases)tool('dropdb',[name])
    })
    const fixtures=[]
    for(const locale of ['C.UTF-8','C']){
      const name='gitgood_locale_test_'+randomBytes(6).toString('hex')
      tool('createdb',['--template=template0','--encoding=UTF8','--locale='+locale,'--locale-provider=libc',name]);databases.push(name)
      process.env.PGDATABASE=name
      await query("CREATE TABLE public.locale_fixture (id integer PRIMARY KEY, value text NOT NULL); INSERT INTO public.locale_fixture VALUES (1,'ASCII fixture');")
      const fingerprint=await fingerprintDatabase(),profile=await databaseProfile()
      await assertDatabaseProfile(profile)
      fixtures.push({fingerprint,profile,lowercase:await query("SELECT lower(U&'\\00C4')")})
    }
    const {profile:firstProfile,...firstStores}=fixtures[0].fingerprint
    const {profile:secondProfile,...secondStores}=fixtures[1].fingerprint
    assert.deepEqual(firstStores,secondStores)
    assert.notEqual(fixtures[0].lowercase,fixtures[1].lowercase)
    assert.notDeepEqual(firstProfile,secondProfile)
    await assert.rejects(assertDatabaseProfile(firstProfile),error=>error.code==='database_locale_incompatible')
    for(const expected of [undefined,{...secondProfile,encoding:'LATIN1'},
      {...secondProfile,provider:'i'},{...secondProfile,collation_version:'foreign'},
      {...secondProfile,libc:'glibc 0.0'}]){
      await assert.rejects(assertDatabaseProfile(expected),error=>error.code==='database_locale_incompatible')
    }
  })
