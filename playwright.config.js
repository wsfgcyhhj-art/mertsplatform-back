import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  timeout: 90000,
  expect: { timeout: 15000 },
  use: { baseURL: 'http://localhost:5173', browserName: 'chromium' },
  webServer: [
    { command: 'cd django_admin && venv/bin/python browser_test_server.py', url: 'http://127.0.0.1:8000/api/v1/health', timeout: 60000 },
    { command: 'npm run dev -- --host localhost --strictPort', url: 'http://localhost:5173', timeout: 30000 },
  ],
});
