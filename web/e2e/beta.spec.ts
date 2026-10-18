import { test, expect, type BrowserContext, type Page } from '@playwright/test'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'

type TestIdentity = 'operator' | 'member' | 'second-member'

function testIdentityCookie(identity: TestIdentity) {
  return {
    name: 'stock_agent_e2e_login_as',
    value: identity,
    domain: '127.0.0.1',
    path: '/',
    httpOnly: false,
    secure: false,
    sameSite: 'Lax' as const,
  }
}

async function loginAs(
  page: Page,
  context: BrowserContext,
  identity: TestIdentity,
  destination: RegExp,
) {
  await context.addCookies([testIdentityCookie(identity)])
  await page.goto('/login')
  const popupPromise = page.waitForEvent('popup')
  await page.getByRole('button', { name: '카카오로 로그인' }).click()
  const popup = await popupPromise
  await popup.waitForURL(/\/auth\/kakao\/callback/)
  await expect(page).toHaveURL(destination)
}

function invitationPersistence(code: string): { used_at: string | null; account_id: string | null } {
  const script = `
import json, sqlite3, sys
db = sqlite3.connect('file:' + sys.argv[1] + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
row = db.execute(
    '''SELECT invitations.used_at, user_beta_access_grants.account_id
       FROM invitations
       LEFT JOIN user_beta_access_grants
         ON user_beta_access_grants.invitation_id = invitations.id
       WHERE invitations.code_hash = ?''',
    (sys.argv[2],),
).fetchone()
assert row is not None, 'issued invitation missing from database'
print(json.dumps({'used_at': row['used_at'], 'account_id': row['account_id']}))
`
  return JSON.parse(execFileSync(process.env.E2E_PYTHON!, [
    '-c',
    script,
    process.env.STOCK_AGENT_E2E_DATABASE!,
    createHash('sha256').update(code).digest('hex'),
  ], { encoding: 'utf8' }))
}

test('invited member redeems once and uses stored analysis without live services', async ({ browser }, testInfo) => {
  const operatorContext = await browser.newContext()
  const operatorPage = await operatorContext.newPage()
  await loginAs(operatorPage, operatorContext, 'operator', /\/invite$/)
  await operatorPage.getByRole('link', { name: '초대 발급' }).click()
  await expect(operatorPage).toHaveURL(/\/admin$/)
  await operatorPage.getByRole('button', { name: '초대 코드 발급', exact: true }).click()
  const code = (await operatorPage.getByTestId('invitation-code').textContent())?.trim()
  expect(code).toBeTruthy()
  expect(invitationPersistence(code!)).toEqual({ used_at: null, account_id: null })
  await operatorContext.close()

  const memberContext = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const memberPage = await memberContext.newPage()
  await loginAs(memberPage, memberContext, 'member', /\/invite$/)
  await expect(memberPage.getByRole('heading', { name: '초대 코드를 등록하세요' })).toBeVisible()
  await memberPage.goto('/app')
  await expect(memberPage).toHaveURL(/\/invite$/)
  expect((await memberPage.request.get('/watchlist')).status()).toBe(403)
  await memberPage.screenshot({ path: testInfo.outputPath('member-invite.png'), fullPage: true })

  await memberPage.getByRole('textbox', { name: '초대 코드', exact: true }).fill('not-a-real-invitation')
  await memberPage.getByRole('button', { name: '초대 코드 등록' }).click()
  await expect(memberPage.getByRole('alert')).toBeVisible()
  expect(invitationPersistence(code!)).toEqual({ used_at: null, account_id: null })

  await memberPage.getByRole('textbox', { name: '초대 코드', exact: true }).fill(code!)
  await memberPage.getByRole('button', { name: '초대 코드 등록' }).click()
  await expect(memberPage).toHaveURL(/\/app$/)
  const session = await memberPage.request.get('/auth/web/session')
  expect(await session.json()).toMatchObject({
    id: 'browser-test-member',
    is_operator: false,
    has_beta_access: true,
  })
  expect(invitationPersistence(code!)).toMatchObject({ account_id: 'browser-test-member' })
  expect(invitationPersistence(code!).used_at).not.toBeNull()

  await memberPage.getByLabel('관심 종목 코드').fill('aapl')
  await memberPage.getByRole('button', { name: '종목 추가' }).click()
  await expect(memberPage.locator('.watchlist')).toContainText('AAPL.KS')
  const history = memberPage.getByRole('list', { name: 'AAPL.KS 저장된 분석 이력' })
  await expect(history).toContainText('브라우저 테스트용 최근 공용 분석입니다.')
  await expect(history).toContainText('브라우저 테스트용 이전 공용 분석입니다.')
  await expect(memberPage.locator('.analysis-detail')).toContainText('브라우저 테스트용 최근 공용 분석입니다.')
  await expect(memberPage.locator('.analysis-detail')).toContainText('현금 흐름이 안정적입니다.')
  await expect(memberPage.locator('.analysis-detail')).toContainText('230원')
  await history.getByRole('button').last().click()
  await expect(memberPage.locator('.analysis-detail')).toContainText('브라우저 테스트용 이전 공용 분석입니다.')
  await memberPage.getByRole('button', { name: '최신 분석 보기' }).click()
  await expect(memberPage.locator('.analysis-detail')).toContainText('브라우저 테스트용 최근 공용 분석입니다.')
  await memberPage.screenshot({ path: testInfo.outputPath('member-analysis-detail.png'), fullPage: true })

  const conditions: Array<{ id: number; symbol: string; name: string; user_rule: string; validation_summary: string; enabled: boolean }> = []
  let connected = false
  await memberPage.route('**/alert-conditions', async route => {
    const request = route.request()
    if (request.method() === 'POST') {
      const body = request.postDataJSON() as { symbol: string; user_rule: string }
      conditions.push({ id: 9, symbol: body.symbol, name: '상승 조건', user_rule: body.user_rule, validation_summary: '검증 완료', enabled: true })
      await route.fulfill({ status: 201, json: conditions[0] })
    } else await route.fulfill({ json: conditions })
  })
  await memberPage.route('**/alert-conditions/9', async route => {
    conditions.length = 0
    await route.fulfill({ status: 204, body: '' })
  })
  await memberPage.route('**/notification-connections/kakao', async route => {
    if (route.request().method() === 'DELETE') {
      connected = false
      await route.fulfill({ status: 204, body: '' })
    } else await route.fulfill({ json: { connected, connection_id: connected ? 5 : null } })
  })
  await memberPage.route('**/notification-connections/kakao/authorize', async route => {
    expect(route.request().postDataJSON()).toEqual({ client: 'web' })
    await route.fulfill({ json: { authorization_url: 'http://127.0.0.1:8765/fake-kakao-consent' } })
  })
  await memberPage.route('**/fake-kakao-consent', async route => {
    await route.fulfill({ contentType: 'text/html', body: '<a href="/app?notification_connection=connected">Approve Kakao</a>' })
  })
  await memberPage.reload()
  await memberPage.getByLabel('알림 조건', { exact: true }).fill('주가가 5% 이상 오르면 알려줘')
  await memberPage.getByRole('button', { name: '조건 등록' }).click()
  await expect(memberPage.getByRole('list', { name: '내 알림 조건 목록' })).toContainText('상승 조건')
  await memberPage.getByRole('button', { name: 'AAPL.KS 조건 9 삭제' }).click()
  await expect(memberPage.getByText('등록된 알림 조건이 없습니다.')).toBeVisible()
  await memberPage.getByRole('button', { name: '카카오 알림 연결', exact: true }).click()
  await expect(memberPage).toHaveURL(/\/fake-kakao-consent$/)
  connected = true
  await memberPage.getByRole('link', { name: 'Approve Kakao' }).click()
  await expect(memberPage).toHaveURL(/\/app$/)
  await expect(memberPage.getByText('카카오 알림 연결됨')).toBeVisible()
  await memberPage.getByRole('button', { name: '연결 해제' }).click()
  await expect(memberPage.getByText('카카오 알림 연결 안 됨')).toBeVisible()

  await memberPage.getByRole('button', { name: 'AAPL.KS 삭제' }).click()
  await expect(memberPage.locator('.watchlist')).toHaveCount(0)
  await memberPage.reload()
  await expect(memberPage).toHaveURL(/\/app$/)
  await expect(memberPage.locator('.watchlist')).toHaveCount(0)

  await memberPage.goto('/invite')
  await expect(memberPage).toHaveURL(/\/app$/)
  await memberPage.goto('/admin')
  await expect(memberPage.getByTestId('invitation-code')).toHaveCount(0)
  const forbidden = await memberPage.request.post('/admin/invitations', {
    headers: { Origin: 'http://127.0.0.1:8765' },
  })
  expect(forbidden.status()).toBe(403)

  await memberPage.getByRole('button', { name: '로그아웃' }).click()
  await expect(memberPage).toHaveURL(/\/login$/)
  await loginAs(memberPage, memberContext, 'member', /\/app$/)
  await memberPage.reload()
  await expect(memberPage).toHaveURL(/\/app$/)
  await memberContext.close()

  const secondContext = await browser.newContext()
  const secondPage = await secondContext.newPage()
  await loginAs(secondPage, secondContext, 'second-member', /\/invite$/)
  await secondPage.getByRole('textbox', { name: '초대 코드', exact: true }).fill(code!)
  await secondPage.getByRole('button', { name: '초대 코드 등록' }).click()
  await expect(secondPage.getByRole('alert')).toBeVisible()
  await expect(secondPage).toHaveURL(/\/invite$/)
  expect(invitationPersistence(code!)).toMatchObject({ account_id: 'browser-test-member' })
  await secondContext.close()
})

test('anonymous users are guarded from beta and operator routes', async ({ page }) => {
  for (const route of ['/invite', '/app', '/admin']) {
    await page.goto(route)
    await expect(page).toHaveURL(/\/login$/)
  }

  expect((await page.request.get('/watchlist')).status()).toBe(401)
  expect((await page.request.post('/auth/web/invitations/redeem', {
    data: { code: 'anything' },
    headers: { Origin: 'http://127.0.0.1:8765' },
  })).status()).toBe(401)
  expect((await page.request.post('/admin/invitations', {
    headers: { Origin: 'http://127.0.0.1:8765' },
  })).status()).toBe(401)
})
