// @ts-check
const { defineConfig } = require('@playwright/test');

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:8000';
const urlObj = new URL(baseURL);
const host = urlObj.hostname;
const port = urlObj.port || '8000';

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: `python3 manage.py runserver ${host}:${port}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
