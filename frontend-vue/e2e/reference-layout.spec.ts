import { expect, test, type Page } from '@playwright/test'

const pages = [
  { path: '/profile', root: '.profile-command-page' },
  { path: '/workshop', root: '.workshop-command-page' },
  { path: '/path', root: '.path-command-page' },
  { path: '/evaluate', root: '.evaluate-command-page' },
]

async function gotoAuthed(page: Page, path: string) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  const loginButton = page.getByRole('button', { name: /登录并进入系统/ })
  if (await loginButton.isVisible().catch(() => false)) {
    await page.getByPlaceholder('手机号').fill('10000000000')
    await page.getByPlaceholder('密码').fill('demo123')
    await page.getByPlaceholder('验证码').fill('2VV3')
    await loginButton.click()
    await expect(page.locator('.login-gate')).toBeHidden()
  }
  await page.goto(path, { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle')
}

test('reference workspaces use the first screen efficiently and keep text readable', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })

  for (const item of pages) {
    await gotoAuthed(page, item.path)
    const root = page.locator(item.root)
    await expect(root).toBeVisible()

    const metrics = await root.evaluate((element) => {
      const rootRect = element.getBoundingClientRect()
      const candidates = Array.from(element.querySelectorAll('p, small, label, button, a, dt, dd, strong, h1, h2, h3'))
      const tinyText = candidates.filter((node) => {
        const target = node as HTMLElement
        const rect = target.getBoundingClientRect()
        const style = getComputedStyle(target)
        return rect.width > 0
          && rect.height > 0
          && style.visibility !== 'hidden'
          && style.display !== 'none'
          && target.textContent?.trim()
          && Number.parseFloat(style.fontSize) < 10
      }).map((node) => ({
        text: node.textContent?.trim().slice(0, 32),
        fontSize: getComputedStyle(node).fontSize,
      }))

      return {
        scrollRatio: element.scrollHeight / window.innerHeight,
        widthRatio: rootRect.width / window.innerWidth,
        tinyText,
      }
    })

    expect(metrics.widthRatio, `${item.path} should use the desktop width`).toBeGreaterThanOrEqual(.94)
    expect(metrics.scrollRatio, `${item.path} should remain a compact first-screen workspace`).toBeLessThanOrEqual(1.35)
    expect(metrics.tinyText, `${item.path} contains unreadably small text`).toEqual([])

    if (item.path === '/profile') {
      const details = await root.evaluate((element) => {
        const avatar = element.querySelector('.shot-avatar-photo') as HTMLElement | null
        const interview = element.querySelector('.shot-interview')?.getBoundingClientRect()
        const matrix = element.querySelector('.shot-matrix')?.getBoundingClientRect()
        return {
          avatarSource: avatar ? getComputedStyle(avatar).backgroundImage : '',
          dimensionIcons: element.querySelectorAll('.shot-dimensions button > i svg').length,
          middleRatio: interview && matrix ? interview.width / matrix.width : 0,
          radarGridLevels: element.querySelectorAll('.shot-radar__grid polygon').length,
          radarAxes: element.querySelectorAll('.shot-radar__axes line').length,
          radarSeries: element.querySelectorAll('.shot-radar__series polygon').length,
          panelIcons: element.querySelectorAll('.shot-panel-icon').length,
          actionIcons: element.querySelectorAll('.shot-action-icon svg').length,
        }
      })
      expect(details.avatarSource).toContain('profile-reference-source.png')
      expect(details.dimensionIcons).toBe(6)
      expect(details.middleRatio).toBeGreaterThan(.72)
      expect(details.middleRatio).toBeLessThan(.9)
      expect(details.radarGridLevels).toBe(4)
      expect(details.radarAxes).toBe(6)
      expect(details.radarSeries).toBeGreaterThanOrEqual(1)
      expect(details.radarSeries).toBeLessThanOrEqual(2)
      expect(details.panelIcons).toBeGreaterThanOrEqual(7)
      expect(details.actionIcons).toBe(3)
    }

    if (item.path === '/workshop') {
      const details = await root.evaluate((element) => {
        const main = element.querySelector('.shot-workshop__main')?.getBoundingClientRect()
        const side = element.querySelector('.shot-workshop__side')?.getBoundingClientRect()
        const hiddenBrief = element.querySelector('.shot-brief-fields') as HTMLElement | null
        const orbit = element.querySelector('.shot-agent-orbit')
        const core = orbit?.querySelector('.orbit-core')?.getBoundingClientRect()
        const agentDistances = core
          ? Array.from(orbit?.querySelectorAll(':scope > i') || []).map((agent) => {
              const rect = agent.getBoundingClientRect()
              return Math.hypot(
                rect.left + rect.width / 2 - (core.left + core.width / 2),
                rect.top + rect.height / 2 - (core.top + core.height / 2),
              )
            })
          : []
        return {
          resourceIcons: element.querySelectorAll('.shot-type-grid button > i svg').length,
          activeTypes: element.querySelectorAll('.shot-type-grid button.active').length,
          agentSteps: element.querySelectorAll('.shot-progress li').length,
          cubeFaces: element.querySelectorAll('.orbit-core > b').length,
          cubeLabels: Array.from(element.querySelectorAll('.orbit-core :is(.cube-front,.cube-side) > span')).map((label) => label.textContent?.trim()),
          cubeFacesClipText: Array.from(element.querySelectorAll('.orbit-core :is(.cube-front,.cube-side)')).every((face) => getComputedStyle(face).overflow === 'hidden'),
          agentDistances,
          heroTitleIcons: element.querySelectorAll('.shot-workshop-copy h1 svg').length,
          recordStateIcons: element.querySelectorAll('.shot-record-grid > button > i svg').length,
          progressStateIcons: element.querySelectorAll('.shot-progress li > em svg').length,
          mainToSideRatio: main && side ? main.width / side.width : 0,
          briefFieldsHidden: hiddenBrief ? getComputedStyle(hiddenBrief).display === 'none' : false,
        }
      })
      expect(details.resourceIcons).toBe(6)
      expect(details.activeTypes).toBe(1)
      expect(details.agentSteps).toBe(0)
      expect(details.cubeFaces).toBe(3)
      expect(details.cubeLabels).toEqual(['AI', 'AI'])
      expect(details.cubeFacesClipText).toBe(true)
      expect(details.agentDistances).toHaveLength(5)
      expect(Math.max(...details.agentDistances)).toBeLessThanOrEqual(210)
      expect(details.heroTitleIcons).toBe(1)
      expect(details.recordStateIcons).toBe(0)
      expect(details.progressStateIcons).toBe(0)
      expect(details.mainToSideRatio).toBeGreaterThan(2.4)
      expect(details.mainToSideRatio).toBeLessThan(2.8)
      expect(details.briefFieldsHidden).toBe(true)
    }

    if (item.path === '/path') {
      const details = await root.evaluate((element) => {
        const avatar = element.querySelector('.shot-path-avatar-photo') as HTMLElement | null
        return {
          avatarSource: avatar ? getComputedStyle(avatar).backgroundImage : '',
          stages: element.querySelectorAll('.shot-route-track > button').length,
          activeStages: element.querySelectorAll('.shot-route-track > button.active').length,
          warningStages: element.querySelectorAll('.shot-route-track > button.is-warning').length,
          wavePaths: element.querySelectorAll('.shot-route-wave path').length,
          resourceIcons: element.querySelectorAll('.shot-resource-chips svg').length,
          agentIcons: element.querySelectorAll('.shot-agent-chain article > i svg').length,
          agentConnectors: element.querySelectorAll('.shot-agent-chain > div > b svg').length,
          primaryActionIcons: element.querySelectorAll('.shot-path-resource > footer a svg').length,
        }
      })
      expect(details.avatarSource).toContain('profile-reference-source.png')
      expect(details.stages).toBeGreaterThanOrEqual(0)
      expect(details.activeStages).toBeLessThanOrEqual(1)
      expect(details.warningStages).toBeLessThanOrEqual(details.stages)
      expect(details.wavePaths).toBe(details.stages ? 2 : 0)
      expect(details.resourceIcons).toBeLessThanOrEqual(4)
      expect(details.agentIcons).toBe(4)
      expect(details.agentConnectors).toBe(3)
      expect(details.primaryActionIcons).toBeLessThanOrEqual(1)
    }
  }
})

test('evaluation wide workspace matches the target geometry', async ({ page }) => {
  await page.setViewportSize({ width: 2048, height: 930 })
  await gotoAuthed(page, '/evaluate')

  const metrics = await page.locator('.shot-evaluate').evaluate((element) => {
    const rect = (selector: string) => element.querySelector(selector)?.getBoundingClientRect()
    const root = element.getBoundingClientRect()
    const scoreRow = rect('.shot-score-row')
    const score = rect('.shot-score')
    const evidence = rect('.shot-evidence-version')
    const engine = rect('.shot-engine')
    const diagnosis = rect('.shot-diagnosis-row')
    return {
      rootWidth: Math.round(root.width),
      scoreTop: Math.round(scoreRow?.top || 0),
      scoreHeight: Math.round(scoreRow?.height || 0),
      scoreWidth: Math.round(score?.width || 0),
      evidenceWidth: Math.round(evidence?.width || 0),
      engineWidth: Math.round(engine?.width || 0),
      diagnosisTop: Math.round(diagnosis?.top || 0),
      evidenceRows: element.querySelectorAll('.shot-evidence-version > div').length,
      engineSignals: element.querySelectorAll('.shot-engine > ul > li').length,
      panelIcons: element.querySelectorAll('.shot-panel-icon').length,
      trendIcons: element.querySelectorAll('.shot-capability li > em svg').length,
      documentOverflow: document.documentElement.scrollWidth - window.innerWidth,
    }
  })

  expect(metrics.rootWidth).toBeGreaterThanOrEqual(1975)
  expect(metrics.rootWidth).toBeLessThanOrEqual(1985)
  expect(metrics.scoreTop).toBeGreaterThanOrEqual(224)
  expect(metrics.scoreTop).toBeLessThanOrEqual(230)
  expect(metrics.scoreHeight).toBe(420)
  expect(metrics.scoreWidth).toBe(337)
  expect(metrics.evidenceWidth).toBe(299)
  expect(metrics.engineWidth).toBe(370)
  expect(metrics.diagnosisTop).toBeGreaterThanOrEqual(662)
  expect(metrics.diagnosisTop).toBeLessThanOrEqual(668)
  expect(metrics.evidenceRows).toBe(3)
  expect(metrics.engineSignals).toBeGreaterThanOrEqual(4)
  expect(metrics.engineSignals).toBeLessThanOrEqual(5)
  expect(metrics.panelIcons).toBeGreaterThanOrEqual(4)
  expect(metrics.trendIcons).toBeGreaterThanOrEqual(0)
  expect(metrics.trendIcons).toBeLessThanOrEqual(4)
  expect(metrics.documentOverflow).toBeLessThanOrEqual(1)
})

test('knowledge chapter titles are fully visible', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 720 })
  await gotoAuthed(page, '/knowledge')

  const clippedTitles = await page.locator('.kg-node.type-chapter .node-copy strong').evaluateAll((titles) =>
    titles
      .filter((title) => title.scrollHeight > title.clientHeight + 1)
      .map((title) => ({
        text: title.textContent?.trim(),
        clientHeight: title.clientHeight,
        scrollHeight: title.scrollHeight,
      })),
  )

  expect(clippedTitles).toEqual([])
})

test('knowledge concepts use semantic icons instead of a repeated text placeholder', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await gotoAuthed(page, '/knowledge')

  const concepts = page.locator('.kg-node.type-concept')
  await expect(concepts.first()).toBeVisible({ timeout: 30_000 })

  const icons = await concepts.evaluateAll((nodes) => nodes.map((node) => {
    const badge = node.querySelector<HTMLElement>('.node-icon')
    return {
      badgeText: badge?.textContent?.trim() || '',
      hasSvg: Boolean(badge?.querySelector('svg')),
      semanticKey: badge?.dataset.conceptIcon || '',
    }
  }))

  expect(icons.length).toBeGreaterThan(3)
  expect(icons.every((icon) => icon.hasSvg)).toBe(true)
  expect(icons.every((icon) => icon.badgeText !== '点')).toBe(true)
  expect(new Set(icons.map((icon) => icon.semanticKey)).size).toBeGreaterThan(2)
})
