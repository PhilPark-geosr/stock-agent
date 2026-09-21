import { test, expect } from '@playwright/test'
import { createHash, randomBytes, randomUUID } from 'node:crypto'
import { execFileSync } from 'node:child_process'

function savedInvitation(code: string): { code_hash: string; used_at: null; lifetime: number } {
  const script = `
import json, sqlite3, sys
from datetime import datetime
db = sqlite3.connect('file:' + sys.argv[1] + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
row = db.execute('SELECT code_hash, issued_at, expires_at, used_at FROM invitations WHERE code_hash = ?', (sys.argv[2],)).fetchone()
assert row is not None, 'issued invitation missing from database'
print(json.dumps({'code_hash': row['code_hash'], 'used_at': row['used_at'], 'lifetime': (datetime.fromisoformat(row['expires_at']) - datetime.fromisoformat(row['issued_at'])).total_seconds()}))
`
  return JSON.parse(execFileSync(process.env.E2E_PYTHON!, [
    '-c', script, process.env.STOCK_AGENT_E2E_DATABASE!, createHash('sha256').update(code).digest('hex'),
  ], { encoding: 'utf8' }))
}

function savedSession(accountId: string, expiresAt: Date): string {
  const token = `browser-e2e-${randomBytes(32).toString('base64url')}`
  const script = `
import hashlib, sqlite3, sys, uuid
db = sqlite3.connect(sys.argv[1])
account = db.execute('SELECT id FROM user_accounts WHERE id = ?', (sys.argv[2],)).fetchone()
assert account is not None, 'browser test account missing from database'
db.execute(
    'INSERT INTO auth_sessions (id, user_account_id, token_hash, expires_at, revoked_at) VALUES (?, ?, ?, ?, NULL)',
    (sys.argv[3], sys.argv[2], hashlib.sha256(sys.argv[4].encode()).hexdigest(), sys.argv[5]),
)
db.commit()
`
  execFileSync(process.env.E2E_PYTHON!, [
    '-c', script,
    process.env.STOCK_AGENT_E2E_DATABASE!, accountId, randomUUID(), token, expiresAt.toISOString(),
  ])
  return token
}

function sessionCookie(token: string) {
  return {
    name: 'stock_agent_session',
    value: token,
    domain: '127.0.0.1',
    path: '/',
    httpOnly: true,
    secure: false,
    sameSite: 'Lax' as const,
  }
}

test('anonymous direct access redirects to login and cannot issue invitations', async ({ page }, testInfo) => {
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('button', { name: '카카오로 로그인' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('desktop-login.png'), fullPage: true })
  const response = await page.request.post('/admin/invitations', {
    headers: { Origin: 'http://127.0.0.1:8765' },
  })
  expect(response.status()).toBe(401)
})

test('operator logs in, issues persisted invitation, copies, refreshes and logs out on mobile', async ({ page, context }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/login')
  const popupPromise = page.waitForEvent('popup')
  await page.getByRole('button', { name: '카카오로 로그인' }).click()
  const popup = await popupPromise
  await popup.waitForURL(/\/auth\/kakao\/callback/)
  await expect(page).toHaveURL(/\/admin$/)
  const session = await page.request.get('/auth/web/session')
  expect(await session.json()).toMatchObject({ id: 'browser-test-operator', is_operator: true })
  const cookies = await context.cookies()
  expect(cookies.find(cookie => cookie.name === 'stock_agent_session')).toMatchObject({
    httpOnly: true, sameSite: 'Lax',
  })
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/admin/invitations') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '초대 코드 발급', exact: true }).click()
  const response = await responsePromise
  expect(response.status()).toBe(201)
  const result = await response.json()
  await expect(page.getByTestId('invitation-code')).toHaveText(result.code)
  await expect(page.getByText(/한국 시간/)).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('mobile-admin.png'), fullPage: true })
  expect(savedInvitation(result.code)).toEqual({
    code_hash: createHash('sha256').update(result.code).digest('hex'),
    used_at: null,
    lifetime: 7 * 24 * 60 * 60,
  })
  await page.getByRole('button', { name: '코드 복사' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(result.code)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.reload()
  await expect(page.getByRole('button', { name: '초대 코드 발급', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '로그아웃' }).click()
  await expect(page).toHaveURL(/\/login/)
  expect((await page.request.get('/auth/web/session')).status()).toBe(401)
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/login/)
})

test('member session can view its account but cannot issue invitations', async ({ page, context }) => {
  await context.addCookies([sessionCookie(savedSession('browser-test-member', new Date(Date.now() + 60_000)))])
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/admin$/)
  await expect(page.getByText('browser-test-member')).toBeVisible()
  await expect(page.getByRole('button', { name: '초대 코드 발급', exact: true })).toHaveCount(0)
  const response = await page.request.post('/admin/invitations', {
    headers: { Origin: 'http://127.0.0.1:8765' },
  })
  expect(response.status()).toBe(403)
})

test('expired browser session is redirected to login and rejected by the API', async ({ page, context }) => {
  await context.addCookies([sessionCookie(savedSession('browser-test-member', new Date(Date.now() - 60_000)))])
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('button', { name: '카카오로 로그인' })).toBeVisible()
  expect((await page.request.get('/auth/web/session')).status()).toBe(401)
})
