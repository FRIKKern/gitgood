import {load, validate, freshness, classify, releaseProblems} from './model.mjs'
const m=load(), now=new Date(), errors=validate(m,now)
if(errors.length){console.error(errors.join('\n'));process.exitCode=1}
else {
  console.log('Gitgood reporting baseline: '+m.snapshot.baseline)
  console.log('Candidate commit: '+(m.snapshot.headCommit??'not implemented'))
  for(const name of ['ledger','evidence','releases'])console.log(name+': '+freshness(m.snapshot,name,now))
  for(const j of m.catalog.journeys) {
    const s=classify(m.snapshot.records.find(r=>r.id===j.id),m.snapshot,now)
    console.log(j.id+' | implementation '+s.implementation+' | verification '+s.verification+' | release '+s.release)
  }
  if(process.argv.includes('--release')){
    const failures=releaseProblems(m,now)
    if(failures.length){console.error('Release acceptance refused:\n'+failures.join('\n'));process.exitCode=2}
  }
  if(process.argv.includes('--freshness')&&['ledger','evidence','releases'].some(n=>freshness(m.snapshot,n,now)!=='current')){
    console.error('Freshness unavailable or expired. Configure source reconciliation before enabling scheduled maintenance.')
    process.exitCode=2
  }
}
