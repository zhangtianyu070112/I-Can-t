import { expect, type Page, test } from '@playwright/test'

const routes = [
  { path: '/profile', slug: 'profile', title: '用户画像中枢', root: '.competition-page' },
  { path: '/workshop', slug: 'workshop', title: /资源工坊/, root: '.competition-page' },
  { path: '/knowledge', slug: 'knowledge', title: /知识图谱|操作系统实现之路/, root: '.knowledge-course-map' },
  { path: '/path', slug: 'path', title: /本周学习路径/, root: '.competition-page' },
  { path: '/tutor', slug: 'tutor', title: '实时视频辅导', root: '.competition-page' },
  { path: '/evaluate', slug: 'evaluate', title: /学习效果评估与策略进化/, root: '.competition-page' },
] as const

const viewports = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '1280x720', width: 1280, height: 720 },
  { label: '768x1024', width: 768, height: 1024 },
  { label: '390x844', width: 390, height: 844 },
] as const

async function login(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  const loginButton = page.getByRole('button', { name: /登录并进入系统/ })
  if (await loginButton.isVisible().catch(() => false)) {
    await page.getByPlaceholder('手机号').fill('10000000000')
    await page.getByPlaceholder('密码').fill('demo123')
    await page.getByPlaceholder('验证码').fill('2VV3')
    await loginButton.click()
    await expect(page.locator('.login-gate')).toBeHidden()
  }
}

for (const viewport of viewports) {
  test(`competition pages pass responsive QA at ${viewport.label}`, async ({ page }) => {
    const consoleErrors: string[] = []
    const failedApis: string[] = []

    page.on('console', (message) => {
      if (message.type() !== 'error' || /favicon|ResizeObserver loop/i.test(message.text())) return
      consoleErrors.push(message.text())
    })
    page.on('response', (response) => {
      if (response.url().includes('/api/') && response.status() >= 500) {
        failedApis.push(`${response.status()} ${response.url()}`)
      }
    })

    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await login(page)

    for (const route of routes) {
      await page.goto(route.path, { waitUntil: 'domcontentloaded' })
      await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => undefined)
      const root = page.locator(route.root)
      await expect(root).toBeVisible()
      await expect(root.getByRole('heading', { level: 1, name: route.title })).toBeVisible()

      const layout = await root.evaluate((pageRoot) => {
        const rect = pageRoot.getBoundingClientRect()
        const title = pageRoot.querySelector<HTMLElement>('h1')
        const unnamedControls = Array.from(
          pageRoot.querySelectorAll<HTMLElement>('button, a'),
        ).filter((element) => {
          const bounds = element.getBoundingClientRect()
          if (!bounds.width || !bounds.height) return false
          const name = element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent || ''
          return !name.trim()
        }).length
        return {
          viewportWidth: document.documentElement.clientWidth,
          documentOverflow: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
          rootLeft: rect?.left ?? -1,
          rootRight: rect?.right ?? Number.POSITIVE_INFINITY,
          rootWidthRatio: rect.width / document.documentElement.clientWidth,
          rootHeight: rect.height,
          titleFontSize: title ? Number.parseFloat(getComputedStyle(title).fontSize) : 0,
          unnamedControls,
        }
      })

      expect(layout.documentOverflow, `${route.path} document overflow at ${viewport.label}`).toBeLessThanOrEqual(1)
      expect(layout.rootLeft, `${route.path} root starts outside viewport`).toBeGreaterThanOrEqual(-1)
      expect(layout.rootRight, `${route.path} root ends outside viewport`).toBeLessThanOrEqual(layout.viewportWidth + 1)
      expect(layout.unnamedControls, `${route.path} has visible unnamed controls`).toBe(0)
      expect(layout.titleFontSize, `${route.path} title is oversized`).toBeLessThanOrEqual(38)
      expect(layout.rootHeight, `${route.path} does not use the available workspace`).toBeGreaterThanOrEqual(viewport.height * 0.62)
      if (viewport.width >= 1280) {
        expect(layout.rootWidthRatio, `${route.path} wastes too much horizontal space`).toBeGreaterThanOrEqual(0.9)
      }
      await expect(page.locator('body')).not.toContainText('Cannot read properties')
      await expect(page.locator('body')).not.toContainText('undefined')

      if (viewport.label === '1440x900') {
        const firstControl = root.locator('button:visible, a:visible').first()
        await firstControl.focus()
        const focusOutlineWidth = await firstControl.evaluate((element) => Number.parseFloat(getComputedStyle(element).outlineWidth))
        expect(focusOutlineWidth, `${route.path} keyboard focus is not visible`).toBeGreaterThanOrEqual(2)
      }

      if (route.path === '/knowledge') {
        await expect(root).toContainText('知识来源')
        await expect(root).toContainText('知识层级')
        await expect(root).toContainText('知识点详情')
        await expect(root).toContainText('上传电子教材')
      }

      await page.screenshot({
        path: `test-results/visual/after/${viewport.label}/${route.slug}.png`,
        fullPage: true,
        animations: 'disabled',
      })
    }

    expect(consoleErrors, `Console errors:\n${consoleErrors.join('\n')}`).toEqual([])
    expect(failedApis, `API failures:\n${failedApis.join('\n')}`).toEqual([])
  })
}
