import {expect} from '@playwright/test'

// Async imports own the repository lease while validating real Git. Use the same bounded
// allowance as the import journey; a normal five-second UI assertion is not that contract.
export async function appliedImport(base: string, id: string, headers: {[name: string]: string}) {
  await expect.poll(async () => {
    const response = await fetch(base + '/operations/' + id, {headers, signal: AbortSignal.timeout(15_000)})
    expect(response.status).toBe(200)
    const current = (await response.json()).operation
    if (!['started', 'validated', 'applied'].includes(current.state))
      throw new Error('Fixture import reached a non-success state: ' + current.state)
    return current.state
  }, {timeout: 60_000}).toBe('applied')
}
