import {defineConfig} from '@playwright/test'
export default defineConfig({
  testDir: './e2e', workers: 1, reporter: [['list'], ['json', {outputFile: 'test-results/results.json'}]],
  use: {baseURL: 'http://localhost:47840', headless: true, trace: 'off', screenshot: 'only-on-failure',
    ...(process.env.GITGOOD_BROWSER_CHANNEL ? {channel: process.env.GITGOOD_BROWSER_CHANNEL} : {})},
  webServer: {command: 'npm run dev', url: 'http://localhost:47840', reuseExistingServer: !process.env.CI},
})
