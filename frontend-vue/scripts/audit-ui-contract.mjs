import fs from 'node:fs'
import path from 'node:path'

const sourceRoot = path.resolve('src')
const failures = []

function visit(directory) {
  for (const name of fs.readdirSync(directory)) {
    const file = path.join(directory, name)
    const stat = fs.statSync(file)
    if (stat.isDirectory()) visit(file)
    else if (file.endsWith('.vue')) auditButtons(file)
  }
}

function auditButtons(file) {
  const source = fs.readFileSync(file, 'utf8').split('<template v-if="false">')[0]
  if (/from\s+["']@\/mock\//.test(source)) {
    failures.push(`${path.relative(process.cwd(), file)}: active page/component imports fixed mock data`)
  }
  const openingTags = source.match(/<button\b(?:"[^"]*"|'[^']*'|[^>])*>/g) || []
  for (const tag of openingTags) {
    const actionable = /@click(?:\.[\w-]+)*\s*=|type\s*=\s*["']submit["']/.test(tag)
    if (!actionable) failures.push(`${path.relative(process.cwd(), file)}: button lacks @click or submit behavior: ${tag.replace(/\s+/g, ' ')}`)
  }
}

visit(sourceRoot)

const forbidden = new Map([
  ['src/pages/ProfilePage.vue', ['radarFallbackValues', '[62,78,83,91,69,74]', "['今天 10:24'"]],
  ['src/pages/WorkshopPage.vue', ['demoResources', 'demo-recursion-video', 'defaultAgentTrace']],
  ['src/pages/PathPage.vue', ['targetStages']],
  ['src/pages/EvaluatePage.vue', ['Math.max(20,42-index*7)', '评估可信度：中']],
  ['src/pages/MultimodalPage.vue', ['buildRtfBlob(title, content)', 'API 未接入时使用本地 RTF 模板兜底']],
  ['src/composables/useStudent.ts', ["localStorage.getItem(key) || 'demo'"]],
])

for (const [file, patterns] of forbidden) {
  const source = fs.readFileSync(file, 'utf8').split('<template v-if="false">')[0]
  for (const pattern of patterns) {
    if (source.includes(pattern)) failures.push(`${file}: contains forbidden fixed UI fallback: ${pattern}`)
  }
}

const backendForbidden = new Map([
  ['../backend/app/api/routers/delivery.py', [
    'resource = _create_demo_resource(',
    'score": max(40',
    'weaknesses": weak or [',
  ]],
  ['../backend/app/agents/orchestrator.py', [
    'using local fallback',
    'for index in range(max(5, len(raw_steps)))',
    'available = resource_types or [',
  ]],
  ['../backend/app/api/routers/multimodal.py', [
    'raw_videos = [',
    'return f"""# 代码实操案例',
    'return f"""# 语音辅导方案',
    '模型不可用时使用本地脚本',
    'except Exception:\n            pass',
  ]],
  ['../backend/app/api/routers/ppt.py', [
    'req.outline or _normalize_outline(req)',
    'slides = fallback["slides"]',
  ]],
  ['../backend/app/services/knowledge_hub.py', [
    'record.get("mastery", inferred)',
  ]],
])

for (const [file, patterns] of backendForbidden) {
  const source = fs.readFileSync(file, 'utf8')
  for (const pattern of patterns) {
    if (source.includes(pattern)) failures.push(`${file}: contains active synthetic-data fallback: ${pattern}`)
  }
}

if (failures.length) {
  console.error(failures.join('\n'))
  process.exit(1)
}

console.log('UI contract audit passed: visible buttons are wired and target pages contain no known fixed-data fallbacks.')
