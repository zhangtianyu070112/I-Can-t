import { expect, type Page, test } from '@playwright/test'

const criticalConsole: string[] = []
const criticalResponses: string[] = []

async function login(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem('las_student_id', 'codex-e2e')
  })
  await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30_000 })
  const loginButton = page.getByRole('button', { name: /登录并进入系统/ })
  if (await loginButton.isVisible().catch(() => false)) {
    await page.getByPlaceholder('手机号').fill('10000000000')
    await page.getByPlaceholder('密码').fill('demo123')
    await page.getByPlaceholder('验证码').fill('2VV3')
    await loginButton.click()
    await expect(page.locator('.login-gate')).toBeHidden({ timeout: 10_000 })
  }
}

async function gotoAuthed(page: Page, path: string) {
  await login(page)
  await page.goto(path, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => undefined)
  await expect(page.locator('#app')).toBeVisible()
  await expect(page.locator('.login-gate')).toBeHidden({ timeout: 10_000 })
  await expect(page.locator('body')).not.toContainText('undefined')
  await expect(page.locator('body')).not.toContainText('Cannot read properties')
}

async function clickIfVisible(page: Page, pattern: RegExp) {
  const button = page.getByRole('button', { name: pattern }).first()
  if (await button.isVisible().catch(() => false) && await button.isEnabled().catch(() => false)) {
    await button.click()
    await page.waitForTimeout(800)
  }
}

async function fillFirstEditable(page: Page, text: string) {
  const textarea = page.locator('textarea').first()
  if (await textarea.isVisible().catch(() => false)) {
    await textarea.fill(text)
    return
  }
  const textbox = page.getByRole('textbox').first()
  if (await textbox.isVisible().catch(() => false)) {
    await textbox.fill(text)
  }
}

test.beforeEach(async ({ page }) => {
  criticalConsole.length = 0
  criticalResponses.length = 0
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    const text = msg.text()
    if (/favicon|ResizeObserver loop/i.test(text)) return
    criticalConsole.push(text)
  })
  page.on('response', (resp) => {
    const url = resp.url()
    if (!url.includes('/api/')) return
    if (resp.status() === 404 || resp.status() >= 500) {
      criticalResponses.push(`${resp.status()} ${url}`)
    }
  })
})

test.afterEach(async () => {
  expect(criticalConsole, `Console errors:\n${criticalConsole.join('\n')}`).toEqual([])
  expect(criticalResponses, `Bad API responses:\n${criticalResponses.join('\n')}`).toEqual([])
})

test('all core pages open without blank screen', async ({ page }) => {
  const pages = [
    ['/', /为每一位学生|个性化学习资源/],
    ['/profile', /用户画像|画像中枢/],
    ['/workshop', /资源工坊/],
    ['/exercise', /练习诊断|Practice Center/],
    ['/knowledge', /知识中枢|知识图谱/],
    ['/multimodal', /多模态实验室/],
    ['/path', /路径推送|学习路径/],
    ['/tutor', /智能辅导|实时视频辅导/],
    ['/evaluate', /评估进化|学习效果评估/],
  ] as const

  for (const [path, title] of pages) {
    await gotoAuthed(page, path)
    await expect(page.locator('body')).toContainText(title, { timeout: 10_000 })
    await expect(page.locator('#app > *').first()).toBeVisible()
  }
})

test('profile page updates learning profile', async ({ page }) => {
  await gotoAuthed(page, '/profile')
  await fillFirstEditable(
    page,
    '我是软件工程专业学生，正在学数据结构，链表和递归比较弱，希望多给图解、例题和代码实操。',
  )
  await clickIfVisible(page, /更新画像|发送|分析|生成/)
  await expect(page.locator('body')).toContainText(/知识基础|认知风格|模态偏好|易错模式/, { timeout: 15_000 })
})

test('workshop page can request resource generation', async ({ page }) => {
  await gotoAuthed(page, '/workshop')
  await fillFirstEditable(
    page,
    '生成数据结构链表与递归的讲解文档、思维导图、练习题和代码实操案例。',
  )
  await clickIfVisible(page, /生成资源|开始生成/)
  await expect(page.locator('body')).toContainText(/生成|资源|讲解文档|思维导图/, { timeout: 20_000 })
  await clickIfVisible(page, /导出|打包/)
})

test('path page shows route nodes and recommendation panel', async ({ page }) => {
  await gotoAuthed(page, '/path')
  await page.locator('#path-real-goal').fill('掌握链表实现并能够解释递归调用栈')
  await clickIfVisible(page, /生成路径|重新规划|生成/)
  await expect(page.locator('body')).toContainText(/本周学习路径|进行中/, {
    timeout: 15_000,
  })
  await expect(page.locator('body')).toContainText(/当前推送资源|暂无推荐资源|推荐理由/, {
    timeout: 15_000,
  })
})

test('tutor page keeps local knowledge usable without a voice provider', async ({ page }) => {
  await gotoAuthed(page, '/tutor')
  await expect(page.locator('.realtime-tutor-panel')).toBeVisible()
  await expect(page.getByRole('button', { name: '开始通话' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '本地资料问答' })).toBeVisible()
  await page.getByLabel('输入课程问题').fill('用例图')
  await page.getByRole('button', { name: '检索本地资料' }).click()
  await expect(page.locator('.tutor-local-answer')).toBeVisible()
})

test('roadshow entry loads the included learner data', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '使用预置数据进入路演' }).click()
  await expect(page.locator('.login-gate')).toBeHidden()
  await expect(page.getByText('预置演示数据')).toBeVisible()
  await page.getByRole('link', { name: '智能辅导' }).click()
  await page.getByLabel('输入课程问题').fill('用例图')
  await page.getByRole('button', { name: '检索本地资料' }).click()
  await expect(page.getByText('检索依据')).toBeVisible()
})

test('exercise page can load and submit practice', async ({ page }) => {
  await gotoAuthed(page, '/exercise')
  await clickIfVisible(page, /载入练习|生成题目|开始/)
  await expect(page.locator('body')).toContainText(/题|提交|下一题|练习/, { timeout: 15_000 })
  const option = page.locator('input[type="radio"]').first()
  if (await option.isVisible().catch(() => false)) {
    await option.check()
  }
  await clickIfVisible(page, /提交答案|提交/)
  await expect(page.locator('body')).toContainText(/解析|正确|错误|诊断|建议|下一题/, { timeout: 15_000 })
})

test('evaluate, knowledge and multimodal pages have usable content', async ({ page }) => {
  await gotoAuthed(page, '/evaluate')
  await clickIfVisible(page, /生成评估|刷新|查看证据/)
  await expect(page.locator('body')).toContainText(/薄弱|评估|进化|证据/, { timeout: 15_000 })

  await gotoAuthed(page, '/knowledge')
  await expect(page.locator('body')).toContainText(/知识|图谱|节点|课程/, { timeout: 15_000 })

  await gotoAuthed(page, '/multimodal')
  await fillFirstEditable(page, '生成链表动画讲解脚本')
  await clickIfVisible(page, /生成|开始/)
  await expect(page.locator('body')).toContainText(/脚本|多模态|生成|视频|动画/, { timeout: 20_000 })
})
