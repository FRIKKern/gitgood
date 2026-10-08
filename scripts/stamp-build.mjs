import {spawnSync} from 'node:child_process'
import {readFileSync,writeFileSync,readdirSync,mkdirSync} from 'node:fs'
import {createHash} from 'node:crypto'
const git = process.env.GITGOOD_GIT ?? 'git'
function command(args) {const result=spawnSync(git,args,{encoding:'utf8'});if(result.status!==0)throw new Error('Cannot identify candidate');return result.stdout.trim()}
const digest=path=>createHash('sha256').update(readFileSync(path)).digest('hex')
const identity={schema:1,candidate:command(['rev-parse','HEAD']),dirty:command(['status','--porcelain','--untracked-files=all'])!=='',
  built_at:new Date().toISOString(),requirements:Object.fromEntries(readdirSync('docs/journeys').filter(n=>/^J\d+\.md$/.test(n)).map(n=>[n.slice(0,-3),digest('docs/journeys/'+n)])),
  locks:{forge:digest('apps/forge/mix.lock'),web:digest('apps/web/package-lock.json'),toolchain:digest('.tool-versions')},
  migrations:readdirSync('apps/forge/priv/repo/migrations').filter(n=>/^\d+_.*\.exs$/.test(n)).map(n=>n.split('_')[0]).sort()}
mkdirSync('apps/web/dist',{recursive:true})
writeFileSync('apps/web/dist/build-identity.json',JSON.stringify(identity,null,2)+'\n')
writeFileSync('apps/forge/priv/build-identity.json',JSON.stringify(identity,null,2)+'\n')
console.log('Stamped candidate '+identity.candidate+'; dirty='+identity.dirty)
