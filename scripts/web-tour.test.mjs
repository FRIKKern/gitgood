import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {sourceFiles, sourceHashes, tourProblems} from './web-tour.mjs'

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gitgood-tour-'))
  t.after(() => fs.rmSync(root, {recursive: true, force: true}))
  const write = (name, body) => {
    const file = path.join(root, name)
    fs.mkdirSync(path.dirname(file), {recursive: true})
    fs.writeFileSync(file, body)
  }
  for (const name of ['apps/web/src/routes/index.tsx', 'apps/web/src/style.css', 'apps/web/package.json',
    'apps/web/package-lock.json', 'apps/web/vite.config.ts', 'apps/web/tour/capture.mjs', 'apps/web/tour/animate.py']) write(name, 'synthetic source\n')
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a8YQAAAAASUVORK5CYII=', 'base64')
  const gif = Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64')
  const files = Object.fromEntries(['01-sign-in', '02-repositories', '03-code', '04-review', '05-releases'].map(name => ['docs/media/web/' + name + '.png', png]))
  Object.assign(files, {
    'docs/media/web/walkthrough.gif': gif,
    'docs/media/web/walkthrough.webm': Buffer.from('1a45dfa381428681', 'hex'),
    'docs/media/web/walkthrough.cast': '{"version":2,"width":80,"height":24}\n[0,"o","Synthetic frontend tour\\r\\n"]\n',
    'docs/media/web/walkthrough.txt': 'Synthetic frontend tour\n'
  })
  for (const [name, bytes] of Object.entries(files)) write(name, bytes)
  const manifest = {
    schemaVersion: 1, kind: 'frontend-with-synthetic-api', sourceHashFormat: 'sha256-utf8-lf', capturedAt: '2026-10-11T12:00:00.000Z',
    sourceCommit: 'a'.repeat(40), viewport: {width: 1280, height: 800}, sources: sourceHashes(root),
    artifacts: Object.fromEntries(Object.entries(files).map(([name, bytes]) => [name, createHash('sha256').update(bytes).digest('hex')])),
    scenes: [{title: 'Sign in', screenshot: 'docs/media/web/01-sign-in.png'}]
  }
  const save = () => write('docs/media/web/capture.json', JSON.stringify(manifest))
  save()
  return {root, write, manifest, save}
}

test('tour freshness follows source bytes, not later documentation commits', t => {
  const {root, write, manifest, save} = fixture(t)
  write('README.md', 'A new guide\n')
  write('apps/web/tour/__pycache__/animate.pyc', 'local Python cache')
  manifest.sourceCommit = 'b'.repeat(40)
  save()
  assert.deepEqual(tourProblems(root), [])
  assert.ok(sourceFiles(root).includes('apps/web/tour/animate.py'))
  assert.ok(!sourceFiles(root).some(name => name.includes('__pycache__')))
})

test('changed UI, capture tooling and lockfiles require a fresh capture', t => {
  const {root, write} = fixture(t)
  for (const name of ['apps/web/src/style.css', 'apps/web/tour/animate.py', 'apps/web/package-lock.json']) write(name, 'changed\n')
  const errors = tourProblems(root)
  assert.equal(errors.filter(error => error.startsWith('Stale web tour source:')).length, 3)
})

test('Windows CRLF and Linux LF checkouts share source identity without hiding content changes', t => {
  const {root, write, manifest} = fixture(t)
  for (const name of sourceFiles(root)) write(name, fs.readFileSync(path.join(root, name), 'utf8').replaceAll('\n', '\r\n'))
  assert.deepEqual(sourceHashes(root), manifest.sources)
  assert.deepEqual(tourProblems(root), [])
  write('apps/web/src/style.css', 'changed content\r\n')
  assert.deepEqual(tourProblems(root), ['Stale web tour source: apps/web/src/style.css; recapture the tour'])
})

test('manifest must declare the source hash normalization format', t => {
  const {root, manifest, save} = fixture(t)
  delete manifest.sourceHashFormat
  save()
  assert.deepEqual(tourProblems(root), ['Web tour sourceHashFormat must be sha256-utf8-lf'])
})

test('new and removed routes cannot escape the captured source set', t => {
  const {root, write} = fixture(t)
  write('apps/web/src/routes/new.tsx', 'new route\n')
  fs.unlinkSync(path.join(root, 'apps/web/src/routes/index.tsx'))
  assert.deepEqual(tourProblems(root), [
    'Uncaptured web tour source: apps/web/src/routes/new.tsx',
    'Removed web tour source: apps/web/src/routes/index.tsx; recapture the tour'
  ])
})

test('changed, missing and unlisted media fail independently', t => {
  const {root, write, manifest, save} = fixture(t)
  write('docs/media/web/walkthrough.txt', 'different transcript\n')
  fs.unlinkSync(path.join(root, 'docs/media/web/03-code.png'))
  delete manifest.artifacts['docs/media/web/04-review.png']
  save()
  const errors = tourProblems(root)
  assert.ok(errors.some(error => error.startsWith('Changed web tour artifact: docs/media/web/walkthrough.txt')))
  assert.ok(errors.includes('Missing web tour artifact: docs/media/web/03-code.png'))
  assert.ok(errors.includes('Unlisted web tour artifact: docs/media/web/04-review.png'))
})

test('invalid media cannot be blessed by replacing its digest', t => {
  const {root, write, manifest, save} = fixture(t)
  const name = 'docs/media/web/walkthrough.gif', bytes = Buffer.from('this is not a GIF')
  write(name, bytes)
  manifest.artifacts[name] = createHash('sha256').update(bytes).digest('hex')
  save()
  assert.deepEqual(tourProblems(root), ['Damaged web tour artifact: ' + name + ' (invalid GIF envelope)'])
})

test('empty inventories, missing scenes and escaping paths do not validate', t => {
  const {root, manifest, save} = fixture(t)
  manifest.sources = {}
  manifest.scenes = []
  manifest.artifacts['docs/media/web/../../outside.png'] = 'a'.repeat(64)
  save()
  const errors = tourProblems(root)
  assert.ok(errors.includes('Web tour source hashes must not be empty'))
  assert.ok(errors.includes('Web tour scenes must not be empty'))
  assert.ok(errors.includes('Invalid web tour artifact path: docs/media/web/../../outside.png'))
  manifest.artifacts = {}
  save()
  assert.ok(tourProblems(root).includes('Web tour artifact hashes must not be empty'))
})
