import { expect, test } from './fixtures'
import { accessToken, prepareAuthenticatedContext } from './support'

const token = accessToken

test('gm and player render the same game through shared play components', async ({ browser, request }) => {
  const headers = { Authorization: `Bearer ${token()}` }
  const games = await (await request.get('/api/games', { headers })).json()
  const game = games.games.find((item: any) => item.player_count > 1 || item.solo_mode === false) || games.games[0]
  const chars = await (await request.get(`/api/games/${encodeURIComponent(game.game_key)}/characters`, { headers })).json()
  const player = chars.players.find((item: any) => item.user_id !== game.gm_uid) || chars.players[0]

  const gmContext = await browser.newContext()
  await prepareAuthenticatedContext(gmContext, request)
  const gmPage = await gmContext.newPage()
  await gmPage.setViewportSize({ width: 1366, height: 768 })
  await gmPage.goto(`/#/play?game=${encodeURIComponent(game.game_key)}`)

  const playerContext = await browser.newContext()
  const playerPage = await playerContext.newPage()
  await playerPage.setViewportSize({ width: 390, height: 844 })
  await playerPage.goto(`/#/play?game=${encodeURIComponent(game.game_key)}&user=${encodeURIComponent(player.user_id)}`)

  await expect(gmPage.getByTestId('timeline')).toBeVisible()
  await expect(playerPage.getByTestId('timeline')).toBeVisible()
  await expect(gmPage.locator('.portrait-edit-button')).toBeVisible()
  await gmPage.locator('.portrait-edit-button').click()
  await expect(gmPage.locator('.portrait-picker')).toBeVisible()
  const gmComposerBottom = await gmPage.locator('.composer').evaluate(element => element.getBoundingClientRect().bottom)
  const playerLayout = await playerPage.evaluate(() => {
    const page = document.querySelector<HTMLElement>('.play-page')!.getBoundingClientRect()
    const hud = document.querySelector<HTMLElement>('.play-hud')!.getBoundingClientRect()
    const main = document.querySelector<HTMLElement>('.play-main')!.getBoundingClientRect()
    const composer = document.querySelector<HTMLElement>('.composer')!.getBoundingClientRect()

    return {
      viewportHeight: window.innerHeight,
      pageTop: page.top,
      pageBottom: page.bottom,
      hudTop: hud.top,
      mainBottom: main.bottom,
      composerBottom: composer.bottom,
    }
  })
  expect(gmComposerBottom).toBeLessThanOrEqual(768)
  expect(Math.abs(playerLayout.pageTop)).toBeLessThanOrEqual(1)
  expect(Math.abs(playerLayout.hudTop)).toBeLessThanOrEqual(1)
  expect(Math.abs(playerLayout.viewportHeight - playerLayout.pageBottom)).toBeLessThanOrEqual(1)
  expect(Math.abs(playerLayout.viewportHeight - playerLayout.mainBottom)).toBeLessThanOrEqual(1)
  expect(playerLayout.composerBottom).toBeGreaterThanOrEqual(playerLayout.viewportHeight - 12)
  expect(playerLayout.composerBottom).toBeLessThanOrEqual(playerLayout.viewportHeight + 1)
  await playerPage.getByRole('button', { name: '状态' }).click()
  await expect(playerPage.getByRole('heading', { name: player.character_name, exact: true })).toBeVisible()
  await expect(playerPage.getByPlaceholder('用自然语言描述行动')).toBeVisible()
  await gmContext.close()
  await playerContext.close()
})

test('generic invite opens free character creation without gm password', async ({ page, request }) => {
  const games = await (await request.get('/api/games', { headers: { Authorization: `Bearer ${token()}` } })).json()
  const game = games.games.find((item: any) => item.solo_mode === false) || games.games[0]
  const unexpectedUnauthorized: string[] = []
  page.on('response', response => {
    if (response.status() === 401 && /\/api\/(?:system\/update-check|plugins\/themes)/.test(response.url())) {
      unexpectedUnauthorized.push(response.url())
    }
  })
  await page.goto(`/#/join?game=${encodeURIComponent(game.game_key)}&share=1`)
  await expect(page.getByRole('heading', { name: '创建你的角色' })).toBeVisible()
  await expect(page.getByText('数字框可直接输入任意数值')).toBeVisible()
  await expect(page.getByRole('button', { name: '创建角色并进入' })).toBeVisible()
  const layout = await page.evaluate(() => {
    const background = document.querySelector<HTMLElement>('.join-page')!
    const form = document.querySelector<HTMLElement>('.join-form')!
    return {
      backgroundBottom: background.getBoundingClientRect().bottom,
      backgroundHeight: background.getBoundingClientRect().height,
      formBottom: form.getBoundingClientRect().bottom,
      viewportHeight: window.innerHeight,
    }
  })
  expect(layout.backgroundBottom).toBeGreaterThanOrEqual(layout.formBottom)
  expect(layout.backgroundHeight).toBeGreaterThan(layout.viewportHeight)
  expect(unexpectedUnauthorized).toEqual([])
})

test('plugin settings are generated from manifest schema', async ({ page }) => {
  await page.addInitScript(value => localStorage.setItem('trpg_access_token', value), token())
  await page.goto('/#/plugins')
  const pluginHeading = page.getByRole('heading', { name: /^QQ \/ NapCat/ })
  await expect(pluginHeading).toBeVisible()
  await pluginHeading.click()
  await expect(page.getByRole('heading', { name: 'NapCat 连接', exact: true }).first()).toBeVisible()
  await expect(page.getByRole('heading', { name: '聊天过滤', exact: true }).first()).toBeVisible()
  await expect(page.getByRole('textbox', { name: '群聊名单', exact: true }).first()).toBeVisible()
  await expect(page.getByLabel('屏蔽 QQ 官方机器人').first()).toBeChecked()
})

test('custom backgrounds stay browser-local and can be restored', async ({ page }) => {
  await page.addInitScript(value => localStorage.setItem('trpg_access_token', value), token())
  const writes: string[] = []
  page.on('request', request => {
    if (['POST', 'PUT', 'PATCH'].includes(request.method())) writes.push(request.url())
  })
  await page.goto('/#/settings?section=appearance')
  const card = page.locator('.background-option-card').first()
  const input = card.locator('input[type="file"]')
  await input.setInputFiles({
    name: 'local-background.png',
    mimeType: 'image/png',
    buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z4r8AAAAASUVORK5CYII=', 'base64'),
  })
  await expect(card.getByText('本地自定义')).toBeVisible()
  const cssImage = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--df-bg-atmosphere-image'))
  expect(cssImage).toContain('blob:')
  expect(writes).toEqual([])
  await card.locator('button').click()
  await expect(card.getByText('本地自定义')).toBeHidden()
})
