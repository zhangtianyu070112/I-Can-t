import { expect, test } from '@playwright/test'

const phase = process.env.AUDIT_PHASE || 'before'
const routes = [
  ['/', 'home'],
  ['/profile', 'profile'],
  ['/workshop', 'workshop'],
  ['/exercise', 'exercise'],
  ['/knowledge', 'knowledge'],
  ['/multimodal', 'multimodal'],
  ['/path', 'path'],
  ['/tutor', 'tutor'],
  ['/evaluate', 'evaluate'],
] as const

test('capture every user-facing page and report typography density', async ({ page }) => {
  test.setTimeout(180_000)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript(() => {
    sessionStorage.setItem('zx-resource-agent-authed', '1')
    localStorage.setItem('las_student_id', sessionStorage.getItem('acceptance_student_id') || 'demo_user_001')
  })
  await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30_000 })

  for (const [route, slug] of routes) {
    const studentId = route === '/workshop'
      ? 'learner-58ce105b-fa0b-4672-bbdc-497494984b79'
      : route === '/exercise'
        ? 'acceptance-exercise'
        : 'demo_user_001'
    await page.evaluate((id) => {
      sessionStorage.setItem('acceptance_student_id', id)
      localStorage.setItem('las_student_id', id)
    }, studentId)
    await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 30_000 })
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => undefined)
    await expect(page.locator('.portal-main')).toBeVisible()
    if (route === '/knowledge') {
      await page.locator('.graph-loading').waitFor({ state: 'hidden', timeout: 30_000 }).catch(() => undefined)
    }

    const metrics = await page.locator('.portal-main').evaluate((root) => {
      const visible = Array.from(root.querySelectorAll<HTMLElement>('h1,h2,h3,p,small,span,button,a,label,dt,dd,strong'))
        .filter((element) => {
          const rect = element.getBoundingClientRect()
          const style = getComputedStyle(element)
          return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && Boolean(element.textContent?.trim())
        })
      const fontSizes = visible.map((element) => Number.parseFloat(getComputedStyle(element).fontSize)).filter(Number.isFinite)
      const contentBlocks = Array.from(root.children).map((element) => element.getBoundingClientRect())
      const contentBottom = Math.max(0, ...contentBlocks.map((rect) => rect.bottom))
      return {
        route: location.pathname,
        documentWidthOverflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
        tinyTextCount: fontSizes.filter((size) => size < 11).length,
        minimumFontSize: fontSizes.length ? Math.min(...fontSizes) : 0,
        tinySamples: visible.filter((element) => Number.parseFloat(getComputedStyle(element).fontSize) < 11).slice(0, 12).map((element) => ({
          tag: element.tagName.toLowerCase(),
          className: element.className,
          text: element.textContent?.trim().slice(0, 36),
          size: getComputedStyle(element).fontSize,
        })),
        rootHeight: root.getBoundingClientRect().height,
        documentHeight: document.documentElement.scrollHeight,
        unusedFirstScreenSpace: Math.max(0, innerHeight - contentBottom),
      }
    })
    console.log(`[FINAL-AUDIT] ${JSON.stringify(metrics)}`)
    await page.screenshot({
      path: `test-results/final-acceptance/${phase}/${slug}.png`,
      fullPage: true,
      animations: 'disabled',
    })
  }
})
