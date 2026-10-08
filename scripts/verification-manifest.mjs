import {spawnSync} from 'node:child_process'
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs'
import {createHash} from 'node:crypto'
const read = (exe, args) => {
  const result = spawnSync(exe, args, {encoding:'utf8',timeout:15000})
  return result.status === 0 ? result.stdout.trim() : 'unavailable'
}
const journeys = ['J01','J02','J03','J04','J05','J06','J07','J08','J09','J12','J13']
const manifest = {
  candidate: read(process.env.GITGOOD_GIT ?? 'git', ['rev-parse','HEAD']),
  trackedWorktreeClean: read(process.env.GITGOOD_GIT ?? 'git', ['status','--porcelain','--untracked-files=no']) === '',
  requirements: Object.fromEntries(journeys.map(id => [id, createHash('sha256').update(readFileSync('docs/journeys/'+id+'.md')).digest('hex')])),
  recordedAt:new Date().toISOString(),
  environment:{platform:process.platform, architecture:process.arch, node:process.version,
    git:read(process.env.GITGOOD_GIT ?? 'git',['--version']),
    python:read(process.env.GITGOOD_PYTHON ?? 'python3',['--version'])},
  run:{id:process.env.GITHUB_RUN_ID ?? null, attempt:process.env.GITHUB_RUN_ATTEMPT ?? null,
    revision:process.env.GITHUB_SHA ?? null, actor:process.env.GITHUB_ACTOR ?? 'local Codex development run'},
  commands:['mix precommit','mix format --check-formatted','npm run check (apps/web)','npx playwright test'],
  results:'See test result artifacts and CI job conclusions; this manifest alone is not verification.',
}
mkdirSync('apps/web/test-results',{recursive:true})
writeFileSync('apps/web/test-results/verification-manifest.json',JSON.stringify(manifest,null,2)+'\n')
