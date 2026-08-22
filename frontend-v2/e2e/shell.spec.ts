import { expect, test } from './fixtures'
import { accessToken, prepareAuthenticatedPage } from './support'

test('new shell and Vue login route render', async ({ page }) => {
  const token = accessToken()
  await page.addInitScript(value => {
    localStorage.setItem('trpg_access_token', value)
    localStorage.setItem('diceframe_locale', 'zh-CN')
  }, token)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '游戏总览' })).toBeVisible()
  await page.goto('/#/login')
  await expect(page.getByRole('heading', { name: 'DiceFrame', exact: true })).toBeVisible()
  await expect(page.locator('.login-announcement')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '📋 DiceFrame 使用指引', exact: true })).toHaveCount(0)

  const emblem = page.locator('.login-emblem-wrap')
  const mark = emblem.locator('.brand-mark')
  await expect(emblem.locator('.login-emblem-geometry')).toBeVisible()
  const [emblemBox, markBox] = await Promise.all([emblem.boundingBox(), mark.boundingBox()])
  expect(emblemBox).not.toBeNull()
  expect(markBox).not.toBeNull()
  expect(Math.abs((emblemBox!.x + emblemBox!.width / 2) - (markBox!.x + markBox!.width / 2))).toBeLessThanOrEqual(1)
  expect(Math.abs((emblemBox!.y + emblemBox!.height / 2) - (markBox!.y + markBox!.height / 2))).toBeLessThanOrEqual(1)
  const lowerRing = await page.locator('.login-page').evaluate(element => getComputedStyle(element, '::before').content)
  expect(lowerRing).toBe('none')
})

test('hub controls whether the overview shows the direct-connect entry', async ({ page, request }) => {
  let entryVisible = false
  await page.route('**/api/hub/rendezvous/config*', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      ok: true,
      enabled: true,
      entry_visible: entryVisible,
      load_level: 'normal',
      max_peers_per_room: 6,
      retry_after: 15,
      message: '',
    }),
  }))
  await prepareAuthenticatedPage(page, request)

  await page.goto('/#/overview')
  await expect(page.getByRole('button', { name: '联机冒险' })).toHaveCount(0)

  entryVisible = true
  await page.reload()
  await expect(page.locator('.adventure-library')).toBeVisible()
  const peerButton = page.getByRole('button', { name: '联机冒险' })
  await expect(peerButton).toBeVisible()
  const overviewActions = page.locator('.overview-actions')
  const importButton = overviewActions.getByRole('button', { name: '导入存档' })
  const createButton = overviewActions.getByRole('button', { name: '创建新冒险' })
  const [peerBox, importBox, createBox] = await Promise.all([
    peerButton.boundingBox(),
    importButton.boundingBox(),
    createButton.boundingBox(),
  ])
  expect(peerBox).not.toBeNull()
  expect(importBox).not.toBeNull()
  expect(createBox).not.toBeNull()
  expect(peerBox!.x).toBeLessThan(importBox!.x)
  expect(importBox!.x).toBeLessThan(createBox!.x)
  expect(Math.abs(peerBox!.y - importBox!.y)).toBeLessThanOrEqual(1)
  expect(Math.abs(importBox!.y - createBox!.y)).toBeLessThanOrEqual(1)

  const sortField = page.locator('.save-sort-field')
  const selectAll = page.getByRole('button', { name: '全选' })
  const invert = page.getByRole('button', { name: '反选' })
  const clear = page.getByRole('button', { name: '取消选择' })
  const exportAll = page.getByRole('button', { name: '批量导出' })
  await expect(sortField).toBeVisible()
  if ((page.viewportSize()?.width || 1000) <= 800) {
    const [sortBox, allBox, invertBox, clearBox, exportBox] = await Promise.all([
      sortField.boundingBox(),
      selectAll.boundingBox(),
      invert.boundingBox(),
      clear.boundingBox(),
      exportAll.boundingBox(),
    ])
    expect(sortBox).not.toBeNull()
    expect(allBox).not.toBeNull()
    expect(invertBox).not.toBeNull()
    expect(clearBox).not.toBeNull()
    expect(exportBox).not.toBeNull()
    expect(sortBox!.width).toBeGreaterThan(allBox!.width + invertBox!.width)
    expect(Math.abs(allBox!.y - invertBox!.y)).toBeLessThanOrEqual(1)
    expect(Math.abs(clearBox!.y - exportBox!.y)).toBeLessThanOrEqual(1)
    expect(Math.abs(allBox!.height - clearBox!.height)).toBeLessThanOrEqual(1)
  }

  await peerButton.click()
  await expect(page.getByText('实验性功能').first()).toBeVisible()
  await expect(page.getByRole('heading', { name: '和朋友一起进入冒险' })).toBeVisible()
  await page.getByRole('button', { name: '创建或加入' }).click()
  await expect(page.getByRole('heading', { name: '创建或加入多人游戏' })).toBeVisible()
  await expect(page.getByText('P2P 多人冒险')).toHaveCount(0)
  await expect(page.getByText('不会发送、接收或显示自定义测试文本。')).toHaveCount(0)
  const [setupBox, statusBox] = await Promise.all([
    page.locator('.peer-setup').boundingBox(),
    page.locator('.peer-status').boundingBox(),
  ])
  expect(setupBox).not.toBeNull()
  expect(statusBox).not.toBeNull()
  if ((page.viewportSize()?.width || 1000) > 760) {
    expect(statusBox!.height).toBeLessThan(setupBox!.height)
  }
})

test('direct share route follows browser locale and exposes a language switch', async ({ browser }) => {
  const context = await browser.newContext({ locale: 'en-US' })
  const page = await context.newPage()
  await page.goto('/#/join?game=missing&share=1')

  const locale = page.locator('.join-actions select')
  await expect(locale).toHaveValue('en')
  await locale.selectOption('zh-CN')
  await expect(locale).toHaveValue('zh-CN')
  await context.close()
})

test('solo save asks before conversion and only then creates an online room', async ({ page, request }) => {
  let converted = false
  let roomRequests = 0
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/games') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          games: [{
            game_key: 'web|solo-room|web_bot',
            world_name: '单人测试存档',
            solo_mode: true,
            player_count: 1,
            max_players: 6,
          }],
        }),
      })
      return
    }
    if (url.pathname.endsWith('/mode')) {
      converted = true
      expect(route.request().postDataJSON()).toEqual({ solo: false })
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, solo_mode: false }),
      })
      return
    }
    if (url.pathname === '/api/hub/rendezvous/config') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          enabled: true,
          entry_visible: true,
          load_level: 'normal',
          max_peers_per_room: 6,
          retry_after: 15,
          message: '',
        }),
      })
      return
    }
    if (url.pathname === '/api/hub/rendezvous/rooms') {
      roomRequests += 1
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          protocol_version: 2,
          topology: 'host-star',
          room_code: 'ABCDEFGH',
          host_peer_id: 'h_abcdefghijk',
          host_token: 'host-token',
          invitations: [{ peer_id: 'p_abcdefghijk', token: 'guest-token' }],
          expires_at: '2026-08-21T12:05:00+00:00',
          websocket_url: 'ws://127.0.0.1:9/v1/rendezvous/rooms/ABCDEFGH/ws',
        }),
      })
      return
    }
    await route.continue()
  })
  await prepareAuthenticatedPage(page, request)
  await page.goto('/#/peer')
  await page.getByLabel('要开放的多人冒险').selectOption('web|solo-room|web_bot')
  await expect(page.getByLabel('要开放的多人冒险')).toContainText('单人存档，创建时转换')
  await page.getByLabel('STUN 服务').selectOption('none')
  await page.locator('.peer-direct-consent input').check()
  await page.getByRole('button', { name: '创建临时直连房间' }).click()
  await expect(page.getByText('转换为多人存档？')).toBeVisible()
  expect(converted).toBe(false)
  expect(roomRequests).toBe(0)
  await page.getByRole('button', { name: '转换并创建房间' }).click()
  await expect.poll(() => converted).toBe(true)
  await expect.poll(() => roomRequests).toBe(1)
  await expect(page.locator('.peer-invite textarea')).toHaveValue(/^DFP2-/)
})

test('a full save can issue a direct-connect code for an occupied character', async ({ page, request }) => {
  let requestedPeerCount = 0
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/games') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          games: [{
            game_key: 'web|full-room|web_bot',
            world_name: '满员存档',
            solo_mode: false,
            gm_uid: 'gm_owner',
            player_count: 2,
            max_players: 2,
          }],
        }),
      })
      return
    }
    if (url.pathname.endsWith('/characters')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          players: [
            { user_id: 'gm_owner', character_name: '房主' },
            { user_id: 'player_nightingale', character_name: '夜莺' },
          ],
        }),
      })
      return
    }
    if (url.pathname === '/api/hub/rendezvous/config') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          enabled: true,
          entry_visible: true,
          load_level: 'normal',
          max_peers_per_room: 6,
          retry_after: 15,
          message: '',
        }),
      })
      return
    }
    if (url.pathname === '/api/hub/rendezvous/rooms') {
      requestedPeerCount = Number(route.request().postDataJSON().peer_count)
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          protocol_version: 2,
          topology: 'host-star',
          room_code: 'FULLROOM',
          host_peer_id: 'h_abcdefghijk',
          host_token: 'host-token',
          invitations: [{
            peer_id: 'p_abcdefghijk',
            token: 'guest-token-with-at-least-thirty-two-characters',
          }],
          expires_at: '2026-08-22T23:59:00+08:00',
          websocket_url: 'ws://127.0.0.1:9/v1/rendezvous/rooms/FULLROOM/ws',
        }),
      })
      return
    }
    await route.continue()
  })

  await prepareAuthenticatedPage(page, request)
  await page.goto('/#/peer')
  await expect(page.getByLabel('要开放的多人冒险')).toContainText('满员存档')
  await expect(page.getByText('夜莺', { exact: true }).first()).toBeVisible()
  await expect(page.getByText(/存档席位 2\/2：可重新邀请 1 个已有角色/)).toBeVisible()
  await expect(page.locator('.peer-room-batch')).toContainText('开房后一次生成 1 枚 P2P 链接码')
  await expect(page.locator('.peer-room-batch')).toContainText('夜莺')
  await page.getByLabel('STUN 服务').selectOption('none')
  await page.locator('.peer-direct-consent input').check()
  await page.getByRole('button', { name: '创建临时直连房间' }).click()

  await expect.poll(() => requestedPeerCount).toBe(2)
  await expect(page.locator('.peer-invite-code-wrap > strong')).toHaveText('夜莺')
  await expect(page.locator('.peer-invite textarea')).toHaveValue(/^DFP2-/)
})
