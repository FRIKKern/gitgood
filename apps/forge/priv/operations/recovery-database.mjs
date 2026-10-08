import {spawn} from 'node:child_process'
import {createHash} from 'node:crypto'
import {RecoveryError} from './recovery-bundle.mjs'
import {normalizeSchemaLine} from './recovery-schema.mjs'
import {StringDecoder} from 'node:string_decoder'
const executables={psql:process.env.GITGOOD_PSQL??'psql',dump:process.env.GITGOOD_PG_DUMP??'pg_dump',restore:process.env.GITGOOD_PG_RESTORE??'pg_restore'}
const identifier=name=>{if(typeof name!=='string'||!/^[a-z][a-z0-9_]{0,62}$/.test(name))throw new RecoveryError('database_inventory_invalid');return '"'+name+'"'}
const environment=()=>({...process.env,PGAPPNAME:'gitgood offline recovery v1',PGCONNECT_TIMEOUT:'5',
  PGOPTIONS:'-c timezone=UTC -c datestyle=ISO,YMD -c bytea_output=hex -c extra_float_digits=3'})
async function command(executable,args,{hash=false,normalizeSchema=false,deadline=300000}={}){
  const child=spawn(executable,args,{env:environment(),stdio:['ignore','pipe','pipe'],windowsHide:true})
  const digest=createHash('sha256'),chunks=[],decoder=new StringDecoder('utf8');let bytes=0,line='',failed=false,killTimer
  const terminate=()=>{if(failed)return;failed=true;child.kill('SIGTERM');killTimer=setTimeout(()=>child.kill('SIGKILL'),1000)}
  const timer=setTimeout(terminate,deadline)
  child.stdout.on('data',chunk=>{
    bytes+=chunk.length
    if(!hash){if(bytes>1048576)terminate();else chunks.push(chunk)}
    else if(!normalizeSchema)digest.update(chunk)
    else{
      line+=decoder.write(chunk);const lines=line.split('\n');line=lines.pop()
      if(Buffer.byteLength(line)>1048576)terminate()
      for(const value of lines)if(!/^\\(?:un)?restrict [A-Za-z0-9]+$/.test(value))digest.update(normalizeSchemaLine(value)+'\n')
    }
  })
  // Drain privately. Native command errors never print arguments, database content or credentials.
  child.stderr.resume()
  await new Promise((resolve,reject)=>{
    child.once('error',()=>reject(new RecoveryError('database_tool_failed')))
    child.once('close',code=>code===0&&!failed?resolve():reject(new RecoveryError('database_tool_failed')))
  }).finally(()=>{clearTimeout(timer);clearTimeout(killTimer)})
  if(hash&&normalizeSchema){line+=decoder.end();if(line&&!/^\\(?:un)?restrict [A-Za-z0-9]+$/.test(line))digest.update(normalizeSchemaLine(line))}
  return hash?digest.digest('hex'):Buffer.concat(chunks).toString('utf8').trim()
}
export const query=sql=>command(executables.psql,['--no-psqlrc','--tuples-only','--no-align','--set','ON_ERROR_STOP=1','--command',sql])
export async function assertDatabaseTools(version){
  for(const [tool,name] of [[executables.dump,'pg_dump'],[executables.restore,'pg_restore']]){
    if(await command(tool,['--version'])!==name+' (PostgreSQL) '+version)throw new RecoveryError('database_version_incompatible')
  }
  if(await query('SHOW server_version')!==version)throw new RecoveryError('database_version_incompatible')
}
export async function databaseProfile(){
  const profile=JSON.parse(await query(`SELECT json_build_object(
    'encoding',pg_encoding_to_char(encoding),'provider',datlocprovider,
    'collate',datcollate,'ctype',datctype,'locale',datlocale,
    'collation_version',datcollversion,
    'actual_collation_version',pg_database_collation_actual_version(oid))
    FROM pg_database WHERE datname=current_database()`))
  // This operational profile requires native PostgreSQL in the same OS. libc also governs
  // case conversion when a C collation has no catalog version to compare.
  profile.libc=await command('/usr/bin/getconf',['GNU_LIBC_VERSION'])
  if(!/^glibc [0-9]+\.[0-9]+$/.test(profile.libc)||profile.collation_version!==profile.actual_collation_version)
    throw new RecoveryError('database_locale_incompatible')
  return profile
}
export async function assertDatabaseProfile(expected){
  if(JSON.stringify(await databaseProfile())!==JSON.stringify(expected))throw new RecoveryError('database_locale_incompatible')
}
export async function assertLease(context){
  if(!Number.isInteger(context.backend_pid)||context.backend_pid<=0)throw new RecoveryError('installation_not_quiescent')
  const sql='SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype=\'advisory\' AND pid='+context.backend_pid+
    ' AND classid::bigint=1197034575 AND objid::bigint=1 AND objsubid=2 AND mode=\'ExclusiveLock\' AND granted) AND NOT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND backend_type=\'client backend\' AND pid NOT IN (pg_backend_pid(),'+context.backend_pid+'))'
  if(await query(sql)!=='t')throw new RecoveryError('installation_not_quiescent')
}
export async function fingerprintDatabase(){
  const tables=JSON.parse(await query(`SELECT coalesce(json_agg(json_build_object('table',c.relname,'keys',(
    SELECT json_agg(a.attname ORDER BY u.ordinality) FROM pg_constraint p
    CROSS JOIN LATERAL unnest(p.conkey) WITH ORDINALITY u(attnum,ordinality)
    JOIN pg_attribute a ON a.attrelid=p.conrelid AND a.attnum=u.attnum
    WHERE p.conrelid=c.oid AND p.contype='p')) ORDER BY c.relname),'[]'::json)
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relkind IN ('r','p')`))
  if(!Array.isArray(tables)||tables.length>1000)throw new RecoveryError('database_inventory_invalid')
  const rows=[]
  for(const table of tables){
    if(!Array.isArray(table.keys)||table.keys.length===0||table.keys.length>64)throw new RecoveryError('database_inventory_invalid')
    const name=identifier(table.table),order=table.keys.map(identifier).join(',')
    const sql='COPY (SELECT to_jsonb(t)::text FROM public.'+name+' t ORDER BY '+order+') TO STDOUT'
    const sha256=await command(executables.psql,['--no-psqlrc','--tuples-only','--no-align','--set','ON_ERROR_STOP=1','--command',sql],{hash:true})
    rows.push({table:table.table,keys:table.keys,sha256})
  }
  const sequences=await query(`SELECT coalesce(json_agg(json_build_object('name',sequencename,
    'start',start_value,'min',min_value,'max',max_value,'increment',increment_by,
    'cycle',cycle,'cache',cache_size,'last',last_value) ORDER BY sequencename),'[]'::json)
    FROM pg_sequences WHERE schemaname='public'`)
  const schema_sha256=await command(executables.dump,['--schema-only','--no-owner','--no-privileges','--no-comments'],{hash:true,normalizeSchema:true})
  return {profile:await databaseProfile(),schema_sha256,tables:rows,sequences:JSON.parse(sequences)}
}
export const dumpDatabase=file=>command(executables.dump,['--format=custom','--no-owner','--no-privileges','--file',file],{deadline:600000})
export const restoreDatabase=file=>command(executables.restore,['--single-transaction','--exit-on-error','--no-owner','--no-privileges','--dbname',process.env.PGDATABASE,file],{deadline:600000})
