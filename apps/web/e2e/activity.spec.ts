import {test, expect, type Page} from '@playwright/test'
import {fixtureSession} from './fixture-session'
import {writeFile} from 'node:fs/promises'
import {resolve} from 'node:path'
const upstream = process.env.GITGOOD_TEST_API_URL ?? 'http://127.0.0.1:47841'
async function signIn(page: Page, username: string) {
  await page.goto('/')
  await page.getByLabel('Username', {exact: true}).fill(username)
  await page.getByLabel('Password', {exact: true}).fill('synthetic-password')
  await page.getByRole('button', {name: 'Sign in', exact: true}).click()
  await expect(page.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
}
test('private discovery handles delayed replies, source failure, reconnect and account changes', async ({page, browser}, info) => {
  test.setTimeout(150_000)
  page.setDefaultTimeout(10_000)
  const owner = await fixtureSession('owner'), outsider = await fixtureSession('outsider')
  const name = 'private-discovery-' + Date.now(), hidden = 'foreign-discovery-' + Date.now()
  for (const [headers, team, repository] of [[owner, 'team', name], [outsider, 'elsewhere', hidden]] as const) {
    const response = await fetch(upstream + '/api/repos', {method: 'POST', headers: {...headers, 'idempotency-key': repository},
      body: JSON.stringify({team, name: repository})})
    expect(response.status).toBe(201)
  }
  await signIn(page, 'owner')
  const ownerPanel = page.getByRole('region', {name: 'Search and activity', exact: true})
  await ownerPanel.getByLabel('Search permitted records').fill(name)
  await ownerPanel.getByRole('button', {name: 'Search', exact: true}).click()
  await expect(ownerPanel.getByRole('link', {name: 'team / ' + name})).toBeVisible()
  await ownerPanel.getByLabel('Search permitted records').fill(hidden)
  await ownerPanel.getByRole('button', {name: 'Search', exact: true}).click()
  await expect(ownerPanel.getByText('No matching permitted records.', {exact: true})).toBeVisible()
  expect(await ownerPanel.innerText()).not.toContain('elsewhere')
  const membership = page.getByRole('region', {name: 'Team members team', exact: true})
  await membership.getByLabel('Member username', {exact: true}).fill('outsider')
  await membership.getByLabel('Member role', {exact: true}).selectOption('writer')
  await membership.getByRole('button', {name: 'Add member', exact: true}).click()
  await expect(membership.getByLabel('Role for outsider')).toHaveValue('writer')
  console.log('Activity fixture: permission granted')
  const context = await browser.newContext({baseURL: process.env.GITGOOD_TEST_WEB_URL ?? 'http://localhost:47840',
    ignoreHTTPSErrors: process.env.GITGOOD_TEST_PRODUCTION === 'true'})
  let releaseHeld: (() => void) | undefined
  let heldOnce = false
  try {
    const viewer = await context.newPage()
    viewer.setDefaultTimeout(10_000)
    await signIn(viewer, 'outsider')
    const panel = viewer.getByRole('region', {name: 'Search and activity', exact: true})
    // Store a synthetic private draft so the real cache boundary must clear it.
    await viewer.evaluate(() => sessionStorage.setItem('gitgood-comment:synthetic-private', 'private cached comment'))
    await panel.getByLabel('Search permitted records').fill(name)
    await panel.getByRole('button', {name: 'Search', exact: true}).click()
    await expect(panel.getByRole('link', {name: 'team / ' + name})).toBeVisible()
    console.log('Activity fixture: permitted search visible')
    await viewer.route('**/api/search?*', async route => {
      if (heldOnce) {await route.continue(); return}
      heldOnce = true
      const response = await route.fetch()
      await new Promise<void>(resolve => {releaseHeld = resolve})
      await route.fulfill({response}).catch(() => {})
    })
    await panel.getByRole('button', {name: 'Refresh records', exact: true}).click()
    await expect.poll(() => !!releaseHeld).toBe(true)
    console.log('Activity fixture: old response held')
    await membership.getByRole('button', {name: 'Remove outsider', exact: true}).click()
    await expect(membership.getByLabel('Role for outsider')).toHaveCount(0)
    console.log('Activity fixture: membership removed')
    // Actual current-session poll detects the role removal while the old response is held.
    await expect.poll(() => viewer.evaluate(() => sessionStorage.getItem('gitgood-comment:synthetic-private')), {timeout: 15_000}).toBeNull()
    console.log('Activity fixture: draft purged')
    releaseHeld!(); releaseHeld = undefined
    await viewer.unroute('**/api/search?*')
    const currentPanel = viewer.getByRole('region', {name: 'Search and activity', exact: true})
    await currentPanel.getByLabel('Search permitted records').fill(name)
    await currentPanel.getByRole('button', {name: 'Search', exact: true}).click()
    await expect(currentPanel.getByText('No matching permitted records.', {exact: true})).toBeVisible()
    await expect(viewer.getByRole('heading', {name: 'team / ' + name, exact: true})).toHaveCount(0)
    expect((await viewer.request.get('/api/search?q=' + name)).status()).toBe(200)
    expect((await (await viewer.request.get('/api/search?q=' + name)).json()).records).toEqual([])
    await viewer.screenshot({path: info.outputPath('revoked-discovery.png'), fullPage: true})
  } finally {
    releaseHeld?.()
    await context.close()
    const existing = (await (await fetch(upstream + '/api/teams/team/members', {headers: owner})).json()).members
    const member = existing.find((value: {username: string}) => value.username === 'outsider')
    if (member) await fetch(upstream + '/api/teams/team/members', {method: 'POST', headers: {...owner, 'idempotency-key': 'cleanup-' + name},
      body: JSON.stringify({username: 'outsider', role: 'absent', expected_role: member.role})})
  }
  await page.goto('/')
  const panel = page.getByRole('region', {name: 'Search and activity', exact: true})
  // Finish the initial read before changing the source. Refetch while loading
  // can reuse a request that started before the interception was installed.
  await expect(panel.getByRole('link', {name: 'Repository created', exact: true}).first()).toBeVisible()
  let unavailable = true
  let replayed: Record<string, unknown> | null = null
  const access = (await (await page.request.get('/api/session')).json()).access_context
  await page.route('**/api/activity', route => unavailable ? route.fulfill({status: 503, contentType: 'application/json',
    headers: {'x-gitgood-access-context': access}, body: JSON.stringify({error: 'discovery_unavailable'})}) : replayed ?
      route.fulfill({status: 200, contentType: 'application/json', headers: {'x-gitgood-access-context': access}, body: JSON.stringify(replayed)}) : route.continue())
  const failedRefresh = page.waitForResponse(response => new URL(response.url()).pathname === '/api/activity' && response.status() === 503)
  await panel.getByRole('button', {name: 'Refresh records', exact: true}).click()
  await failedRefresh
  await expect(panel.getByRole('alert')).toContainText('Records unavailable')
  await expect(panel.getByRole('link', {name: 'Repository created', exact: true})).toHaveCount(0)
  unavailable = false
  await panel.getByRole('button', {name: 'Retry records'}).click()
  await expect(panel.getByRole('link', {name: 'Repository created', exact: true}).first()).toBeVisible()
  const snapshot = await (await page.request.get('/api/activity')).json()
  const before = snapshot.records
  expect(new Set(before.map((record: {id: string}) => record.id)).size).toBe(before.length)
  const later = name + '-after-gap'
  const added = await fetch(upstream + '/api/repos', {method: 'POST', headers: {...owner, 'idempotency-key': later}, body: JSON.stringify({team: 'team', name: later})})
  expect(added.status).toBe(201)
  replayed = snapshot
  const replayResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/activity')
  await panel.getByRole('button', {name: 'Refresh records', exact: true}).click()
  expect((await (await replayResponse).json()).snapshot).toBe(snapshot.snapshot)
  await expect(panel.locator('.discovery-records li')).toHaveCount(before.length)
  await expect(panel.locator('a[href="/repos/team/' + later + '"]')).toHaveCount(0)
  replayed = null
  await panel.getByRole('button', {name: 'Refresh records', exact: true}).click()
  await expect(panel.locator('a[href="/repos/team/' + later + '"]')).toHaveCount(1)
  await page.context().setOffline(true)
  await expect(page.getByRole('alert')).toContainText('Access check unavailable')
  await expect(page.getByRole('region', {name: 'Search and activity', exact: true})).toHaveCount(0)
  await page.context().setOffline(false)
  await expect(page.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
  await expect(page.getByRole('heading', {name: 'team / ' + name, exact: true})).toBeVisible()
  await expect(page.getByRole('region', {name: 'Search and activity', exact: true}).getByRole('link', {name: 'Repository created', exact: true}).first()).toBeVisible()
  await expect(page.getByRole('region', {name: 'Team members team', exact: true}).getByLabel('Role for owner')).toHaveValue('owner')
  await page.screenshot({path: info.outputPath('activity-reconnected.png'), fullPage: true})
  await page.setViewportSize({width: 390, height: 844})
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({path: info.outputPath('activity-mobile.png'), fullPage: true})
  await page.setViewportSize({width: 1280, height: 720})
  const audit = (await (await fetch(upstream + '/api/teams/team/members', {headers: owner})).json()).events
    .filter((event: {username: string}) => event.username === 'outsider').slice(0, 2)
  expect(audit).toHaveLength(2)
  expect(audit.some((event: {role: string}) => event.role === 'absent')).toBe(true)
  const retained = before.find((record: {url: string}) => record.url === '/repos/team/' + name)
  expect(retained).toBeTruthy()
  const receipt = JSON.stringify({repository: name, hidden_repository: hidden, later_repository: later,
    record: {id: retained.id, url: retained.url, occurred_at: retained.occurred_at},
    membership_events: audit.map((event: {id: string}) => event.id), criteria: ['J13-A-native', 'J13-B', 'J13-C-native']}, null, 2) + '\n'
  await writeFile(info.outputPath('activity-receipt.json'), receipt)
  await writeFile(resolve(process.env.GITGOOD_TEST_PRODUCTION === 'true' ? 'test-results-production' : 'test-results', 'activity-receipt.json'), receipt)
  // A second tab shares the browser cookie but has an independent memory cache.
  const second = await page.context().newPage()
  await second.goto('/')
  await expect(second.getByRole('heading', {name: 'team / ' + name, exact: true})).toBeVisible()
  await page.getByRole('button', {name: 'Sign out', exact: true}).click()
  await expect(second.getByRole('heading', {name: 'Sign in to your installation'})).toBeVisible()
  await signIn(page, 'outsider')
  await expect(second.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
  await expect(second.getByRole('heading', {name: 'team / ' + name, exact: true})).toHaveCount(0)
  await expect(second.getByRole('heading', {name: 'elsewhere / ' + hidden, exact: true})).toBeVisible()
  await second.close()
})
