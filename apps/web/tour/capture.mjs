// Capture the application itself; the tour fixture replaces only API responses.
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import {fileURLToPath} from 'node:url'
import {createHash} from 'node:crypto'
import {execFileSync} from 'node:child_process'
import {createServer} from 'vite'
import {chromium, expect} from '@playwright/test'
import viteConfig from '../vite.config.ts'
import {installTourFixtures, TOUR} from './fixtures.mjs'
import {sourceHashes} from '../../../scripts/web-tour.mjs'

const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const root = path.resolve(web, '../..')
const destination = path.join(root, 'docs/media/web')
const runtime = path.join(root, '.gitgood', 'web-tour-' + Date.now())
const viewport = {width: 1280, height: 900}
const tour = {repositoryLabel: `${TOUR.team} / ${TOUR.repository}`,
  pullTitle: 'Make release notes easier to scan', releaseTitle: 'Fieldnotes v0.3.0 · demo'}
const python = process.env.GITGOOD_TOUR_PYTHON || (os.platform() === 'win32' ? 'python' : 'python3')
// Check this before launching a browser. Installation belongs to setup, not capture.
execFileSync(python, ['-c', 'import PIL'], {stdio: 'pipe'})
await fs.mkdir(runtime, {recursive: true})
await fs.mkdir(destination, {recursive: true})
const beforeSources = sourceHashes(root)
const originalUpstream = process.env.GITGOOD_API_URL
process.env.GITGOOD_API_URL = 'http://127.0.0.1:0'
let server, context
try {
  server = await createServer({...viteConfig, root: web, configFile: false,
    cacheDir: path.join(runtime, 'vite-cache'),
    server: {host: '127.0.0.1', port: 0, strictPort: true, open: false, hmr: false}})
  await server.listen()
  const origin = 'http://127.0.0.1:' + server.httpServer.address().port
  context = await chromium.launchPersistentContext(path.join(runtime, 'browser'), {
    headless: true, viewport, locale: 'en-GB', timezoneId: 'UTC', reducedMotion: 'reduce',
    serviceWorkers: 'block',
    ...(process.env.GITGOOD_BROWSER_CHANNEL ? {channel: process.env.GITGOOD_BROWSER_CHANNEL} : {}),
    recordVideo: {dir: path.join(runtime, 'video'), size: viewport},
    env: {...process.env, TMP: runtime, TEMP: runtime, TMPDIR: runtime},
  })
  const fixtures = await installTourFixtures(context, {origin})
  const page = context.pages()[0] || await context.newPage()
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))
  const video = page.video()
  const scenes = []
  async function capture(id, title) {
    await page.evaluate(() => document.fonts.ready)
    await expect(page.getByRole('alert')).toHaveCount(0)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
    if (overflow) throw new Error('Horizontal overflow in ' + id)
    const screenshot = 'docs/media/web/' + id + '.png'
    await page.screenshot({path: path.join(root, screenshot), animations: 'disabled'})
    const visible = await page.locator('main').evaluate(main => {
      const leaves = [...main.querySelectorAll('h1,h2,h3,p,label,li,pre')]
      return leaves.filter(node => {
        const rect = node.getBoundingClientRect()
        return rect.height > 0 && rect.bottom > 0 && rect.top < innerHeight
      }).map(node => node.innerText.trim()).filter(Boolean).join('\n')
    })
    scenes.push({id, title, screenshot, route: new URL(page.url()).pathname,
      text: visible.replace(/[^\x20-\x7e\n]/g, ' ').replace(/ +/g, ' ').trim()})
    // Deliberate reading time in the recorded browser walkthrough.
    await page.waitForTimeout(2400)
  }
  await page.goto(origin)
  await expect(page.getByRole('heading', {name: 'Sign in to your installation'})).toBeVisible()
  await capture('01-sign-in', 'Sign in to a private installation')
  await page.getByLabel('Username').fill(TOUR.username)
  await page.getByLabel('Password').fill(TOUR.password)
  await page.getByRole('button', {name: 'Sign in', exact: true}).click()
  await expect(page.getByRole('heading', {name: 'Your repositories', exact: true})).toBeVisible()
  await expect(page.getByRole('link', {name: tour.repositoryLabel, exact: true})).toBeVisible()
  await capture('02-repositories', 'Find your team repository')
  await page.getByRole('link', {name: tour.repositoryLabel, exact: true}).click()
  await expect(page.getByRole('heading', {name: tour.repositoryLabel, exact: true})).toBeVisible()
  await expect(page.getByRole('link', {name: 'README.md', exact: true})).toBeVisible()
  await capture('03-code', 'Browse code at a pinned commit')
  await page.locator('.collaboration-panel').filter({has: page.getByRole('heading', {name: 'Pull requests', exact: true})})
    .getByRole('link', {name: tour.pullTitle, exact: true}).click()
  await expect(page.getByRole('heading', {name: tour.pullTitle, exact: true})).toBeVisible()
  await expect(page.locator('.source')).toContainText('diff --git')
  await page.evaluate(() => scrollTo(0, 0))
  await capture('04-review', 'Read a pull request and its diff')
  await page.getByRole('link', {name: 'Repository', exact: true}).click()
  const releases = page.getByRole('region', {name: 'Releases', exact: true})
  await releases.getByRole('link', {name: tour.releaseTitle, exact: true}).click()
  await expect(releases.getByRole('heading', {name: tour.releaseTitle, exact: true})).toBeVisible()
  await releases.evaluate(node => node.scrollIntoView({block: 'start'}))
  await capture('05-releases', 'Inspect a sample release and its assets')
  const diagnostics = fixtures.diagnostics()
  if (pageErrors.length || diagnostics.unknownApiPaths.length || diagnostics.rejectedMutations.length || diagnostics.blockedExternalRequests.length) {
    throw new Error(JSON.stringify({pageErrors, diagnostics}))
  }
  // Finalize the recording while the persistent browser connection still lives.
  await page.close()
  await video.saveAs(path.join(destination, 'walkthrough.webm'))
  await context.close()
  context = null
  const screens = scenes.map(scene => path.join(root, scene.screenshot))
  execFileSync(python, [path.join(web, 'tour/animate.py'), path.join(destination, 'walkthrough.gif'), ...screens], {stdio: 'inherit'})

  const asciiFrames = scenes.map((scene, index) => {
    const lines = scene.text.split('\n').flatMap(line => line.match(/.{1,88}(?:\s|$)|.{1,88}/g) || []).slice(0, 17).map(line => line.trimEnd())
    return ['GITGOOD / WEB TOUR / SAMPLE DATA', '='.repeat(88),
      '[' + (index + 1) + '/5] ' + scene.title, 'Screen: ' + scene.route,
      'Sign in -> Repositories -> Code -> Review -> Releases', '', ...lines,
      '', 'Actual frontend; synthetic API responses. This is not a terminal recording.'].join('\r\n')
  })
  await fs.writeFile(path.join(destination, 'walkthrough.txt'), (asciiFrames.join('\n\n' + '-'.repeat(88) + '\n\n') + '\n').replaceAll('\r\n', '\n'))
  const cast = [JSON.stringify({version: 2, width: 92, height: 29,
    title: 'Gitgood web screens - ASCII companion (synthetic data)',
    env: {TERM: 'xterm-256color'}}),
    ...asciiFrames.map((frame, index) => JSON.stringify([index * 2.4, 'o', '\x1b[2J\x1b[H' + frame])),
    JSON.stringify([12, 'o', '\r\nEnd of screen tour.\r\n'])].join('\n') + '\n'
  await fs.writeFile(path.join(destination, 'walkthrough.cast'), cast)
  const afterSources = sourceHashes(root)
  if (JSON.stringify(beforeSources) !== JSON.stringify(afterSources)) throw new Error('Tour sources changed during capture; rerun from a stable tree')
  const artifacts = {}
  for (const relative of [...scenes.map(scene => scene.screenshot), ...['walkthrough.gif', 'walkthrough.webm', 'walkthrough.cast', 'walkthrough.txt'].map(name => 'docs/media/web/' + name)]) {
    artifacts[relative] = createHash('sha256').update(await fs.readFile(path.join(root, relative))).digest('hex')
  }
  const manifest = {schemaVersion: 1, kind: 'frontend-with-synthetic-api',
    capturedAt: new Date().toISOString(), sourceCommit: execFileSync('git', ['rev-parse', 'HEAD'], {cwd: root, encoding: 'utf8'}).trim(),
    sourceState: 'Working tree captured; sources identifies normalized UTF-8/LF source content, sourceCommit is its base.',
    viewport, browser: process.env.GITGOOD_BROWSER_CHANNEL || 'chromium',
    limitations: 'API fixtures supply all data. No backend, Git, authentication or merge acceptance is established.',
    sourceHashFormat: 'sha256-utf8-lf', sources: afterSources, artifacts, scenes: scenes.map(({text, ...scene}) => scene)}
  await fs.writeFile(path.join(destination, 'capture.json'), JSON.stringify(manifest, null, 2) + '\n')
  console.log('Captured five actual web screens, GIF, browser video and ASCII companion in docs/media/web.')
} finally {
  await context?.close()
  await server?.close()
  if (originalUpstream === undefined) delete process.env.GITGOOD_API_URL
  else process.env.GITGOOD_API_URL = originalUpstream
}
