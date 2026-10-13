import { expect, type Page, test } from '@playwright/test'

const allRoutes = ['/profile', '/workshop', '/exercise', '/knowledge', '/multimodal', '/path', '/tutor', '/evaluate']
const routes = process.env.BUTTON_ROUTE ? [process.env.BUTTON_ROUTE] : allRoutes

async function openAsFreshLearner(page: Page, route: string) {
  await page.addInitScript(() => {
    sessionStorage.setItem('zx-resource-agent-authed', '1')
    localStorage.setItem('las_student_id', 'button-contract-learner')
    localStorage.removeItem('multimodal-chat-sessions-v2')
  })
  await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => undefined)
  await expect(page.locator('.portal-main')).toBeVisible()
}

async function signature(page: Page) {
  return page.locator('.portal-main').evaluate((element) => ({
    html: element.innerHTML,
    controls: Array.from(element.querySelectorAll('input, textarea, select')).map((control) => {
      const input = control as HTMLInputElement
      return `${input.value}|${input.checked}|${input.disabled}`
    }),
  }))
}

function requiresProcessingEvidence(label: string) {
  return /分析|更新画像|刷新证据|生成|提交|评估|进化|规划|保存|反馈|有帮助|不匹配|删除|清空|重试|重新回答|完成考试|提交答案|generate|analyse|analyze|evaluate|submit|save|refresh evidence/i.test(label)
}

test('every initially visible enabled page button produces an observable action', async ({ page }) => {
  test.setTimeout(240_000)

  for (const route of routes) {
    await openAsFreshLearner(page, route)
    const initialButtons = page.locator('.portal-main button:visible:not(:disabled)')
    const count = await initialButtons.count()

    for (let index = 0; index < count; index += 1) {
      await openAsFreshLearner(page, route)
      const buttons = page.locator('.portal-main button:visible:not(:disabled)')
      if (index >= await buttons.count()) continue
      const button = buttons.nth(index)
      const label = ((await button.innerText().catch(() => '')) || await button.getAttribute('aria-label') || `button-${index}`).trim().replace(/\s+/g, ' ')
      const actionKind = await button.getAttribute('data-action-kind')
      const alreadyActive = await button.evaluate((element) => (
        element.getAttribute('aria-pressed') === 'true'
        || element.getAttribute('aria-selected') === 'true'
        || ['active', 'selected', 'is-active', 'current'].some((name) => element.classList.contains(name))
      ))

      await test.step(`${route} :: ${label.slice(0, 50)}`, async () => {
        const before = await signature(page)
        const beforeUrl = page.url()
        let apiRequest = false
        let fileChooser = false
        let download = false
        let popup = false

        const onRequest = (request: { url(): string }) => { if (request.url().includes('/api/')) apiRequest = true }
        page.on('request', onRequest)
        page.once('filechooser', () => { fileChooser = true })
        page.once('download', () => { download = true })
        page.once('popup', () => { popup = true })

        await button.click({ timeout: 15_000, noWaitAfter: true })
        await page.waitForTimeout(700)
        const after = await signature(page)
        page.off('request', onRequest)

        const changed = JSON.stringify(before) !== JSON.stringify(after)
        const navigated = beforeUrl !== page.url()
        const processingEvidence = apiRequest || fileChooser || download || popup || navigated
        if (actionKind !== 'compose' && requiresProcessingEvidence(label)) {
          expect(
            processingEvidence,
            `Processing button did not call an API or produce an external result: ${route} :: ${label}`,
          ).toBeTruthy()
        } else {
          expect(
            alreadyActive || processingEvidence || changed,
            `Button produced no observable action: ${route} :: ${label}`,
          ).toBeTruthy()
        }
      })
    }
  }
})
