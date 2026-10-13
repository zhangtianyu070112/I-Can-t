import { expect, test, type Locator, type Page } from '@playwright/test'

const EMPTY_STUDENT_ID = 'density-audit-empty-user-v1'
const viewport = { width: 2048, height: 1152 }

type DensityMetrics = {
  containerHeight: number
  occupiedHeight: number
  contentOccupancyRatio: number
  blankRatio: number
  largestBlankGap: number
  largestBlankGapRatio: number
  itemCount: number
}

type FootprintMetrics = {
  availableHeight: number
  meaningfulBottom: number
  viewportEffectiveCoverage: number
  viewportBlankRatio: number
}

async function openExercise(page: Page) {
  await page.setViewportSize(viewport)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript((studentId) => {
    sessionStorage.setItem('zx-resource-agent-authed', '1')
    localStorage.setItem('las_student_id', studentId)
    localStorage.removeItem(`exercise_active_question_banks:${studentId}`)
  }, EMPTY_STUDENT_ID)
  await page.goto('/exercise', { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => undefined)
  await expect(page.locator('.exercise-practice-center')).toBeVisible()
}

async function measureVerticalDensity(container: Locator, selectors: string[]): Promise<DensityMetrics> {
  return container.evaluate((root, itemSelectors) => {
    const containerRect = root.getBoundingClientRect()
    const top = Math.max(0, containerRect.top)
    const bottom = Math.min(window.innerHeight, containerRect.bottom)
    const height = Math.max(1, bottom - top)
    const padding = 7
    const seen = new Set<Element>()
    const intervals: Array<[number, number]> = []

    for (const selector of itemSelectors) {
      for (const element of root.querySelectorAll<HTMLElement>(selector)) {
        if (seen.has(element)) continue
        seen.add(element)
        const style = getComputedStyle(element)
        const rect = element.getBoundingClientRect()
        if (
          style.display === 'none'
          || style.visibility === 'hidden'
          || Number(style.opacity) === 0
          || rect.width <= 0
          || rect.height <= 0
          || rect.bottom <= top
          || rect.top >= bottom
        ) continue
        intervals.push([
          Math.max(top, rect.top - padding),
          Math.min(bottom, rect.bottom + padding),
        ])
      }
    }

    intervals.sort((a, b) => a[0] - b[0])
    const merged: Array<[number, number]> = []
    for (const interval of intervals) {
      const current = merged.at(-1)
      if (!current || interval[0] > current[1]) merged.push([...interval])
      else current[1] = Math.max(current[1], interval[1])
    }

    const occupiedHeight = merged.reduce((sum, interval) => sum + interval[1] - interval[0], 0)
    let cursor = top
    let largestBlankGap = 0
    for (const interval of merged) {
      largestBlankGap = Math.max(largestBlankGap, interval[0] - cursor)
      cursor = Math.max(cursor, interval[1])
    }
    largestBlankGap = Math.max(largestBlankGap, bottom - cursor)
    const ratio = (value: number) => Number((value / height).toFixed(3))

    return {
      containerHeight: Math.round(height),
      occupiedHeight: Math.round(occupiedHeight),
      contentOccupancyRatio: ratio(occupiedHeight),
      blankRatio: Number((1 - occupiedHeight / height).toFixed(3)),
      largestBlankGap: Math.round(largestBlankGap),
      largestBlankGapRatio: ratio(largestBlankGap),
      itemCount: intervals.length,
    }
  }, selectors)
}

async function measureFirstScreenFootprint(page: Page, selectors: string[]): Promise<FootprintMetrics> {
  return page.locator('.portal-main').evaluate((portal, meaningfulSelectors) => {
    const portalTop = Math.max(0, portal.getBoundingClientRect().top)
    const viewportBottom = window.innerHeight
    const availableHeight = Math.max(1, viewportBottom - portalTop)
    let meaningfulBottom = portalTop

    for (const selector of meaningfulSelectors) {
      for (const element of portal.querySelectorAll<HTMLElement>(selector)) {
        const style = getComputedStyle(element)
        const rect = element.getBoundingClientRect()
        if (
          style.display === 'none'
          || style.visibility === 'hidden'
          || Number(style.opacity) === 0
          || rect.width <= 0
          || rect.height <= 0
          || rect.bottom <= portalTop
          || rect.top >= viewportBottom
        ) continue
        meaningfulBottom = Math.max(meaningfulBottom, Math.min(viewportBottom, rect.bottom))
      }
    }

    const occupancy = (meaningfulBottom - portalTop) / availableHeight
    return {
      availableHeight: Math.round(availableHeight),
      meaningfulBottom: Math.round(meaningfulBottom),
      viewportEffectiveCoverage: Number(occupancy.toFixed(3)),
      viewportBlankRatio: Number((1 - occupancy).toFixed(3)),
    }
  }, selectors)
}

function report(state: string, zone: string, metrics: DensityMetrics | Record<string, number>) {
  console.log(`[DENSITY-AUDIT] ${JSON.stringify({ state, zone, viewport, ...metrics })}`)
}

test.describe('2048x1152 exercise density regression', () => {
  test('training overview does not stretch a short form over an empty viewport', async ({ page }) => {
    await openExercise(page)
    await page.locator('.practice-workshop-nav button:visible').first().click()
    const panel = page.locator('.workshop-content > .studio-panel').first()
    await expect(panel).toBeVisible()

    const metrics = await measureVerticalDensity(panel, [
      ':scope > .studio-panel-header',
      ':scope > .studio-panel-body > .studio-empty',
      ':scope > .studio-panel-body > .studio-grid',
      ':scope > .studio-panel-body > input',
      ':scope > .studio-panel-body > .practice-config-summary',
      ':scope > .studio-panel-body > .stage-steps',
    ])
    const footprint = await measureFirstScreenFootprint(page, [
      '.workshop-content > .studio-panel > .studio-panel-header',
      '.workshop-content > .studio-panel > .studio-panel-body > .studio-empty',
      '.workshop-content > .studio-panel > .studio-panel-body > .studio-grid',
      '.workshop-content > .studio-panel > .studio-panel-body > input',
      '.workshop-content > .studio-panel > .studio-panel-body > .practice-config-summary',
      '.workshop-content > .studio-panel > .studio-panel-body > .stage-steps',
    ])
    report('course', 'main-panel', metrics)
    report('course', 'first-screen-footprint', footprint)
    await page.screenshot({ path: 'test-results/final-density/course.png', animations: 'disabled' })

    expect(metrics.contentOccupancyRatio, '课程选择主面板首屏内容占用率应至少 62%').toBeGreaterThanOrEqual(0.62)
    expect(metrics.largestBlankGapRatio, '课程选择主面板不得留下超过 24% 高度的连续空白').toBeLessThanOrEqual(0.24)
    expect(footprint.viewportEffectiveCoverage, '课程总览的有效内容应覆盖至少 78% 的可用首屏高度').toBeGreaterThanOrEqual(0.78)
  })

  test('empty smart-practice state uses both main and progress columns efficiently', async ({ page }) => {
    await openExercise(page)
    const mainPanel = page.locator('.exercise-practice-center .practice-main-panel')
    const emptyState = mainPanel.locator('.exercise-empty')
    const progressPanel = page.locator('.exercise-practice-center .exercise-nav-card')
    await expect(emptyState).toBeVisible()

    const mainMetrics = await measureVerticalDensity(mainPanel, [
      ':scope > .exercise-hero',
      ':scope > .practice-progress-line',
      ':scope > .exercise-empty',
      ':scope > .exercise-workbench',
    ])
    const emptyMetrics = await measureVerticalDensity(emptyState, [
      ':scope > .exercise-empty-mark',
      ':scope > strong',
      ':scope > span',
      ':scope > .exercise-empty-config',
      ':scope > .exercise-empty-preflight',
      ':scope > .exercise-empty-steps',
      ':scope > .exercise-empty-outcomes',
      ':scope > .exercise-empty-primary',
    ])
    const progressMetrics = await measureVerticalDensity(progressPanel, [
      ':scope > .exercise-side-head',
      ':scope > .practice-progress-summary',
      ':scope > .exercise-compact-empty',
      ':scope > .exercise-question-nav',
      ':scope > .practice-progress-hint',
    ])
    const footprint = await measureFirstScreenFootprint(page, [
      '.practice-main-panel > .exercise-hero',
      '.practice-main-panel > .practice-progress-line',
      '.practice-main-panel > .exercise-empty > *',
      '.practice-main-panel > .exercise-empty > .exercise-empty-config',
      '.practice-main-panel > .exercise-workbench',
      '.exercise-nav-card > .exercise-side-head',
      '.exercise-nav-card > .practice-progress-summary',
      '.exercise-nav-card > .exercise-compact-empty',
      '.exercise-nav-card > .exercise-question-nav',
    ])
    report('diagnosis-empty', 'main-panel', mainMetrics)
    report('diagnosis-empty', 'empty-state', emptyMetrics)
    report('diagnosis-empty', 'progress-panel', progressMetrics)
    report('diagnosis-empty', 'first-screen-footprint', footprint)
    await page.screenshot({ path: 'test-results/final-density/diagnosis-empty.png', animations: 'disabled' })

    expect(mainMetrics.contentOccupancyRatio, '空题态主面板首屏内容占用率应至少 68%').toBeGreaterThanOrEqual(0.68)
    expect(emptyMetrics.contentOccupancyRatio, '空题引导内部不应靠固定高度制造留白').toBeGreaterThanOrEqual(0.62)
    expect(progressMetrics.contentOccupancyRatio, '答题进度栏首屏内容占用率应至少 58%').toBeGreaterThanOrEqual(0.58)
    expect(progressMetrics.largestBlankGapRatio, '答题进度栏中部不得出现超过 24% 的断层').toBeLessThanOrEqual(0.24)
    expect(footprint.viewportEffectiveCoverage, '空题态有效内容应覆盖至少 78% 的可用首屏高度').toBeGreaterThanOrEqual(0.78)
  })

  test('empty wrong-book uses one dense next-step flow and hides the zero-value radar', async ({ page }) => {
    await openExercise(page)
    await page.locator('.practice-workshop-nav button:visible').nth(3).click()
    const emptyState = page.locator('.wrongbook-empty-state')
    await expect(emptyState).toBeVisible()
    await expect(page.locator('.wrongbook-layout')).toHaveCount(0)
    await expect(page.locator('.wrongbook-radar')).toHaveCount(0)

    const metrics = await measureVerticalDensity(emptyState, [
      ':scope > .wrongbook-empty-state__intro',
      ':scope > .wrongbook-empty-flow',
      ':scope > .wrongbook-empty-state__actions',
    ])
    const footprint = await measureFirstScreenFootprint(page, [
      '.workshop-content > .studio-panel > .studio-panel-header',
      '.wrongbook-empty-state > .wrongbook-empty-state__intro',
      '.wrongbook-empty-state > .wrongbook-empty-flow',
      '.wrongbook-empty-state > .wrongbook-empty-state__actions',
    ])
    report('wrong-book-empty', 'empty-state', metrics)
    report('wrong-book-empty', 'first-screen-footprint', footprint)
    await page.screenshot({ path: 'test-results/final-density/wrong-book-empty.png', animations: 'disabled' })

    expect(metrics.contentOccupancyRatio, '空错题本引导内部内容占用率应至少 72%').toBeGreaterThanOrEqual(0.72)
    expect(metrics.largestBlankGapRatio, '空错题本引导不得出现超过 20% 的连续纵向留白').toBeLessThanOrEqual(0.2)
    expect(footprint.viewportEffectiveCoverage, '空错题本有效内容应覆盖至少 78% 的可用首屏高度').toBeGreaterThanOrEqual(0.78)
  })
})

test('knowledge concept branches use semantic SVG icons instead of repeated 点 glyphs', async ({ page }) => {
  await page.setViewportSize(viewport)
  await page.addInitScript(() => {
    sessionStorage.setItem('zx-resource-agent-authed', '1')
    localStorage.setItem('las_student_id', 'demo_user_001')
  })
  await page.goto('/knowledge', { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await page.locator('.graph-loading').waitFor({ state: 'hidden', timeout: 30_000 }).catch(() => undefined)
  const conceptIcons = page.locator('.kg-node.type-concept .node-icon')
  await expect(conceptIcons.first()).toBeVisible()

  const iconAudit = await conceptIcons.evaluateAll((icons) => ({
    count: icons.length,
    withoutSvg: icons.filter((icon) => !icon.querySelector('svg')).length,
    pointGlyphs: icons.filter((icon) => icon.textContent?.trim() === '点').length,
    distinctSemanticIcons: new Set(icons.map((icon) => icon.getAttribute('data-concept-icon')).filter(Boolean)).size,
  }))
  console.log(`[KNOWLEDGE-ICON-AUDIT] ${JSON.stringify(iconAudit)}`)
  await page.screenshot({ path: 'test-results/final-density/knowledge-semantic-icons.png', animations: 'disabled' })

  expect(iconAudit.count).toBeGreaterThan(0)
  expect(iconAudit.withoutSvg).toBe(0)
  expect(iconAudit.pointGlyphs).toBe(0)
  expect(iconAudit.distinctSemanticIcons).toBeGreaterThanOrEqual(Math.min(3, iconAudit.count))
})
