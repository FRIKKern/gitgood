import {test, expect, type Page} from '@playwright/test'
import {writeFile} from 'node:fs/promises'
import {resolve} from 'node:path'

async function signIn(page: Page, username: string) {
  await page.goto('/')
  await page.getByLabel('Username', {exact: true}).fill(username)
  await page.getByLabel('Password', {exact: true}).fill('synthetic-password')
  await page.getByRole('button', {name: 'Sign in', exact: true}).click()
  await expect(page.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
}
const syntheticToken = 'synthetic-browser-only-credential'
const generation = () => crypto.randomUUID()
function saved(label: string) {
  return {state: 'connected', generation: generation(), id: generation(),
    origin: 'https://source.example.invalid', workspace: 'synthetic-workspace', project: 'default', dataset: 'production',
    source_identity: {token_id: generation(), kind: 'api', label, permissions: ['read'],
      expires_at: '2099-01-01T00:00:00Z', verified_at: '2026-10-08T00:00:00Z'}}
}
test('account settings reconcile current state, hide failed reads and discard old-actor mutation completion', async ({page, browser}, info) => {
  test.setTimeout(120_000)
  page.setDefaultTimeout(10_000)
  await signIn(page, 'owner')
  const owner = await (await page.request.get('/api/session')).json()
  let current: Record<string, unknown> = {state: 'unconfigured', generation: 'absent'}
  let mode: 'normal' | 'outage' | 'stale' | 'replay' | 'hold' = 'normal'
  let reads = 0, writes = 0, releaseHeld: (() => void) | undefined
  let heldReply: Promise<void> | undefined
  const bodies: Record<string, unknown>[] = []
  await page.route('**/api/connections/barkpark**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    const headers = {'x-gitgood-access-context': request.headers()['x-gitgood-access-context'] ?? owner.access_context}
    if (request.method() === 'GET') {
      reads++
      await route.fulfill({status: mode === 'outage' ? 503 : 200, headers,
        contentType: 'application/json', body: JSON.stringify(mode === 'outage' ? {error: 'connection_unavailable'} : headers['x-gitgood-access-context'] === owner.access_context ? current : {state: 'unconfigured', generation: 'absent'})})
      return
    }
    writes++
    const body = request.postDataJSON()
    bodies.push(body)
    expect(request.headers()['x-gitgood-csrf']).toBe(owner.csrf)
    expect(request.headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/)
    if (mode === 'stale') {
      current = saved('Concurrent replacement')
      await route.fulfill({status: 409, headers, contentType: 'application/json', body: JSON.stringify({error: 'connection_changed'})})
      return
    }
    const receipt = saved('Synthetic verified service')
    current = path.endsWith('/disconnect') || mode === 'replay'
      ? {...receipt, state: 'disconnected', generation: generation()} : receipt
    if (mode === 'hold') {
      await new Promise<void>(resolve => {releaseHeld = resolve})
      heldReply = route.fulfill({status: 200, headers, contentType: 'application/json', body: JSON.stringify(receipt)}).catch(() => {})
      await heldReply
      return
    }
    await route.fulfill({status: 200, headers, contentType: 'application/json', body: JSON.stringify(mode === 'replay' ? receipt : current)})
  })
  try {
    await page.reload()
    const panel = page.getByRole('region', {name: 'Barkpark connection', exact: true})
    await expect(panel.getByText('No saved connection', {exact: true})).toBeVisible()
    async function connect() {
      await panel.getByLabel('Barkpark workspace', {exact: true}).fill('synthetic-workspace')
      await panel.getByLabel('Barkpark API credential', {exact: true}).fill(syntheticToken)
      await panel.getByRole('button', {name: /^(Connect Barkpark|Replace Barkpark credential)$/}).click()
      await expect(panel.getByLabel('Barkpark API credential', {exact: true})).toHaveValue('')
    }
    await connect()
    await expect(panel.getByText('Saved connection', {exact: true})).toBeVisible()
    await expect(panel.getByText(/API service: Synthetic verified service/)).toBeVisible()
    await expect(page.getByRole('heading', {name: 'SSH access', exact: true})).toHaveCount(1)
    await page.screenshot({path: info.outputPath('barkpark-account-connected.png'), fullPage: true})
    expect(bodies[0]).toEqual({workspace: 'synthetic-workspace', project: 'default', dataset: 'production',
      token: syntheticToken, expected_generation: 'absent'})
    expect(await page.evaluate(token => JSON.stringify({...localStorage, ...sessionStorage}).includes(token), syntheticToken)).toBe(false)
    mode = 'outage'
    // Foreground polling exercises the real query error path without timers in the test.
    await expect(panel.getByRole('alert')).toContainText('Connection state unavailable', {timeout: 15_000})
    await expect(panel.getByText(/API service:/)).toHaveCount(0)
    await expect(panel.getByLabel('Barkpark API credential', {exact: true})).toHaveCount(0)
    mode = 'normal'
    await panel.getByRole('button', {name: 'Refresh connection'}).click()
    await expect(panel.getByText('Saved connection', {exact: true})).toBeVisible()
    mode = 'stale'
    await connect()
    await expect(panel.getByRole('status')).toContainText('The connection changed')
    await expect(panel.getByText(/API service: Concurrent replacement/)).toBeVisible()
    mode = 'normal'
    await panel.getByRole('button', {name: 'Disconnect Barkpark'}).click()
    await expect(panel.getByText('Disconnected', {exact: true})).toBeVisible()
    await expect(panel.getByText(/API service:/)).toHaveCount(0)
    mode = 'replay'
    await connect()
    // A historical success receipt cannot resurrect today's disconnected state.
    await expect(panel.getByText('Disconnected', {exact: true})).toBeVisible()
    await expect(panel.getByRole('status')).toContainText('Connection request confirmed')
    await expect(panel.getByText(/API service:/)).toHaveCount(0)
    mode = 'hold'
    await connect()
    await expect.poll(() => !!releaseHeld).toBe(true)
    const switcher = await page.context().newPage()
    await switcher.goto('/')
    await expect(switcher.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
    await switcher.getByRole('button', {name: 'Sign out', exact: true}).click()
    await expect(page.getByRole('heading', {name: 'Sign in to your installation'})).toBeVisible()
    await signIn(switcher, 'outsider')
    // Use actual shared cookies and native session polling for the account change.
    await expect(page.getByRole('heading', {name: 'Your repositories'})).toBeVisible()
    current = {state: 'unconfigured', generation: 'absent'}
    const outsiderPanel = page.getByRole('region', {name: 'Barkpark connection', exact: true})
    await expect(outsiderPanel.getByText('No saved connection', {exact: true})).toBeVisible()
    // Block further GETs so any old mutation's finally/refetch is detectable.
    let oldCompletionReads = 0
    await page.route('**/api/connections/barkpark', async route => {
      if (route.request().method() === 'GET') oldCompletionReads++
      await route.fallback()
    })
    releaseHeld!(); releaseHeld = undefined
    await expect.poll(() => !!heldReply).toBe(true)
    await heldReply
    // Browser round trips flush promise completion; no sleep-based race.
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    expect(oldCompletionReads).toBe(0)
    await expect(outsiderPanel.getByText('No saved connection', {exact: true})).toBeVisible()
    await expect(outsiderPanel.getByRole('status')).toHaveCount(0)
    await switcher.close()
    await expect(page.getByRole('heading', {name: 'SSH access', exact: true})).toHaveCount(1)
    await expect(page.getByRole('heading', {name: 'Barkpark connection', exact: true})).toHaveCount(1)
    await page.setViewportSize({width: 390, height: 844})
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({path: info.outputPath('barkpark-account-mobile.png'), fullPage: true})
    const receipt = JSON.stringify({fixture: 'synthetic browser connection wire with actual native sessions',
      reads, writes, old_completion_reads: oldCompletionReads, checks: ['enrollment', 'DOM-token-cleared', 'no-browser-secret-storage',
        'read-error-hides-metadata', 'stale-generation-reconciled', 'disconnect', 'historical-receipt-current-state',
        'held-write-account-switch-discard', 'no-old-actor-refetch', 'mobile-width'],
      limitations: ['Source connection responses are intercepted synthetic fixtures; live source backend proof is separate.']}, null, 2) + '\n'
    await writeFile(info.outputPath('barkpark-account-receipt.json'), receipt)
    await writeFile(resolve(process.env.GITGOOD_TEST_PRODUCTION === 'true' ? 'test-results-production' : 'test-results', 'barkpark-account-receipt.json'), receipt)
  } finally {releaseHeld?.()}
})
