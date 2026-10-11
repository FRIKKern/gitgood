import fs from 'node:fs'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {fileURLToPath} from 'node:url'

const directory = 'docs/media/web/'
const captureFile = directory + 'capture.json'
const requiredArtifacts = [
  '01-sign-in.png', '02-repositories.png', '03-code.png', '04-review.png',
  '05-releases.png', 'walkthrough.gif', 'walkthrough.webm', 'walkthrough.cast', 'walkthrough.txt'
].map(name => directory + name)
const digest = bytes => createHash('sha256').update(bytes).digest('hex')
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)

export function sourceFiles(root) {
  const walk = (relative, skipPythonCache = false) => {
    const entries = fs.readdirSync(path.join(root, relative), {withFileTypes: true})
    return entries.flatMap(entry => {
      if (skipPythonCache && entry.name === '__pycache__') return []
      const name = relative + '/' + entry.name
      if (entry.isSymbolicLink()) throw new Error('Tour source must not be a symbolic link: ' + name)
      if (entry.isDirectory()) return walk(name, skipPythonCache)
      if (!entry.isFile()) throw new Error('Tour source must be a regular file: ' + name)
      return [name]
    })
  }
  const ui = walk('apps/web/src'), capture = walk('apps/web/tour', true)
  if (!ui.length || !capture.length) throw new Error('Tour source directories must not be empty')
  return [...ui, ...capture, 'apps/web/package.json', 'apps/web/package-lock.json', 'apps/web/vite.config.ts'].sort()
}

export function sourceHashes(root) {
  // Git checks these text files out with either CRLF or LF. Capture identity must
  // describe their content consistently on Windows and Linux.
  return Object.fromEntries(sourceFiles(root).map(name => [name,
    digest(fs.readFileSync(path.join(root, name), 'utf8').replaceAll('\r\n', '\n'))]))
}

function mediaProblem(name, bytes) {
  if (!bytes.length) return 'empty file'
  if (name.endsWith('.png')) {
    if (bytes.length < 45 || !bytes.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex')) ||
        bytes.toString('ascii', 12, 16) !== 'IHDR' || bytes.readUInt32BE(16) === 0 || bytes.readUInt32BE(20) === 0 ||
        !bytes.subarray(-12).equals(Buffer.from('0000000049454e44ae426082', 'hex'))) return 'invalid PNG envelope'
  } else if (name.endsWith('.gif')) {
    if (bytes.length < 14 || !['GIF87a', 'GIF89a'].includes(bytes.toString('ascii', 0, 6)) ||
        bytes.readUInt16LE(6) === 0 || bytes.readUInt16LE(8) === 0 || bytes.at(-1) !== 0x3b) return 'invalid GIF envelope'
  } else if (name.endsWith('.webm')) {
    if (bytes.length < 8 || !bytes.subarray(0, 4).equals(Buffer.from('1a45dfa3', 'hex'))) return 'invalid WebM envelope'
  } else if (name.endsWith('.cast')) {
    try {
      const [header, ...events] = bytes.toString('utf8').trim().split('\n').map(line => JSON.parse(line))
      if (header.version !== 2 || !Number.isInteger(header.width) || header.width < 1 ||
          !Number.isInteger(header.height) || header.height < 1 || !events.length ||
          events.some(event => !Array.isArray(event) || event.length !== 3 || !Number.isFinite(event[0]) ||
            event[0] < 0 || !['o', 'i'].includes(event[1]) || typeof event[2] !== 'string')) return 'invalid asciicast recording'
    } catch { return 'invalid asciicast recording' }
  } else if (name.endsWith('.txt') && !bytes.toString('utf8').trim()) return 'empty transcript'
  return null
}

// This checks reproducibility and freshness of a synthetic frontend tour. It does
// not turn screenshots or matching hashes into backend or journey acceptance.
export function tourProblems(root) {
  const errors = []
  let manifest, current
  try { manifest = JSON.parse(fs.readFileSync(path.join(root, captureFile), 'utf8')) }
  catch { return ['Missing or invalid web tour manifest: ' + captureFile] }
  if (!record(manifest)) return ['Web tour manifest must be an object']
  if (manifest.schemaVersion !== 1 || manifest.kind !== 'frontend-with-synthetic-api') errors.push('Web tour must declare schemaVersion 1 and its synthetic frontend scope')
  if (manifest.sourceHashFormat !== 'sha256-utf8-lf') errors.push('Web tour sourceHashFormat must be sha256-utf8-lf')
  if (typeof manifest.capturedAt !== 'string' || !Number.isFinite(Date.parse(manifest.capturedAt))) errors.push('Web tour needs a valid capturedAt timestamp')
  if (typeof manifest.sourceCommit !== 'string' || !/^[a-f0-9]{40}$/.test(manifest.sourceCommit)) errors.push('Web tour needs its informational sourceCommit')
  if (!record(manifest.viewport) || !['width', 'height'].every(key => Number.isInteger(manifest.viewport[key]) && manifest.viewport[key] > 0)) errors.push('Web tour needs a positive integer viewport')
  try { current = sourceHashes(root) }
  catch (error) { errors.push('Cannot inspect web tour sources: ' + error.message) }
  if (!record(manifest.sources) || !Object.keys(manifest.sources).length) errors.push('Web tour source hashes must not be empty')
  else if (current) {
    for (const name of Object.keys(current)) {
      if (!(name in manifest.sources)) errors.push('Uncaptured web tour source: ' + name)
      else if (!hash(manifest.sources[name]) || current[name] !== manifest.sources[name]) errors.push('Stale web tour source: ' + name + '; recapture the tour')
    }
    for (const name of Object.keys(manifest.sources)) if (!(name in current)) errors.push('Removed web tour source: ' + name + '; recapture the tour')
  }
  if (!record(manifest.artifacts) || !Object.keys(manifest.artifacts).length) errors.push('Web tour artifact hashes must not be empty')
  else {
    for (const name of requiredArtifacts) if (!(name in manifest.artifacts)) errors.push('Unlisted web tour artifact: ' + name)
    for (const [name, expected] of Object.entries(manifest.artifacts)) {
      if (!name.startsWith(directory) || name.includes('\\') || name.split('/').some(part => ['.', '..', ''].includes(part)) ||
          !/\.(png|gif|webm|cast|txt)$/.test(name)) {
        errors.push('Invalid web tour artifact path: ' + name)
        continue
      }
      try {
        const file = path.join(root, name)
        if (!fs.lstatSync(file).isFile()) throw new Error('Not a regular file')
        const bytes = fs.readFileSync(file)
        if (!hash(expected) || digest(bytes) !== expected) errors.push('Changed web tour artifact: ' + name + '; recapture the tour')
        const problem = mediaProblem(name, bytes)
        if (problem) errors.push('Damaged web tour artifact: ' + name + ' (' + problem + ')')
      } catch { errors.push('Missing web tour artifact: ' + name) }
    }
  }
  if (!Array.isArray(manifest.scenes) || !manifest.scenes.length) errors.push('Web tour scenes must not be empty')
  else for (const [index, scene] of manifest.scenes.entries()) {
    if (!record(scene) || typeof scene.title !== 'string' || !scene.title.trim() ||
        typeof scene.screenshot !== 'string' || !scene.screenshot.endsWith('.png') ||
        !record(manifest.artifacts) || !(scene.screenshot in manifest.artifacts)) errors.push('Web tour scene ' + (index + 1) + ' needs a title and a captured PNG screenshot')
  }
  return errors
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const errors = tourProblems(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'))
  if (errors.length) { console.error(errors.join('\n')); process.exitCode = 1 }
  else console.log('PASS: web tour source and media hashes are current (synthetic frontend only)')
}
