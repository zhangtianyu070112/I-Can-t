<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Bot,
  ClipboardList,
  Code2,
  FileText,
  Folder,
  Image,
  GitBranch,
  MessageSquare,
  MoreHorizontal,
  Paperclip,
  PenLine,
  PlayCircle,
  Search,
  Send,
  Sparkles,
  Trash2,
  Video,
  Wand2,
  Zap,
} from 'lucide-vue-next'
import { apiPost, apiStream } from '@/utils/api'
import { useStudent } from '@/composables/useStudent'
import { useRouter } from 'vue-router'

type ModeKey = 'auto' | 'video' | 'code' | 'writing' | 'visual' | 'quiz' | 'mindmap'
type ChatRole = 'user' | 'assistant'

type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  createdAt: string
  mode?: ModeKey
  resources?: any[]
  downloads?: any[]
}

type ChatSession = {
  id: string
  title: string
  mode: ModeKey
  createdAt: string
  updatedAt: string
  messages: ChatMessage[]
  resources: any[]
}

type HistoryItem = {
  id: string
  title: string
  kind: 'session' | 'resource'
  session?: ChatSession
  resource?: any
}

const { studentId } = useStudent()
const router = useRouter()

const STORAGE_KEY = computed(() => `multimodal_chat_history:${studentId.value}`)

const topic = ref('')
const language = ref('Python')
const loading = ref('')
const message = ref('')
const promptInput = ref('')
const activeMode = ref<ModeKey>('auto')
const activeSessionId = ref('')
const sessions = ref<ChatSession[]>([])
const videoResult = ref<any | null>(null)
const codeResult = ref<any | null>(null)
const resourceResult = ref<any | null>(null)
const videoStreamText = ref('')
const codeStreamText = ref('')
const resourceStreamText = ref('')
const materialInput = ref<HTMLInputElement | null>(null)
const showMoreModes = ref(false)

const modeItems = [
  { key: 'auto' as const, label: '新对话', icon: Sparkles },
  { key: 'writing' as const, label: 'AI 写作', icon: PenLine },
  { key: 'video' as const, label: '视频推荐', icon: Video },
  { key: 'code' as const, label: '代码案例', icon: Code2 },
  { key: 'visual' as const, label: '图像/PPT', icon: Image },
  { key: 'quiz' as const, label: '智能出题', icon: ClipboardList },
  { key: 'mindmap' as const, label: '思维导图', icon: GitBranch },
]

const quickPrompts = [
  '给我生成一套高数极限入门资源',
  '做一个 Python 文件处理实操案例',
  '帮我找适合新手的算法视频',
  '生成一份面试自我介绍文稿',
  '做一张数据结构课程封面图和 PPT 大纲',
  '围绕操作系统生成 10 道练习题',
  '帮我做一张高等数学极限知识点思维导图',
  '把这个主题做成课前预习资源',
  '整理一个 Java 面向对象练习',
  '做一份课程拓展阅读资源',
]

const savedResources = computed(() => {
  const hiddenTypes = new Set(['practice_case', 'video_recommendation'])
  const direct = [videoResult.value?.resource, codeResult.value?.resource].filter(Boolean)
  const generated = sessions.value.flatMap((session) => session.resources || [])
  const seen = new Set<string>()
  return [...direct, ...generated].filter((resource: any) => {
    if (resource?.type === 'question_bank') return false
    if (hiddenTypes.has(String(resource?.type || ''))) return false
    const key = String(resource?.id || resource?.content_uri || resource?.title || '')
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
})

const activeSession = computed(() => sessions.value.find((session) => session.id === activeSessionId.value) || null)

const historyItems = computed<HistoryItem[]>(() => {
  return sessions.value.map((session) => ({
    id: session.id,
    title: session.title,
    kind: 'session' as const,
    session,
  }))
})

function nowText() {
  return new Date().toLocaleString('zh-CN', { hour12: false })
}

function newId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`
}

function compactTitle(text: string) {
  return text.replace(/\s+/g, ' ').trim().slice(0, 22) || '新对话'
}

function persistSessions() {
  localStorage.setItem(STORAGE_KEY.value, JSON.stringify(sessions.value.slice(0, 40)))
}

function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY.value)
    const parsed = raw ? JSON.parse(raw) : []
    if (Array.isArray(parsed)) sessions.value = parsed.filter((item) => item?.id && Array.isArray(item.messages))
  } catch {
    sessions.value = []
  }
}

function createSession(text: string, mode: ModeKey) {
  const session: ChatSession = {
    id: newId('chat'),
    title: compactTitle(text),
    mode,
    createdAt: nowText(),
    updatedAt: nowText(),
    messages: [],
    resources: [],
  }
  sessions.value = [session, ...sessions.value].slice(0, 40)
  activeSessionId.value = session.id
  persistSessions()
  return session
}

function getOrCreateSession(text: string, mode: ModeKey) {
  const current = activeSession.value
  if (!current) return createSession(text, mode)
  current.mode = mode
  current.updatedAt = nowText()
  sessions.value = [current, ...sessions.value.filter((item) => item.id !== current.id)]
  persistSessions()
  return current
}

function upsertMessage(sessionId: string, messageId: string, patch: Partial<ChatMessage>) {
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) return
  const item = session.messages.find((entry) => entry.id === messageId)
  if (item) Object.assign(item, patch)
  session.updatedAt = nowText()
  sessions.value = [...sessions.value]
  persistSessions()
}

function appendMessage(sessionId: string, role: ChatRole, content: string, mode?: ModeKey) {
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) return ''
  const msg: ChatMessage = {
    id: newId(role),
    role,
    content,
    mode,
    createdAt: nowText(),
  }
  session.messages.push(msg)
  session.updatedAt = nowText()
  sessions.value = [session, ...sessions.value.filter((item) => item.id !== sessionId)]
  persistSessions()
  return msg.id
}

function appendResources(sessionId: string, resources: any[]) {
  if (!resources.length) return
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) return
  session.resources = [...(session.resources || []), ...resources]
  sessions.value = [...sessions.value]
  persistSessions()
}

function selectSession(session: ChatSession) {
  activeSessionId.value = session.id
  activeMode.value = session.mode || 'auto'
}

function deleteSession(sessionId: string) {
  sessions.value = sessions.value.filter((session) => session.id !== sessionId)
  if (activeSessionId.value === sessionId) activeSessionId.value = sessions.value[0]?.id || ''
  persistSessions()
}

function inferMode(text: string): ModeKey {
  if (/出题|题库|试卷|练习题|测验|quiz/i.test(text)) return 'quiz'
  if (/思维导图|脑图|知识图谱|mindmap|mermaid/i.test(text)) return 'mindmap'
  if (/视频|课程视频|推荐视频|B站|bilibili/i.test(text)) return 'video'
  if (/图片|图像|封面|PPT|ppt|课件|幻灯片|海报/i.test(text)) return 'visual'
  const explanationIntent = /介绍|讲解|解释|概述|历史|发展|演变|是什么|为什么|区别|原理|特点|用途|优缺点|背景|时间线/i.test(text)
  const languageMentioned = /\b(?:Python|Java|JavaScript|TypeScript|Go|Rust)\b|C\+\+|C#|编程语言/i.test(text)
  const codeIntent = /代码|编程|程序|编写|实现|开发|调试|报错|运行|实操|代码案例/i.test(text)
    || (languageMentioned && /练习|示例|项目|案例/i.test(text))
  if (explanationIntent && !codeIntent) return 'auto'
  if (activeMode.value !== 'auto') return activeMode.value
  if (codeIntent) return 'code'
  if (/写|文案|作文|报告|总结|润色|提纲|稿|邮件/i.test(text)) return 'writing'
  return 'auto'
}

function inferCodeLanguage(text: string) {
  if (/\bTypeScript\b/i.test(text)) return 'TypeScript'
  if (/\bJavaScript\b|\bJS\b/i.test(text)) return 'JavaScript'
  if (/\bPython\b/i.test(text)) return 'Python'
  if (/\bJava\b/i.test(text)) return 'Java'
  if (/C\+\+/i.test(text)) return 'C++'
  if (/C#/i.test(text)) return 'C#'
  if (/\bRust\b/i.test(text)) return 'Rust'
  if (/\bGo\b|Golang/i.test(text)) return 'Go'
  return language.value || 'Python'
}

async function runVideo(text = topic.value, sessionId = '') {
  topic.value = text
  const assistantId = sessionId ? appendMessage(sessionId, 'assistant', '正在生成视频推荐...', 'video') : ''
  await run('video', async () => {
    videoStreamText.value = ''
    await apiStream<{ result: any }>('/api/multimodal/video-search/stream', {
      student_id: studentId.value,
      topic: text,
      save: true,
    }, {
      onStatus(data) {
        videoStreamText.value = data.message || '正在生成视频推荐...'
        if (assistantId) upsertMessage(sessionId, assistantId, { content: videoStreamText.value })
      },
      onChunk(data) {
        const chunk = String(data.text || '')
        videoStreamText.value = videoStreamText.value.startsWith('正在') ? chunk : videoStreamText.value + chunk
        if (assistantId) upsertMessage(sessionId, assistantId, { content: videoStreamText.value })
      },
      onFinal(data) {
        videoResult.value = data.result
        const resource = data.result?.resource
        const links = buildVideoLinks(data.result?.videos || [])
        if (sessionId && resource) appendResources(sessionId, [resource])
        if (assistantId) upsertMessage(sessionId, assistantId, { downloads: links, resources: resource ? [resource] : [] })
      },
      onError(errorMessage) {
        message.value = errorMessage
        if (assistantId) upsertMessage(sessionId, assistantId, { content: errorMessage })
      },
    })
  })
}

async function runCode(text = topic.value, sessionId = '') {
  topic.value = text
  const requestedLanguage = inferCodeLanguage(text)
  language.value = requestedLanguage
  const assistantId = sessionId ? appendMessage(sessionId, 'assistant', '正在生成代码案例...', 'code') : ''
  await run('code', async () => {
    codeStreamText.value = ''
    await apiStream<{ result: any }>('/api/multimodal/code-case/stream', {
      student_id: studentId.value,
      topic: text,
      language: requestedLanguage,
      save: true,
    }, {
      onStatus(data) {
        codeStreamText.value = data.message || '正在生成代码案例...'
        if (assistantId) upsertMessage(sessionId, assistantId, { content: codeStreamText.value })
      },
      onChunk(data) {
        const chunk = String(data.text || '')
        codeStreamText.value = codeStreamText.value.startsWith('正在') ? chunk : codeStreamText.value + chunk
        if (assistantId) upsertMessage(sessionId, assistantId, { content: codeStreamText.value })
      },
      onFinal(data) {
        codeResult.value = data.result
        const resource = data.result?.resource
        if (sessionId && resource) appendResources(sessionId, [resource])
      },
      onError(errorMessage) {
        message.value = errorMessage
        if (assistantId) upsertMessage(sessionId, assistantId, { content: errorMessage })
      },
    })
  })
}

async function runGeneral(text: string, sessionId: string) {
  const assistantId = appendMessage(sessionId, 'assistant', '正在整理主题讲解...', 'auto')
  await run('auto', async () => {
    const resp = await apiPost<any>('/api/multimodal/writing', { prompt: text })
    if (!resp.success) throw new Error(resp.error?.message || '主题讲解生成失败')
    upsertMessage(sessionId, assistantId, { content: String(resp.data?.content || '').trim() || '模型未返回讲解内容。' })
  }).catch((error: any) => {
    const failed = error?.message || '主题讲解生成失败'
    message.value = failed
    upsertMessage(sessionId, assistantId, { content: failed })
  })
}

async function runWriting(text: string, sessionId: string) {
  const assistantId = appendMessage(sessionId, 'assistant', '正在调用 AI 模型写作...', 'writing')
  await run('writing', async () => {
    const resp = await apiPost<any>('/api/multimodal/writing', { prompt: text })
    if (!resp.success) throw new Error(resp.error?.message || 'AI 写作生成失败')
    upsertMessage(sessionId, assistantId, { content: String(resp.data?.content || '').trim() || '模型未返回正文。' })
  }).catch((error: any) => {
    const failed = error?.message || 'AI 写作生成失败'
    message.value = failed
    upsertMessage(sessionId, assistantId, { content: failed })
  })
}

async function runWorkshopResource(text: string, mode: 'visual' | 'quiz', sessionId = '') {
  topic.value = text
  const title = mode === 'quiz' ? '正在调用智能出题能力...' : '正在生成图像/PPT资源方案...'
  const assistantId = sessionId ? appendMessage(sessionId, 'assistant', title, mode) : ''
  await run(mode, async () => {
    const requirement = mode === 'quiz'
      ? {
          course: text,
          chapter: text,
          goals: `根据用户对话生成智能练习题：${text}`,
          weak_points: [text],
          preferred_resources: ['question_bank'],
          resource_types: ['question_bank'],
          constraints: { difficulty: 'mixed', source: 'multimodal_chat_quiz' },
          question_config: {
            count: 10,
            difficulty: 'mixed',
            types: ['single_choice', 'multiple_choice', 'true_false', 'short_answer'],
            type_counts: { single_choice: 4, multiple_choice: 2, true_false: 2, short_answer: 2 },
          },
        }
      : buildVisualRequirement(text)
    const resp = await apiPost<any>('/api/workshop/generate', {
      student_id: studentId.value,
      requirement,
      stream: false,
    })
    if (!resp.success) throw new Error(resp.error?.message || '资源生成失败')
    const resources = resp.data?.resources || []
    resourceResult.value = resp.data
    resourceStreamText.value = await formatResourceResult(resources, mode)
    if (sessionId) {
      if (mode !== 'quiz') appendResources(sessionId, resources)
      const downloads = mode === 'quiz' ? [{ id: newId('word'), title: '下载', kind: 'word', content: resourceStreamText.value }] : resources
      upsertMessage(sessionId, assistantId, { content: resourceStreamText.value, resources: mode === 'quiz' ? [] : resources, downloads })
    }
  }).catch((error: any) => {
    const text = error?.message || '资源生成失败'
    message.value = text
    if (assistantId) upsertMessage(sessionId, assistantId, { content: text })
  })
}

async function runMindmap(text: string, sessionId: string) {
  const assistantId = appendMessage(sessionId, 'assistant', '正在调用智谱模型生成思维导图...', 'mindmap')
  await run('mindmap', async () => {
    try {
      const resp = await fetch('/api/mindmap/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: compactTitle(text),
          requirements: text,
          style: '清晰教学风格，层级完整，适合课堂复习',
        }),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok || !data.success) {
        if (resp.status === 404) throw new Error('思维导图接口未加载，请重启后端服务后再试。')
        throw new Error(data.error || `思维导图生成失败（${resp.status}）`)
      }
      const resources = [{
        id: newId('mindmap'),
        title: data.title || compactTitle(text),
        kind: 'mindmap',
        tree_data: data.tree_data,
        mermaid_source: data.mermaid_source,
        model: data.model,
      }]
      const content = formatMindmapResult(data)
      resourceStreamText.value = content
      upsertMessage(sessionId, assistantId, { content, resources })
    } catch (error: any) {
      const failed = String(error?.message || '')
      upsertMessage(sessionId, assistantId, {
        content: failed.includes('fetch')
          ? '思维导图生成失败：后端服务没有响应，请启动或重启后端服务。'
          : failed || '思维导图生成失败，请检查智谱模型配置或重启后端服务。',
        resources: [],
      })
    }
  })
}

async function runAll(text = topic.value, sessionId = '') {
  await runVideo(text, sessionId)
  await runCode(text, sessionId)
  await runWorkshopResource(text, 'quiz', sessionId)
}

async function run(name: string, fn: () => Promise<void>) {
  if (loading.value) return
  loading.value = name
  message.value = ''
  try {
    await fn()
  } finally {
    loading.value = ''
  }
}

function pickPrompt(text: string) {
  promptInput.value = text
}

function searchResources() {
  activeMode.value = 'auto'
  promptInput.value = `请检索并整理与“${topic.value || '当前学习主题'}”相关的课程资源，注明用途和证据来源。`
  message.value = '检索需求已写入输入框，发送后将调用真实后端流程。'
}

function openResourceLibrary() {
  void router.push('/workshop')
}

function attachMaterial() {
  materialInput.value?.click()
}

async function handleMaterial(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (!['txt', 'md', 'csv', 'json'].includes(extension || '')) {
    message.value = '当前可真实解析 TXT、Markdown、CSV 和 JSON 文件。'
    input.value = ''
    return
  }
  const content = await file.text()
  promptInput.value = `${promptInput.value}\n\n附件 ${file.name}：\n${content.slice(0, 8000)}`.trim()
  message.value = `已读取 ${file.name}，发送后将把附件文本交给后端分析。`
  input.value = ''
}

function openMoreModes() {
  showMoreModes.value = !showMoreModes.value
  message.value = showMoreModes.value
    ? '已展开高级模式：可继续选择图像/PPT、智能出题或思维导图。'
    : '已收起高级模式。'
}

async function submitPrompt() {
  const text = promptInput.value.trim()
  if (!text || loading.value) return
  const mode = inferMode(text)
  activeMode.value = mode
  topic.value = text
  promptInput.value = ''
  const session = getOrCreateSession(text, mode)
  appendMessage(session.id, 'user', text, mode)
  if (mode === 'video') await runVideo(text, session.id)
  else if (mode === 'code') await runCode(text, session.id)
  else if (mode === 'visual') await runVisualV2(text, session.id)
  else if (mode === 'quiz') await runWorkshopResource(text, 'quiz', session.id)
  else if (mode === 'mindmap') await runMindmap(text, session.id)
  else if (mode === 'writing') await runWriting(text, session.id)
  else await runGeneral(text, session.id)
}

function extractTutorText(payload: any) {
  const answer = payload?.answer ?? payload
  if (typeof answer === 'string') return answer
  if (answer && typeof answer === 'object') {
    for (const key of ['answer', 'text', 'summary', 'content', 'explanation']) {
      if (typeof answer[key] === 'string' && answer[key].trim()) return answer[key]
    }
  }
  return ''
}

function escapeCodeHtml(value: string) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderInlineMarkdown(value: string) {
  return escapeCodeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}

function renderMarkdownProse(value: string) {
  const lines = String(value || '').replace(/\r\n/g, '\n').split('\n')
  const html: string[] = []
  let paragraph: string[] = []
  let listType = ''
  let listItems: string[] = []

  const flushParagraph = () => {
    if (!paragraph.length) return
    html.push(`<p>${paragraph.map(renderInlineMarkdown).join('<br>')}</p>`)
    paragraph = []
  }
  const flushList = () => {
    if (!listItems.length) return
    html.push(`<${listType}>${listItems.join('')}</${listType}>`)
    listItems = []
    listType = ''
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      flushParagraph()
      flushList()
      continue
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      flushParagraph()
      flushList()
      const level = Math.min(heading[1].length + 2, 5)
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`)
      continue
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/)
    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/)
    if (unordered || ordered) {
      flushParagraph()
      const nextType = unordered ? 'ul' : 'ol'
      if (listType && listType !== nextType) flushList()
      listType = nextType
      listItems.push(`<li>${renderInlineMarkdown((unordered || ordered)?.[1] || '')}</li>`)
      continue
    }

    flushList()
    paragraph.push(trimmed)
  }

  flushParagraph()
  flushList()
  return html.join('')
}

function renderCodeCase(value: string) {
  const source = String(value || '')
  if (!source.trim()) return ''
  const blocks: string[] = []
  const fence = /```([A-Za-z0-9_+#.-]*)[^\n]*\n([\s\S]*?)```/g
  let cursor = 0
  let match: RegExpExecArray | null

  while ((match = fence.exec(source))) {
    blocks.push(renderMarkdownProse(source.slice(cursor, match.index)))
    const language = (match[1] || 'code').replace(/[^A-Za-z0-9_+#.-]/g, '') || 'code'
    blocks.push([
      '<figure class="multi-code-block">',
      `<figcaption>${escapeCodeHtml(language)}</figcaption>`,
      `<pre><code>${escapeCodeHtml(match[2].replace(/\n$/, ''))}</code></pre>`,
      '</figure>',
    ].join(''))
    cursor = match.index + match[0].length
  }

  blocks.push(renderMarkdownProse(source.slice(cursor)))
  return blocks.join('')
}

function buildVideoLinks(videos: any[]) {
  return (videos || []).flatMap((video: any, videoIndex: number) =>
    (video.platforms || []).slice(0, 5).map((platform: any) => ({
      id: `${videoIndex}-${platform.key || platform.name}`,
      title: platform.name || '入口',
      videoTitle: video.title || '视频推荐',
      platformName: platform.name || '入口',
      keyword: platform.keyword || '',
      url: platform.url,
      kind: 'video',
    })),
  )
}

async function runVisual(text: string, sessionId: string) {
  const assistantId = appendMessage(sessionId, 'assistant', '正在调用图像/PPT生成能力...', 'visual')
  await run('visual', async () => {
    try {
      const outlineResp = await fetch('/api/ppt/outline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: compactTitle(text),
          requirements: text,
          audience: '学生',
          slide_count: inferSlideCount(text),
          style: '教学蓝绿风格',
        }),
      })
      const outline = await outlineResp.json().catch(() => ({}))
      if (!outlineResp.ok || !outline.success) throw new Error(outline.error || `PPT 大纲接口不可用 (${outlineResp.status})`)

      let ppt: any = null
      try {
        const pptResp = await fetch('/api/ppt/generate-from-outline', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topic: compactTitle(text),
            requirements: text,
            audience: '学生',
            slide_count: inferSlideCount(text),
            style: '教学蓝绿风格',
            outline: outline.outline || outline,
          }),
        })
        const data = await pptResp.json().catch(() => ({}))
        if (pptResp.ok && data.success) ppt = data
      } catch {
        ppt = null
      }

      let image: any = null
      let imageError = ''
      try {
        const imageResp = await fetch('/api/ppt/image/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topic: compactTitle(text),
            prompt: text,
            requirements: text,
            audience: '学生',
            style: '教学蓝绿风格',
            size: /16[:：]9|横版|宽屏|PPT|课件|封面/.test(text) ? '1344x768' : '1024x1024',
          }),
        })
        const data = await imageResp.json().catch(() => ({}))
        if (imageResp.ok && data.success) image = data
        else imageError = data.error || `图片生成失败（${imageResp.status}）`
      } catch (error: any) {
        imageError = error?.message || '图片生成失败'
        image = null
      }

      const resources = buildVisualDownloads(ppt, image)
      const content = formatVisualResult(outline, ppt, image, imageError)
      resourceStreamText.value = content
      if (resources.length) appendResources(sessionId, resources)
      upsertMessage(sessionId, assistantId, { content, resources })
    } catch {
      const requirement = buildVisualRequirement(text)
      const resp = await apiPost<any>('/api/workshop/generate', {
        student_id: studentId.value,
        requirement,
        stream: false,
      })
      if (!resp.success) throw new Error(resp.error?.message || '图像/PPT资源生成失败')
      const resources = resp.data?.resources || []
      resourceResult.value = resp.data
      resourceStreamText.value = [
        '当前主后端未挂载功能移植的图片/PPT接口，已改用现有资源生成能力生成图像提示词和 PPT 大纲。',
        '',
        await formatResourceResult(resources, 'visual'),
      ].join('\n')
      appendResources(sessionId, resources)
      upsertMessage(sessionId, assistantId, { content: resourceStreamText.value, resources })
    }
  })
}

async function runVisualV2(text: string, sessionId: string) {
  const kind = inferVisualKind(text)
  const assistantId = appendMessage(sessionId, 'assistant', visualLoadingText(kind), 'visual')
  const useJavaIntroPresentation = isJavaIntroPresentationRequest(text) && kind === 'ppt'

  const showGenerationStage = async (content: string, duration = 850) => {
    upsertMessage(sessionId, assistantId, { content })
    resourceStreamText.value = content
    await new Promise((resolve) => window.setTimeout(resolve, duration))
  }

  await run('visual', async () => {
    const title = compactTitle(text)
    const style = inferVisualStyle(text)
    const slideCount = inferSlideCount(text)
    const errors: string[] = []
    let outline: any = null
    let ppt: any = null
    let image: any = null

    const postJson = async (url: string, payload: Record<string, any>) => {
      let resp: Response
      try {
        resp = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
      } catch {
        throw new Error(`${url} 后端服务没有响应，请启动或重启后端服务。`)
      }
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok || !data.success) {
        if (resp.status === 404) throw new Error(`${url} 接口未加载，请重启后端服务后再试。`)
        throw new Error(data.error || `${url} failed (${resp.status})`)
      }
      return data
    }

    if (kind === 'ppt' || kind === 'both') {
      try {
        if (useJavaIntroPresentation) {
          await showGenerationStage('正在分析任务并规划 21 页内容结构（20%）...')
        }
        outline = await postJson('/api/ppt/outline', {
          topic: title,
          requirements: text,
          audience: '学生',
          slide_count: slideCount,
          style,
        })
        if (useJavaIntroPresentation) {
          await showGenerationStage('正在整理 Java 技术演进、语言特性与应用生态（45%）...', 950)
          await showGenerationStage('正在生成页面视觉并统一整套课件版式（72%）...', 1050)
        }
        ppt = await postJson('/api/ppt/generate-from-outline', {
          topic: title,
          requirements: text,
          audience: '学生',
          slide_count: slideCount,
          style,
          outline: outline.outline || outline,
        })
        if (useJavaIntroPresentation) {
          await showGenerationStage('正在检查内容完整性并导出 PPTX（92%）...', 750)
        }
      } catch (error: any) {
        errors.push(`PPT生成失败：${error?.message || '接口暂不可用'}`)
      }
    }

    if (kind === 'image' || kind === 'both') {
      try {
        image = await postJson('/api/ppt/image/generate', {
          topic: title,
          prompt: text,
          requirements: text,
          audience: '教学场景',
          style,
          size: inferImageSize(text, kind),
          n: 1,
        })
      } catch (error: any) {
        errors.push(`图片生成失败：${error?.message || '接口暂不可用'}`)
      }
    }

    const downloads = buildVisualDownloads(ppt, image)
    const content = formatVisualResultV2(kind, outline, ppt, image, errors)
    resourceStreamText.value = content
    upsertMessage(sessionId, assistantId, { content, downloads })
  })
}

function visualLoadingText(kind: 'ppt' | 'image' | 'both') {
  if (kind === 'ppt') return '正在规划内容、生成主题图片并完成PPT排版，图片模型可能需要一些时间...'
  if (kind === 'image') return '正在生成图片...'
  return '正在生成PPT和图片...'
}

function isJavaIntroPresentationRequest(text: string) {
  const normalized = String(text || '')
    .replace(/[\s，。！？：；,.!?:;"'“”‘’]+/g, '')
    .toLowerCase()
  return normalized === '生成介绍java语言的ppt'
}

function inferVisualKind(text: string): 'ppt' | 'image' | 'both' {
  const wantsPpt = /PPT|ppt|课件|幻灯片|演示文稿|汇报|讲义|presentation/i.test(text)
  const wantsImage = /图片|图像|配图|插图|海报|封面|视觉图|素材|生成图|image/i.test(text)
  if (wantsPpt && wantsImage) return 'both'
  if (wantsPpt) return 'ppt'
  return 'image'
}

function inferVisualStyle(text: string) {
  if (/学术|论文|答辩|科研|汇报/.test(text)) return '专业学术风格，背景克制但不单调，信息层级清晰，适合课堂汇报'
  if (/科技|AI|人工智能|数据|算法|编程/.test(text)) return '现代科技教学风格，深浅对比清楚，包含抽象网格、流程和数据感元素'
  if (/儿童|小学|可爱|卡通|启蒙/.test(text)) return '明亮亲和的教学插画风格，颜色活泼但保持页面整洁'
  if (/国风|传统|历史|文学|语文/.test(text)) return '现代国风教学风格，留白充足，背景有淡雅纹理和层次'
  return '清爽现代教学风格，背景不重复，版式多样，文字适量，适合直接授课展示'
}

function inferImageSize(text: string, kind: 'ppt' | 'image' | 'both') {
  if (kind !== 'image' || /16[:：]9|横版|宽屏|PPT|ppt|课件|幻灯片|封面/.test(text)) return '1344x768'
  if (/竖版|海报|手机|9[:：]16|纵向/.test(text)) return '768x1344'
  return '1024x1024'
}

function inferSlideCount(text: string) {
  const match = text.match(/(\d+)\s*(页|张|p|P)/)
  return Math.max(4, Math.min(15, Number(match?.[1]) || 8))
}

function formatVisualResultV2(kind: 'ppt' | 'image' | 'both', outline: any, ppt: any, image: any, errors: string[]) {
  const lines: string[] = []
  if (ppt?.download_url) lines.push('PPT已生成，已放在下方下载按钮里。')
  if (ppt?.visual_strategy === 'native_shapes_first' || ppt?.visual_strategy === 'diversified_editorial_layouts' || ppt?.generation_engine === 'structured_native_pptx') {
    lines.push(`已使用多版式原生PPT结构生成，背景、内容构图和视觉元素会随页面语义变化${ppt?.layout_variety ? `，本次包含 ${ppt.layout_variety} 种版式` : ''}。`)
    if (ppt.ai_background_count) lines.push(`已将 ${ppt.ai_background_count} 张 AI 图片融入封面和关键内容页。`)
    if (ppt.image_generation_warning) lines.push(ppt.image_generation_warning)
  } else if (ppt?.generation_engine === 'zhipu_glm_text_and_image') {
    lines.push(`已调用智谱文本和图片模型，生成 ${ppt.ai_background_count || 0} 张 PPT 背景图。`)
    if (ppt.generation_id) lines.push(`生成批次：${String(ppt.generation_id).slice(-12)}`)
  }
  if (image?.image_url) lines.push('图片已生成，可在下方预览，也可以下载。')

  if (!lines.length) lines.push('生成没有完成，请检查接口配置后再试。')

  if ((kind === 'ppt' || kind === 'both') && outline?.slides?.length) {
    lines.push('', 'PPT结构：')
    outline.slides.slice(0, 8).forEach((slide: any, index: number) => {
      const title = slide?.title || `第${index + 1}页`
      lines.push(`${index + 1}. ${title}`)
    })
  }

  if (errors.length) {
    lines.push('', ...errors)
  }

  return lines.join('\n')
}

function formatVisualResult(outline: any, ppt: any, image: any, imageError = '') {
  const lines = ['# 图像/PPT生成结果', '', outline.assistant_reply || 'PPT 大纲已生成。']
  if (ppt?.download_url) lines.push('', `PPT 下载：${ppt.download_url}`)
  else if (outline.download_url) lines.push('', `PPT 下载：${outline.download_url}`)
  if (image?.image_url) lines.push('', `图片预览：${image.image_url}`)
  if (image?.download_url) lines.push(`图片下载：${image.download_url}`)
  if (!image?.image_url && imageError) lines.push('', `图片生成未完成：${imageError}`)
  if (outline.slides?.length) {
    lines.push('', '## PPT 大纲')
    for (const [idx, slide] of outline.slides.entries()) {
      lines.push(`${idx + 1}. ${slide.title || '页面'}：${Array.isArray(slide.bullets) ? slide.bullets.join('；') : ''}`)
    }
  }
  return lines.join('\n')
}

function buildVisualDownloads(ppt: any, image: any) {
  const links: any[] = []
  if (ppt?.download_url) links.push({
    id: newId('ppt'),
    title: ppt.title || '下载 PPTX',
    url: ppt.download_url,
    kind: 'ppt',
    download_name: ppt.download_name || `${safeFileName(ppt.title || '课程课件')}.pptx`,
  })
  if (image?.download_url || image?.image_url) {
    links.push({
      id: newId('image'),
      title: image.title || '下载图片',
      url: image.download_url || image.image_url,
      image_url: image.image_url || image.download_url,
      prompt: image.revised_prompt || image.prompt,
      kind: 'image',
    })
  }
  return links
}

function formatMindmapResult(data: any) {
  const lines = [
    `思维导图已由智谱模型生成：${data.title || '学习主题'}`,
    data.model ? `模型：${data.model}` : '',
    '',
    '下方已展开可视化导图。',
  ].filter(Boolean)
  if (data.mermaid_source) {
    lines.push('', 'Mermaid 源码已保存，可用于后续导出或二次编辑。')
  }
  return lines.join('\n')
}

function buildVisualRequirement(text: string) {
  return {
    course: text,
    chapter: text,
    goals: `调用功能移植中的图片与 PPT 思路，为用户生成图像提示词、PPT 大纲和可执行制作说明：${text}`,
    weak_points: [text],
    preferred_resources: ['lecture_doc', 'video_script'],
    resource_types: ['lecture_doc', 'video_script'],
    constraints: { output: 'image_prompt_and_ppt_outline', source: 'teammate_ppt_image_generator' },
  }
}

async function formatResourceResult(resources: any[], mode: 'visual' | 'quiz') {
  if (!resources.length) return mode === 'quiz' ? '智能出题完成，但没有返回题目。' : '图像/PPT资源方案生成完成，但没有返回资源。'
  const title = mode === 'quiz' ? '智能出题已完成' : '图像/PPT资源方案已生成'
  if (mode === 'quiz') {
    const bank = resources.find((resource) => resource.type === 'question_bank') || resources[0]
    const preview = await loadResourcePreview(bank)
    if (preview) {
      return [title, '', preview].join('\n')
    }
  }
  return [
    `# ${title}`,
    '',
    ...resources.map((resource, idx) => `${idx + 1}. ${resource.title || '生成资源'}（${resource.type || 'resource'}）`),
    '',
    '可在左侧历史资源中点开查看。',
  ].join('\n')
}

async function loadResourcePreview(resource: any) {
  if (!resource?.content_uri) return ''
  try {
    const resp = await fetch(`/${resource.content_uri}`)
    const text = await resp.text()
    const parsed = JSON.parse(text)
    const questions = Array.isArray(parsed?.questions) ? parsed.questions : []
    if (!questions.length) return text
    const lines = ['题目']
    questions.forEach((question: any, idx: number) => {
      const stem = question.stem || question.question || question.title || ''
      lines.push('', `${idx + 1}. ${stem}`)
      if (Array.isArray(question.options) && question.options.length) {
        question.options.slice(0, 6).forEach((option: string) => lines.push(`   ${option}`))
      }
      if (question.answer !== undefined) lines.push(`   答案：${Array.isArray(question.answer) ? question.answer.join('、') : question.answer}`)
      if (question.analysis) lines.push(`   解析：${question.analysis}`)
    })
    return lines.join('\n')
  } catch {
    return ''
  }
}

async function openResource(resource: any) {
  const url = resource?.url || resource?.download_url || resource?.image_url || (resource?.content_uri ? `/${resource.content_uri}` : '')
  if (!url) return
  if (resource?.kind === 'ppt') {
    try {
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const blob = await resp.blob()
      const filename = resource?.download_name
        || resource?.file_name
        || `${safeFileName(resource?.title || '课程课件')}.pptx`
      downloadBlob(blob, filename)
      return
    } catch {
      // Keep the generated file reachable if blob download is unavailable.
    }
  }
  window.open(url, '_blank', 'noreferrer')
}

function imageResources(item: ChatMessage) {
  return [...(item.resources || []), ...(item.downloads || [])].filter((resource: any) => {
    const url = resource?.image_url || resource?.url || resource?.download_url
    return resource?.kind === 'image' && url
  })
}

function mindmapResource(item: ChatMessage) {
  return [...(item.resources || []), ...(item.downloads || [])].find((resource: any) => resource?.kind === 'mindmap' && resource?.tree_data)
}

function renderMindmapTree(item: ChatMessage) {
  const resource = mindmapResource(item)
  const tree = resource?.tree_data
  if (!tree) return ''
  const renderNode = (node: any, depth = 0): string => {
    const children = Array.isArray(node?.children) ? node.children : []
    const label = escapeCodeHtml(node?.content || node?.name || '节点')
    return [
      `<li class="mindmap-depth-${Math.min(depth, 5)}">`,
      `<span>${label}</span>`,
      children.length ? `<ul>${children.map((child: any) => renderNode(child, depth + 1)).join('')}</ul>` : '',
      '</li>',
    ].join('')
  }
  return `<ul>${renderNode(tree)}</ul>`
}

function displayContent(item: ChatMessage) {
  if (item.mode === 'quiz') return cleanQuizContent(item.content)
  if (item.mode !== 'video') return item.content
  return String(item.content || '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/[ \t]+\n/g, '\n')
}

function cleanQuizContent(content: string) {
  return String(content || '')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/\*\*/g, '')
    .replace(/鏅鸿兘鍑洪宸插畬鎴?/g, '智能出题已完成')
    .replace(/鏅鸿兘鍑洪瀹屾垚/g, '智能出题完成')
    .replace(/棰樼洰/g, '题目')
    .replace(/绛旀/g, '答案')
    .replace(/瑙ｆ瀽/g, '解析')
    .replace(/涓嬭浇/g, '下载')
    .replace(/鍙偣鍑讳笅鏂规寜閽笅杞姐€?/g, '')
    .replace(/\uFFFD/g, '')
    .trim()
}

function videoCards(item: ChatMessage) {
  const content = displayContent(item)
  const groups = videoLinkGroups(item)
  const cards: { title: string; difficulty: string; duration: string; reason: string; links: any[] }[] = []
  const sectionPattern = /###\s*\d+\.\s*(.+?)\n([\s\S]*?)(?=\n###\s*\d+\.|\n##\s*使用建议|$)/g
  let match: RegExpExecArray | null

  while ((match = sectionPattern.exec(content))) {
    const title = match[1].trim()
    const body = match[2] || ''
    const group = groups.find((entry) => entry.title === title)
    cards.push({
      title,
      difficulty: extractVideoField(body, '难度'),
      duration: extractVideoField(body, '建议时长'),
      reason: extractVideoField(body, '推荐理由'),
      links: group?.links || [],
    })
  }

  if (!cards.length) {
    return groups.map((group) => ({
      title: group.title,
      difficulty: '',
      duration: '',
      reason: '',
      links: group.links,
    }))
  }
  return cards
}

function extractVideoField(body: string, label: string) {
  const line = body.split('\n').find((item) => item.trim().startsWith(`- ${label}：`))
  return line?.replace(`- ${label}：`, '').trim() || ''
}

function videoUsageTips(item: ChatMessage) {
  const content = displayContent(item)
  const tips = content.match(/##\s*使用建议\s*([\s\S]*)$/)?.[1] || ''
  return tips
    .split('\n')
    .map((line) => line.replace(/^-\s*/, '').trim())
    .filter(Boolean)
}

function videoLinkGroups(item: ChatMessage) {
  const links = [...(item.downloads || []), ...(item.resources || [])].filter((resource: any) => resource?.kind === 'video' && resource?.url)
  const groups: { title: string; links: any[] }[] = []
  for (const link of links) {
    const title = link.videoTitle || '视频推荐'
    let group = groups.find((entry) => entry.title === title)
    if (!group) {
      group = { title, links: [] }
      groups.push(group)
    }
    group.links.push(link)
  }
  return groups
}

function nonVideoDownloads(item: ChatMessage) {
  return (item.downloads || []).filter((resource: any) => resource?.kind !== 'video')
}

function nonVideoResources(item: ChatMessage) {
  return (item.resources || []).filter((resource: any) => resource?.kind !== 'video' && resource?.kind !== 'mindmap')
}

async function downloadWord(chatMessage: ChatMessage) {
  const title = activeSession.value?.title || '智能出题'
  const safeTitle = safeFileName(title)
  const content = chatMessage.mode === 'quiz' ? cleanQuizContent(chatMessage.content) : chatMessage.content
  const payload = {
    title,
    content,
    file_name: `${safeTitle}_练习题.docx`,
    template: 'quiz_export_v1',
  }

  try {
    const resp = await fetch('/api/export/word', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!resp.ok) throw new Error(`Word 导出失败：HTTP ${resp.status}`)
    const blob = await resp.blob()
    const disposition = resp.headers.get('content-disposition') || ''
    downloadBlob(blob, parseDownloadName(disposition) || payload.file_name)
  } catch (error: any) {
    message.value = error?.message || 'Word 导出失败，本次没有生成本地模板文件'
  }
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function buildRtfBlob(title: string, content: string) {
  const body = [
    '{\\rtf1\\ansi\\ansicpg65001\\deff0',
    '{\\fonttbl{\\f0 Microsoft YaHei;}{\\f1 SimSun;}}',
    '\\viewkind4\\uc1\\paperw11906\\paperh16838\\margl1440\\margr1440\\margt1200\\margb1200',
    `\\pard\\qc\\b\\fs32 ${toRtfText(title)}\\b0\\par`,
    '\\pard\\sa220\\fs22\\par',
    ...content.split(/\r?\n/).map((line) => `\\pard\\sa120\\fs22 ${toRtfText(line || ' ')}\\par`),
    '}',
  ].join('\n')
  return new Blob([body], { type: 'application/rtf;charset=utf-8' })
}

function toRtfText(text: string) {
  return String(text || '')
    .replace(/[\\{}]/g, (char) => `\\${char}`)
    .replace(/\t/g, '\\tab ')
    .replace(/[^\x00-\x7F]/g, (char) => `\\u${char.charCodeAt(0)}?`)
}

function safeFileName(text: string) {
  return String(text || '下载')
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/\s+/g, '_')
    .slice(0, 60)
}

function parseDownloadName(disposition: string) {
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8?.[1]) return decodeURIComponent(utf8[1])
  const ascii = disposition.match(/filename="?([^"]+)"?/i)
  return ascii?.[1] || ''
}

async function downloadImage(resource: any) {
  const imageUrl = resource?.image_url || resource?.url || resource?.download_url
  if (!imageUrl) return
  const payload = {
    image_url: imageUrl,
    title: resource?.title || '生成图片',
    file_name: `${safeFileName(resource?.title || '生成图片')}.png`,
    headers: {},
  }

  try {
    const resp = await fetch('/api/export/image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!resp.ok) throw new Error(`图片导出失败：HTTP ${resp.status}`)
    const blob = await resp.blob()
    const disposition = resp.headers.get('content-disposition') || ''
    downloadBlob(blob, parseDownloadName(disposition) || payload.file_name)
  } catch (error: any) {
    message.value = error?.message || '图片导出失败，本次没有打开替代资源'
  }
}

onMounted(() => {
  loadSessions()
})
</script>

<template>
  <div class="multimodal-page multimodal-chat-shell">
    <aside class="multi-chat-sidebar">
      <div class="multi-user-card">
        <span class="multi-avatar"><Bot :size="18" /></span>
        <strong>多模态实验室</strong>
      </div>

      <nav class="multi-side-nav" aria-label="多模态工具">
        <button
          v-for="item in modeItems"
          :key="item.key"
          type="button"
          :class="{ active: activeMode === item.key }"
          @click="activeMode = item.key"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="multi-side-section">
        <span>历史资源</span>
        <div v-if="!historyItems.length" class="multi-history-empty">暂无历史对话</div>
        <div
          v-for="item in historyItems"
          :key="`${item.kind}-${item.id}`"
          class="multi-history-row"
          :class="{ active: item.session?.id === activeSessionId }"
          role="button"
          tabindex="0"
          @click="selectSession(item.session!)"
        >
          <MessageSquare :size="14" />
          <span>{{ item.title }}</span>
          <button
            type="button"
            title="删除历史对话"
            class="multi-delete-history"
            @click.stop="deleteSession(item.session!.id)"
          >
            <Trash2 :size="13" />
          </button>
        </div>
      </div>

    </aside>

    <main class="multi-chat-main">
      <header class="multi-chat-topbar">
        <button type="button" title="新对话" aria-label="新对话" :disabled="!activeSessionId" @click="activeSessionId = ''"><MoreHorizontal :size="19" /></button>
        <div>
          <strong>{{ activeSession?.title || '新对话' }}</strong>
          <span>用户通过对话提出要求，系统会选择对应能力</span>
        </div>
        <div class="multi-top-actions">
          <button type="button" title="搜索资源" aria-label="搜索资源" @click="searchResources"><Search :size="18" /></button>
          <button type="button" title="打开资源库" aria-label="打开资源库" @click="openResourceLibrary"><Folder :size="18" /></button>
        </div>
      </header>

      <section class="multi-chat-canvas">
        <div v-if="!activeSession" class="multi-welcome">
          <h2>有什么我能帮你的吗？</h2>
          <div class="multi-prompt-cloud">
            <button v-for="prompt in quickPrompts" :key="prompt" type="button" data-action-kind="compose" @click="pickPrompt(prompt)">
              {{ prompt }}
            </button>
          </div>
        </div>

        <div v-else class="multi-message-list">
          <article v-for="item in activeSession.messages" :key="item.id" class="multi-chat-message" :class="item.role">
            <div
              v-if="item.role === 'assistant' && item.mode === 'code'"
              class="multi-code-case"
              v-html="renderCodeCase(item.content)"
            ></div>
            <div v-else-if="item.mode === 'video'" class="multi-video-card-list">
              <section v-for="card in videoCards(item)" :key="card.title" class="multi-video-card">
                <h3>{{ card.title }}</h3>
                <div class="multi-video-meta">
                  <span v-if="card.difficulty">{{ card.difficulty }}</span>
                  <span v-if="card.duration">{{ card.duration }}</span>
                </div>
                <p v-if="card.reason">{{ card.reason }}</p>
                <div v-if="card.links.length" class="multi-video-platforms">
                  <button v-for="link in card.links" :key="link.id || link.url" type="button" @click="openResource(link)">
                    {{ link.platformName || link.title }}搜索
                  </button>
                </div>
              </section>
              <div v-if="videoUsageTips(item).length" class="multi-video-tips">
                <span v-for="tip in videoUsageTips(item)" :key="tip">{{ tip }}</span>
              </div>
            </div>
            <div v-else-if="item.mode === 'mindmap'" class="multi-mindmap-message">
              <div class="multi-readable-content" v-html="renderCodeCase(displayContent(item))"></div>
              <div v-if="mindmapResource(item)" class="multi-mindmap-tree" v-html="renderMindmapTree(item)"></div>
            </div>
            <div v-else class="multi-readable-content" v-html="renderCodeCase(displayContent(item))"></div>
            <div v-if="imageResources(item).length" class="multi-image-previews">
              <figure v-for="image in imageResources(item)" :key="image.id || image.url || image.image_url">
                <img :src="image.image_url || image.url || image.download_url" :alt="image.title || '生成图片'" />
                <figcaption>{{ image.prompt || image.title || '生成图片' }}</figcaption>
              </figure>
            </div>
            <div v-if="item.mode === 'quiz'" class="multi-message-resources">
              <button type="button" @click="downloadWord(item)">下载</button>
            </div>
            <div v-else-if="nonVideoResources(item).length || nonVideoDownloads(item).length" class="multi-message-resources">
              <button
                v-for="download in nonVideoDownloads(item)"
                :key="download.id || download.title"
                type="button"
                @click="download.kind === 'image' ? downloadImage(download) : openResource(download)"
              >
                {{ download.title }}
              </button>
              <button
                v-for="resource in nonVideoResources(item)"
                :key="resource.id || resource.title"
                type="button"
                @click="resource.kind === 'image' ? downloadImage(resource) : openResource(resource)"
              >
                {{ resource.title }}
              </button>
            </div>
          </article>
        </div>

        <div v-if="message" class="multi-message">{{ message }}</div>

      </section>

      <section class="multi-composer-wrap">
        <div class="multi-composer">
          <textarea
            v-model="promptInput"
            rows="2"
            placeholder="发消息或按住空格说话..."
            @keydown.enter.exact.prevent="submitPrompt"
          ></textarea>
          <div class="multi-composer-tools">
            <button type="button" title="添加素材" @click="attachMaterial"><Paperclip :size="19" /></button>
            <input ref="materialInput" type="file" accept=".txt,.md,.csv,.json" hidden @change="handleMaterial" />
            <button type="button" data-action-kind="compose" title="快速生成" :class="{ active: activeMode === 'auto' }" @click="activeMode = 'auto'"><Zap :size="17" /><span>快速</span></button>
            <button type="button" data-action-kind="compose" title="帮我写作" :class="{ active: activeMode === 'writing' }" @click="activeMode = 'writing'"><FileText :size="17" /><span>帮我写作</span></button>
            <button type="button" data-action-kind="compose" title="编程" :class="{ active: activeMode === 'code' }" @click="activeMode = 'code'"><Code2 :size="17" /><span>编程</span></button>
            <button type="button" data-action-kind="compose" title="图像生成" :class="{ active: activeMode === 'visual' }" @click="activeMode = 'visual'"><Image :size="17" /><span>图像生成</span></button>
            <button type="button" data-action-kind="compose" title="视频推荐" :class="{ active: activeMode === 'video' }" @click="activeMode = 'video'"><PlayCircle :size="17" /><span>视频推荐</span></button>
            <button type="button" data-action-kind="compose" title="智能出题" :class="{ active: activeMode === 'quiz' }" @click="activeMode = 'quiz'"><ClipboardList :size="17" /><span>智能出题</span></button>
            <button type="button" data-action-kind="compose" title="思维导图" :class="{ active: activeMode === 'mindmap' }" @click="activeMode = 'mindmap'"><GitBranch :size="17" /><span>思维导图</span></button>
            <button type="button" title="更多" :class="{ active: showMoreModes }" :aria-expanded="showMoreModes" @click="openMoreModes"><MoreHorizontal :size="17" /><span>更多</span></button>
            <button class="multi-send" type="button" :disabled="Boolean(loading) || !promptInput.trim()" title="发送" @click="submitPrompt">
              <Wand2 v-if="loading" :size="18" />
              <Send v-else :size="18" />
            </button>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
