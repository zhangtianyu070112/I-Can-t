import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: false,
})

const defaultLinkOpen = markdown.renderer.rules.link_open

markdown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const hrefIndex = token.attrIndex('href')
  const href = hrefIndex >= 0 ? token.attrs?.[hrefIndex]?.[1] || '' : ''

  if (!/^https?:\/\//i.test(href) && !href.startsWith('/') && !href.startsWith('#')) {
    token.attrSet('href', '#')
  }

  token.attrSet('target', '_blank')
  token.attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen ? defaultLinkOpen(tokens, idx, options, env, self) : self.renderToken(tokens, idx, options)
}

let domPurifyHookInstalled = false

function installDomPurifyHook() {
  if (domPurifyHookInstalled) return
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node instanceof HTMLAnchorElement) {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer')
    }
  })
  domPurifyHookInstalled = true
}

export function normaliseMarkdownForStreaming(source: string) {
  let text = normaliseGeneratedMarkdown(source)
  const fenceMatches = text.match(/```/g) || []
  if (fenceMatches.length % 2 === 1) text += '\n```'
  return text
}

function scalar(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return `\`${JSON.stringify(value, null, 2)}\``
}

const readableLabels: Record<string, string> = {
  meta: '资源信息', course: '课程', chapter: '章节', weak_points: '重点内容', review_plan: '复习建议',
  type: '题型', options: '选项', answer: '参考答案', correct_answer: '正确答案',
  analysis: '解析', explanation: '说明', tags: '知识标签', difficulty: '难度',
}

const questionTypeLabels: Record<string, string> = {
  single_choice: '单选题', multiple_choice: '多选题', blank: '填空题',
  short_answer: '简答题', true_false: '判断题', coding: '编程题',
}

function readableScalar(key: string, value: unknown): string {
  if (key === 'type' && typeof value === 'string') return questionTypeLabels[value] || value
  if (key === 'difficulty' && typeof value === 'number') return ['未分级', '基础', '进阶', '挑战'][value] || `${value} 级`
  return scalar(value)
}

function jsonToReadableMarkdown(value: unknown, depth = 1): string {
  if (Array.isArray(value)) {
    return value.map((item, index) => {
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        const record = item as Record<string, unknown>
        const title = scalar(record.stem || record.question || record.title || record.name || `第 ${index + 1} 项`)
        const lines = [`${'#'.repeat(Math.min(depth + 1, 5))} ${title}`]
        for (const [key, child] of Object.entries(record)) {
          if (['stem', 'question', 'title', 'name'].includes(key)) continue
          if (Array.isArray(child)) {
            lines.push(`**${readableLabels[key] || key}**`)
            lines.push(...child.map((entry) => `- ${scalar(entry)}`))
          } else if (child && typeof child === 'object') {
            lines.push(`**${readableLabels[key] || key}**\n\n${jsonToReadableMarkdown(child, depth + 1)}`)
          } else if (readableScalar(key, child)) {
            lines.push(`**${readableLabels[key] || key}：** ${readableScalar(key, child)}`)
          }
        }
        return lines.join('\n\n')
      }
      return `- ${scalar(item)}`
    }).join('\n\n')
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    const preferred = ['questions', 'items', 'resources', 'content', 'result']
    const primary = preferred.find((key) => Array.isArray(record[key]))
    if (primary) {
      const heading = primary === 'questions' ? '# 定制练习题库' : '# 生成结果'
      const metadata = Object.entries(record)
        .filter(([key]) => key !== primary && key !== 'generated_by')
        .map(([key, child]) => {
          if (child && typeof child === 'object') return `## ${readableLabels[key] || key}\n\n${jsonToReadableMarkdown(child, depth + 1)}`
          return `**${readableLabels[key] || key}：** ${readableScalar(key, child)}`
        })
        .join('\n\n')
      return [heading, metadata, jsonToReadableMarkdown(record[primary], depth)].filter(Boolean).join('\n\n')
    }
    return Object.entries(record).map(([key, child]) => {
      if (key === 'generated_by') return ''
      if (child && typeof child === 'object') return `${'#'.repeat(Math.min(depth + 1, 5))} ${readableLabels[key] || key}\n\n${jsonToReadableMarkdown(child, depth + 1)}`
      return `**${readableLabels[key] || key}：** ${readableScalar(key, child)}`
    }).join('\n\n')
  }
  return scalar(value)
}

export function normaliseGeneratedMarkdown(source: string) {
  let text = String(source || '').replace(/\r\n/g, '\n').trim()
  if (!text) return ''
  if (!text.includes('\n') && /\\n|\\t/.test(text)) {
    text = text.replace(/\\n/g, '\n').replace(/\\t/g, '  ')
  }
  if ((text.startsWith('{') && text.endsWith('}')) || (text.startsWith('[') && text.endsWith(']'))) {
    try {
      return jsonToReadableMarkdown(JSON.parse(text))
    } catch {
      // Model output may resemble JSON without being valid; render as Markdown.
    }
  }
  return text
}

export function renderMarkdown(source: string, options: { streaming?: boolean } = {}) {
  installDomPurifyHook()
  const input = options.streaming ? normaliseMarkdownForStreaming(source) : normaliseGeneratedMarkdown(source)
  const rawHtml = markdown.render(input)

  return DOMPurify.sanitize(rawHtml, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['target', 'rel', 'class'],
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button'],
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'style'],
  })
}
