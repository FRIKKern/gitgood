import fs from 'node:fs'
import path from 'node:path'
import {load, read, root, validate} from './model.mjs'
import {generated} from './generate.mjs'
import {documentationProblems} from './documentation.mjs'
const m=load(), errors=validate(m)
function walk(dir) {
  return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>{
    if(['.git','.gitgood','node_modules','work','deps','_build','.output','dist','.tanstack'].includes(e.name))return []
    const p=path.join(dir,e.name)
    return e.isDirectory()?walk(p):[p]
  })
}
for(const j of m.catalog.journeys) {
  const p=path.join(root,j.spec)
  if(!fs.existsSync(p)) {errors.push('Missing spec: '+j.spec);continue}
  const doc=read(j.spec)
  for(const suffix of ['A','B','C']) if(!doc.includes('**'+j.id+'-'+suffix+':**'))errors.push('Missing acceptance criterion: '+j.id+'-'+suffix)
}
const files = walk(root)
errors.push(...documentationProblems(files.map(file => path.relative(root, file)), read))
for(const f of files.filter(p=>p.endsWith('.md'))) {
  const body=fs.readFileSync(f,'utf8')
  for(const [,url] of body.matchAll(/!?\[[^\]]*\]\(([^)]+)\)/g)) {
    if(/^(https?:|mailto:|#)/.test(url))continue
    const target=decodeURIComponent(url.split('#')[0])
    const resolved=path.resolve(path.dirname(f),target)
    if(!resolved.startsWith(root) || !fs.existsSync(resolved))errors.push('Broken local link: '+path.relative(root,f)+' -> '+url)
  }
}
for(const f of m.fragments) for(const ref of f.references??[]) {
  if(/^https:\/\//.test(ref))continue
  if(!fs.existsSync(path.join(root,ref)))errors.push('Missing fragment reference: '+ref)
}
if(!errors.length) for(const [name,expected] of Object.entries(generated(m))) {
  if(!fs.existsSync(path.join(root,name))||read(name)!==expected) errors.push('Generated drift: '+name+'; run npm run generate')
}
if(errors.length) {console.error(errors.map(e=>'FAIL '+e).join('\n'));process.exitCode=1}
else console.log('PASS: catalogs, criteria, links, documentation indexes, snapshot, changelog, and generated outputs')
