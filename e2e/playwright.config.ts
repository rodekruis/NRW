import { defineConfig } from '@playwright/test';

import { env } from '@nrw-e2e/env';

export default defineConfig({
  tsconfig: './tsconfig.json',
  snapshotPathTemplate: '{testDir}/__screenshots__/{testFilePath}/{arg}{ext}',
  fullyParallel: false,
  forbidOnly: env.CI, // Fail the build on CI if you accidentally left test.only in the source code.
  retries: 1,
  reporter: [['list']],
  // Specs share one database, so they must not run concurrently.
  workers: 1,
  outputDir: './test-results',
  timeout: 60_000,
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.001,
    },
  },
  use: {
    baseURL: env.BASE_URL,
    locale: 'en-US',
    timezoneId: 'UTC',
    video: 'on-first-retry',
    screenshot: 'only-on-failure',
    headless: true,
    acceptDownloads: true,
    actionTimeout: 20_000,
    launchOptions: {
      args: ['--window-size=1920,1024'],
    },
    viewport: null,
    ignoreHTTPSErrors: true,
    bypassCSP: false,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'setup',
      testDir: './nrw/setup',
      testMatch: '*.setup.ts',
      retries: 0,
      timeout: 600_000,
    },
    {
      name: 'chromium',
      testDir: './nrw/tests',
      dependencies: ['setup'],
      use: { channel: 'chromium' },
    },
  ],
});
