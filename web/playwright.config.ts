import { defineConfig, devices } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, resolve, join } from 'node:path'

const python = process.env.E2E_PYTHON ?? resolve(
  '..', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)
// The config is evaluated again in Playwright workers. Let those workers reuse
// only the path created by this config's parent process; never trust a shell's
// arbitrary E2E database setting.
const inheritedDatabase = process.env.STOCK_AGENT_E2E_DATABASE
const inheritedDirectory = inheritedDatabase ? dirname(resolve(inheritedDatabase)) : undefined
const ownsInheritedDatabase = process.env.STOCK_AGENT_E2E_DATABASE_OWNED === 'true'
  && inheritedDirectory !== undefined
  && dirname(inheritedDirectory) === resolve(tmpdir())
  && basename(inheritedDirectory).startsWith('stock-agent-e2e-')
if (!ownsInheritedDatabase) {
  process.env.STOCK_AGENT_E2E_DATABASE = join(mkdtempSync(join(tmpdir(), 'stock-agent-e2e-')), 'test.db')
  process.env.STOCK_AGENT_E2E_DATABASE_OWNED = 'true'
}
const database = process.env.STOCK_AGENT_E2E_DATABASE
if (!database) {
  throw new Error('Playwright did not create an isolated E2E database')
}
process.env.E2E_PYTHON = python

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:8765',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `"${python}" tests/browser_server.py`,
    cwd: resolve('..'),
    url: 'http://127.0.0.1:8765/openapi.json',
    reuseExistingServer: false,
    timeout: 60_000,
    env: { STOCK_AGENT_E2E_DATABASE: database },
  },
})
