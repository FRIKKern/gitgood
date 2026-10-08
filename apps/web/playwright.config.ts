import {defineConfig} from '@playwright/test'
const external=process.env.GITGOOD_TEST_WEB_URL
const production=process.env.GITGOOD_TEST_PRODUCTION==='true'
const output=production?'test-results-production':'test-results'
export default defineConfig({
  testDir:'./e2e',outputDir:output,workers:1,reporter:[['list'],['json',{outputFile:output+'/results.json'}]],
  use:{baseURL:external??'http://localhost:47840',headless:true,trace:'off',screenshot:'only-on-failure',
    ignoreHTTPSErrors:production,
    ...(process.env.GITGOOD_BROWSER_CHANNEL?{channel:process.env.GITGOOD_BROWSER_CHANNEL}:{})},
  ...(external?{}:{webServer:{command:'npm run dev',url:'http://localhost:47840',reuseExistingServer:!process.env.CI}}),
})
