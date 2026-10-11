import fs from 'node:fs'
import path from 'node:path'
import {load, read, root, validate} from './model.mjs'
import {svg, journeySvg, overviewSvg, roadmap, index, status, changelog} from './render.mjs'
export function generated(m) {
  const changes = changelog(m)
  const readme = read('README.md').replace(/<!-- whats-new:start -->[\s\S]*?<!-- whats-new:end -->/, '<!-- whats-new:start -->\n'+changes.highlights+'\n<!-- whats-new:end -->')
  return {'README.md':readme,'JOURNEYS.md':index(m),'docs/ROADMAP.md':roadmap(m),'docs/STATUS.md':status(m),'docs/images/overview.svg':overviewSvg(m),'docs/images/roadmap.svg':svg(m),'docs/images/journey-evidence.svg':journeySvg(m),'CHANGELOG.md':changes.body}
}
if (process.argv[1] && path.resolve(process.argv[1]) === path.join(root,'scripts/generate.mjs')) {
  const m=load(), errors=validate(m)
  if(errors.length) { console.error(errors.join('\n')); process.exitCode=1 }
  else for(const [name,body] of Object.entries(generated(m))) {
    const filename=path.join(root,name)
    fs.mkdirSync(path.dirname(filename),{recursive:true})
    if(!fs.existsSync(filename)||fs.readFileSync(filename,'utf8')!==body) {
      fs.writeFileSync(filename,body)
      console.log('Generated '+name)
    }
  }
}
