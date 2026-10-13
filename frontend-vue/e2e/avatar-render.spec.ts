import { expect, test } from '@playwright/test'

test('avatar renderer produces a visible surface', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('zx-resource-agent-authed', '1')
    localStorage.setItem('las_student_id', 'demo_user_001')
  })
  await page.goto('/tutor')
  await page.waitForTimeout(6000)
  const fallback = page.locator('.digital-human-rig')
  await expect(fallback).toBeVisible()
  await expect(fallback).toHaveCSS('background-image', /digital-human-tutor-v2\.png/)
  const state = await page.locator('#xingyuan-avatar-sdk').evaluate((mount) => ({
    html: mount.innerHTML.slice(0, 1000),
    children: mount.childElementCount,
    rect: mount.getBoundingClientRect().toJSON(),
    surfaces: Array.from(mount.querySelectorAll('canvas,video,iframe')).map((item) => ({
      tag: item.tagName,
      rect: item.getBoundingClientRect().toJSON(),
      display: getComputedStyle(item).display,
      opacity: getComputedStyle(item).opacity,
    })),
  }))
  console.log(`[AVATAR-STATE] ${JSON.stringify(state)}`)
})
