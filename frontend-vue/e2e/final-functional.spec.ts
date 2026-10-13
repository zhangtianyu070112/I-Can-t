import { expect, test } from '@playwright/test'

async function authenticate(page: import('@playwright/test').Page, studentId: string) {
  await page.addInitScript((id) => {
    sessionStorage.setItem('zx-resource-agent-authed', '1')
    localStorage.setItem('las_student_id', id)
  }, studentId)
}

test('wrong-book radar renders persisted answer evidence', async ({ page }) => {
  await authenticate(page, 'acceptance-exercise')
  await page.goto('/exercise')
  await page.getByRole('button', { name: /错题本/ }).first().click()
  const radar = page.locator('.ability-radar-svg')
  await expect(radar).toBeVisible()
  await expect(page.getByText('33%', { exact: true }).first()).toBeVisible()
  const points = await radar.locator('.radar-area').getAttribute('points')
  expect(points).toBeTruthy()
  expect(points).not.toBe('120,120 120,120 120,120 120,120 120,120 120,120')
  await page.screenshot({ path: 'test-results/final-acceptance/detail/exercise-wrong-book.png', fullPage: true })
})

test('workshop loads a persisted resource body as readable preview', async ({ page }) => {
  await authenticate(page, 'learner-58ce105b-fa0b-4672-bbdc-497494984b79')
  await page.goto('/workshop')
  const preview = page.locator('.shot-preview-content .markdown-body')
  await expect(preview).toBeVisible({ timeout: 20_000 })
  expect((await preview.innerText()).trim().length).toBeGreaterThan(40)
  await page.getByRole('button', { name: /展开预览/ }).click()
  await expect(page.getByRole('button', { name: /收起/ })).toBeVisible()
  await page.screenshot({ path: 'test-results/final-acceptance/detail/workshop-preview.png', fullPage: true })
})

test('global user settings opens and exposes profile actions', async ({ page }) => {
  await authenticate(page, 'demo_user_001')
  await page.goto('/profile')
  await page.getByRole('button', { name: /用户设置/ }).click()
  await expect(page.getByText('学习者 ID')).toBeVisible()
  await expect(page.getByRole('link', { name: /完善用户画像/ })).toBeVisible()
})
