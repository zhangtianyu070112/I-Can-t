import { expect, test } from '@playwright/test'

async function openDemo(page: import('@playwright/test').Page, path: string) {
  await page.addInitScript(() => {
    sessionStorage.setItem('zx-resource-agent-authed', '1')
    localStorage.setItem('las_student_id', 'demo')
  })
  await page.goto(path, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => undefined)
}

test.describe('roadshow interaction QA', () => {
  test('knowledge graph zoom, keyboard navigation and fullscreen are usable', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error' && !/favicon|ResizeObserver loop|status of 503/i.test(message.text())) consoleErrors.push(message.text())
    })

    await page.setViewportSize({ width: 1440, height: 900 })
    await openDemo(page, '/knowledge')
    await expect(page.locator('.kg-node').first()).toBeVisible({ timeout: 15_000 })

    const zoomValue = page.locator('.graph-zoom-value')
    await expect(zoomValue).toHaveText('100%')
    await page.getByRole('button', { name: '放大图谱' }).click()
    await expect(zoomValue).toHaveText('110%')
    await page.getByRole('button', { name: '恢复图谱百分之百' }).click()
    await expect(zoomValue).toHaveText('100%')

    const graphScroll = page.locator('.graph-scroll')
    await graphScroll.hover()
    await page.keyboard.down('Control')
    await page.mouse.wheel(0, -120)
    await page.keyboard.up('Control')
    await expect(zoomValue).toHaveText('110%')
    await page.keyboard.press('0')
    await expect(zoomValue).toHaveText('100%')

    const selectedNode = page.locator('.kg-node[aria-selected="true"]').first()
    await selectedNode.focus()
    await expect(selectedNode).toBeFocused()
    await page.keyboard.press('ArrowRight')
    await expect(page.locator('.kg-node:focus-visible')).toHaveCount(1)
    await page.keyboard.press('Home')
    await expect(page.locator('.kg-node[aria-selected="true"]').first()).toHaveAttribute('aria-label', /课程入口/)

    const fullscreenButton = page.getByRole('button', { name: /进入图谱全屏/ })
    await fullscreenButton.click()
    await expect(page.locator('.knowledge-course-map')).toHaveClass(/fullscreen/)
    await page.keyboard.press('Escape')
    await expect(page.locator('.knowledge-course-map')).not.toHaveClass(/fullscreen/)
    await expect(page.getByRole('button', { name: /进入图谱全屏/ })).toBeFocused()

    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(700)
    const filterToggle = page.getByRole('button', { name: '筛选' })
    await filterToggle.click()
    await expect(page.locator('#knowledge-filter-panel')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.locator('#knowledge-filter-panel')).toBeHidden()

    const overflow = await page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth))
    expect(overflow).toBeLessThanOrEqual(1)
    expect(consoleErrors).toEqual([])
  })

  test('wrong-book galaxy supports focus, keyboard zoom and label selection', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error' && !/favicon|ResizeObserver loop/i.test(message.text())) consoleErrors.push(message.text())
    })

    await page.setViewportSize({ width: 1440, height: 900 })
    await openDemo(page, '/exercise')
    await page.getByRole('button', { name: /错题本/ }).first().click()
    await page.getByRole('button', { name: /进入历史星系/ }).click()

    const canvas = page.locator('canvas[aria-label="错题标签星系"]')
    await expect(canvas).toBeVisible({ timeout: 15_000 })
    await expect(canvas).toHaveAttribute('tabindex', '0')
    await expect(canvas).toHaveAttribute('role', 'img')
    await canvas.focus()
    await page.keyboard.press('+')
    await expect(page.locator('.galaxy-zoom-tools output')).toHaveText('108%')
    await page.keyboard.press('0')
    await expect(page.locator('.galaxy-zoom-tools output')).toHaveText('100%')

    await page.getByRole('button', { name: '放大错题标签星系' }).click()
    await expect(page.locator('.galaxy-zoom-tools output')).toHaveText('108%')
    await page.getByRole('button', { name: '恢复错题标签星系百分之百' }).click()
    await expect(page.locator('.galaxy-zoom-tools output')).toHaveText('100%')

    const tagButton = page.locator('.tag-galaxy-clusters button').first()
    if (await tagButton.count()) {
      await tagButton.click()
      await expect(page.locator('.tag-galaxy-inspector strong')).toContainText((await tagButton.innerText()).trim())
    }
    expect(consoleErrors).toEqual([])
  })

  test('roadshow routes expose named buttons with safe types and no mobile overflow', async ({ page }) => {
    test.setTimeout(120_000)
    const consoleErrors: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error' && !/favicon|ResizeObserver loop/i.test(message.text())) consoleErrors.push(message.text())
    })

    await page.setViewportSize({ width: 390, height: 844 })
    for (const path of ['/', '/profile', '/workshop', '/path', '/exercise', '/knowledge', '/multimodal', '/tutor', '/evaluate']) {
      await openDemo(page, path)
      const violations = await page.locator('button:visible').evaluateAll((buttons) => buttons.flatMap((button) => {
        const element = button as HTMLButtonElement
        const name = (element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent || '').replace(/\s+/g, ' ').trim()
        const type = element.getAttribute('type')
        return [
          !name ? 'unnamed button' : '',
          !type || !['button', 'submit', 'reset'].includes(type) ? `invalid type ${type || '(missing)'}` : '',
        ].filter(Boolean)
      })).then((items) => items.map((item) => `${path}: ${item}`))
      expect(violations).toEqual([])
      const overflow = await page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth))
      expect(overflow, `${path}: document overflow`).toBeLessThanOrEqual(1)
    }
    expect(consoleErrors).toEqual([])
  })

  test('an unavailable overview API keeps the path page actionable', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error' && !/favicon|ResizeObserver loop|status of 503/i.test(message.text())) consoleErrors.push(message.text())
    })
    await page.route('**/api/path/overview**', (route) => route.fulfill({
      status: 503,
      contentType: 'text/plain',
      body: 'upstream unavailable',
    }))
    await openDemo(page, '/path')
    await expect(page.locator('.shot-notice.is-error')).toContainText(/HTTP 503|学习路径加载失败/)
    await expect(page.getByRole('button', { name: '重新加载' })).toBeVisible()
    await expect(page.locator('#app')).toBeVisible()
    expect(consoleErrors).toEqual([])
  })
})
