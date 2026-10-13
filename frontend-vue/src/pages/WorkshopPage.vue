<script setup lang="ts">
import { computed, onMounted, ref, type Component } from 'vue'
import {
  ArrowRight,
  BadgeCheck,
  BookOpen,
  Bot,
  Boxes,
  Check,
  CircleAlert,
  ClipboardCheck,
  Clock3,
  Download,
  Eye,
  FileArchive,
  FileInput,
  FileQuestion,
  FileText,
  FlaskConical,
  Layers3,
  LoaderCircle,
  Network,
  PackageCheck,
  RefreshCw,
  Share2,
  Sparkles,
  Target,
  Upload,
  UsersRound,
  Video,
  WandSparkles,
} from 'lucide-vue-next'
import MarkdownContent from '@/components/MarkdownContent.vue'
import { normaliseGeneratedMarkdown } from '@/utils/markdownRenderer'
import {
  exportResourcePackage,
  generateResourcePackStream,
  getWorkshopOverview,
  type ResourceSummary,
  type WorkshopOverview,
} from '@/api/learningApi'
import { useStudent } from '@/composables/useStudent'

type ResourceTypeOption = {
  value: string
  label: string
  short: string
  description: string
  icon: Component
  tone: string
}

const resourceTypes: ResourceTypeOption[] = [
  { value: 'lecture_doc', label: '讲解文档', short: '文档', description: '章节讲解、概念梳理、知识点总结', icon: FileText, tone: 'blue' },
  { value: 'mindmap', label: '思维导图', short: '导图', description: '知识点关系、层级结构可视化', icon: Share2, tone: 'cyan' },
  { value: 'question_bank', label: '练习题库', short: '题库', description: '诊断题、巩固题、阶段检测题', icon: ClipboardCheck, tone: 'violet' },
  { value: 'reading', label: '拓展阅读', short: '阅读', description: '背景知识、案例材料、延伸阅读', icon: BookOpen, tone: 'indigo' },
  { value: 'practice_case', label: '实验案例', short: '案例', description: '代码/建模任务、步骤说明', icon: FlaskConical, tone: 'purple' },
  { value: 'video_script', label: '视频脚本', short: '脚本', description: '录屏脚本、分镜提示、字幕草案', icon: Video, tone: 'sky' },
]

const agentLabels: Record<string, string> = {
  lecture: '课程讲解智能体',
  mindmap: '思维导图智能体',
  quiz: '题库设计智能体',
  reading: '拓展阅读智能体',
  practice: '实操案例智能体',
  video: '多模态脚本智能体',
  quality_check: '内容质量审查',
}

const { studentId, goals } = useStudent()
const overview = ref<WorkshopOverview | null>(null)
const overviewLoading = ref(true)
const overviewRefreshing = ref(false)
const generating = ref(false)
const exporting = ref(false)
const error = ref('')
const notice = ref('')
const uploadInput = ref<HTMLInputElement | null>(null)
const uploadMode = ref<'reference' | 'outline'>('reference')

const course = ref('')
const chapter = ref('')
const weakPoints = ref('')
const learningStyle = ref('')
const selectedTypes = ref<string[]>(['lecture_doc'])
const uploadedContext = ref<{ name: string; mode: string; text: string } | null>(null)
const showAllRecords = ref(false)

const generatedResources = ref<ResourceSummary[]>([])
const selectedResource = ref<ResourceSummary | null>(null)
const selectedResourceIds = ref<string[]>([])
const previewContent = ref('')
const previewLoading = ref(false)
const previewError = ref('')
const exportUrl = ref('')
const liveTrace = ref<Array<{ key: string; label: string; role: string; status: string; verified: boolean }>>([])
let previewRequestId = 0

const visibleResources = computed(() => generatedResources.value)
const selectedTypeLabels = computed(() => resourceTypes.filter((item) => selectedTypes.value.includes(item.value)).map((item) => item.label))
const selectedCount = computed(() => selectedResourceIds.value.length)
const readablePreviewContent = computed(() => normaliseGeneratedMarkdown(previewContent.value))
const displayedResources = computed(() => showAllRecords.value ? visibleResources.value : visibleResources.value.slice(0, 4))
const smartRecommendations = computed(() => {
  const tags = visibleResources.value.flatMap((item) => item.tags || [])
  return tags.filter((tag, index) => tags.indexOf(tag) === index).slice(0, 4)
})
const qualityLabel = computed(() => {
  const quality = overview.value?.quality
  if (!quality) return '等待质量检查'
  if (quality.status === 'ready') return '质量检查可用'
  if (quality.status === 'pending') return '等待生成结果'
  return quality.status
})

const traceItems = computed(() => {
  if (liveTrace.value.length) return liveTrace.value
  const trace = selectedResource.value?.agent_trace
  if (Array.isArray(trace) && trace.length) {
    return trace.map((item, index) => ({
      key: `${item?.agent || 'agent'}-${index}`,
      label: agentLabels[item?.agent] || item?.agent || `协作角色 ${index + 1}`,
      role: item?.task || item?.role || '参与本资源的生成与校验',
      status: item?.status || 'returned',
      verified: true,
    }))
  }
  if (selectedResource.value?.agent) {
    return [{
      key: selectedResource.value.agent,
      label: agentLabels[selectedResource.value.agent] || '资源生成智能体',
      role: '资源已生成并保存，可在预览区阅读或加入导出清单',
      status: 'persisted',
      verified: true,
    }]
  }
  return []
})
const displayTraceItems = computed(() => {
  return traceItems.value.slice(0, 7)
})

function updateLiveTrace(agent: string, patch: Partial<{ label: string; role: string; status: string; verified: boolean }>) {
  const localizedPatch = { ...patch, label: agentLabels[agent] || patch.label || '资源生成智能体' }
  const index = liveTrace.value.findIndex((item) => item.key === agent)
  if (index < 0) {
    liveTrace.value.push({ key: agent, label: localizedPatch.label, role: patch.role || '等待后端处理', status: patch.status || 'pending', verified: Boolean(patch.verified) })
    return
  }
  liveTrace.value[index] = { ...liveTrace.value[index], ...localizedPatch }
}

function labelForType(type: string) {
  return resourceTypes.find((item) => item.value === type)?.label
    || overview.value?.distribution.find((item) => item.type === type)?.label
    || (type === 'quality_check' ? '质量审查' : '')
    || type
}

function completedResourceMessage(resource?: ResourceSummary) {
  if (!resource) return '生成流程已完成'
  return `${labelForType(resource.type)}已生成并保存，可在资源预览中阅读`
}

function splitWeakPoints() {
  return weakPoints.value
    .split(/[，,、;；\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function formatDate(value: string) {
  if (!value) return '未记录时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

function toggleResourceType(value: string) {
  error.value = ''
  notice.value = ''
  selectedTypes.value = selectedTypes.value.includes(value)
    ? selectedTypes.value.filter((item) => item !== value)
    : [...selectedTypes.value, value]
}

function chooseUpload(mode: 'reference' | 'outline') {
  uploadMode.value = mode
  uploadInput.value?.click()
}

async function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (!['txt', 'md', 'csv', 'json'].includes(extension || '')) {
    error.value = '当前真实解析链路支持 TXT、Markdown、CSV 和 JSON；PDF、Word 请先转为文本后导入。'
    input.value = ''
    return
  }
  const text = await file.text()
  if (!text.trim()) {
    error.value = '导入文件没有可分析的文本内容。'
    input.value = ''
    return
  }
  uploadedContext.value = { name: file.name, mode: uploadMode.value, text: text.slice(0, 20_000) }
  notice.value = `${uploadMode.value === 'outline' ? '课程大纲' : '参考资料'}已解析：${file.name}（${text.length} 字符），生成时将发送到后端分析。`
  input.value = ''
}

async function loadOverview() {
  const initial = !overview.value
  if (initial) overviewLoading.value = true
  else overviewRefreshing.value = true
  error.value = ''
  try {
    const previousSelection = selectedResource.value?.id
    overview.value = await getWorkshopOverview(studentId.value)
    generatedResources.value = overview.value.latest || []
    const nextSelection = visibleResources.value.find((item) => item.id === previousSelection) || visibleResources.value[0]
    if (nextSelection) {
      await openResource(nextSelection)
    } else {
      selectedResource.value = null
      previewContent.value = ''
    }
  } catch (reason: any) {
    error.value = reason?.message || '资源工坊数据加载失败'
  } finally {
    overviewLoading.value = false
    overviewRefreshing.value = false
  }
}

async function generateResources() {
  if (generating.value) return
  const naturalRequest = weakPoints.value.trim()
  if (!course.value.trim() && !chapter.value.trim() && !naturalRequest) {
    error.value = '请描述要生成的课程资源、章节范围或具体学习需求。'
    return
  }
  if (!selectedTypes.value.length) {
    error.value = '请至少选择一种资源类型。'
    return
  }

  generating.value = true
  liveTrace.value = []
  error.value = ''
  notice.value = ''
  exportUrl.value = ''
  try {
    const inferredTopic = naturalRequest.split(/[，。；;\n]/).map((item) => item.trim()).find(Boolean) || naturalRequest
    const resolvedCourse = course.value.trim() || inferredTopic.slice(0, 48)
    const resolvedChapter = chapter.value.trim() || naturalRequest.slice(0, 96)
    const generationPayload = {
      student_id: studentId.value,
      requirement: {
        course: resolvedCourse,
        chapter: resolvedChapter,
        goals: goals.value || undefined,
        weak_points: splitWeakPoints(),
        resource_types: selectedTypes.value,
        style: learningStyle.value.trim(),
        source_documents: uploadedContext.value ? [uploadedContext.value] : [],
      },
    }
    const resources = await generateResourcePackStream(generationPayload, (event) => {
      if (event.type === 'start') {
        for (const agent of event.agents || []) updateLiveTrace(agent, { status: 'pending', role: '已由后端加入本轮处理队列' })
      } else if (event.type === 'agent_start' && event.agent) {
        updateLiveTrace(event.agent, { label: event.title || event.agent, status: 'running', role: '正在调用真实生成或质量检查流程' })
      } else if (event.type === 'agent_chunk' && event.agent) {
        updateLiveTrace(event.agent, { status: 'running', role: `正在生成${agentLabels[event.agent] || '学习资源'}内容` })
      } else if (event.type === 'agent_done' && event.agent) {
        updateLiveTrace(event.agent, { status: 'completed', role: completedResourceMessage(event.resource), verified: true })
      }
    })
    generatedResources.value = resources
    selectedResourceIds.value = resources.map((item) => item.id).filter(Boolean)
    if (resources[0]) await openResource(resources[0])
    notice.value = resources.length
      ? `后端已返回 ${resources.length} 份资源，已默认加入导出清单。`
      : '后端已完成请求，但本轮没有返回资源。请调整范围后重试。'
    await loadOverview()
  } catch (reason: any) {
    error.value = reason?.message || '资源生成失败，请保留当前配置后重试。'
  } finally {
    generating.value = false
  }
}

async function openResource(resource: ResourceSummary) {
  const requestId = ++previewRequestId
  const derivedUrl = resource.preview_url || (resource.content_uri ? `/${String(resource.content_uri).replace(/^\/+/, '')}` : '')
  const normalizedResource = { ...resource, preview_url: derivedUrl }
  selectedResource.value = normalizedResource
  previewContent.value = resource.content || resource.summary || ''
  previewError.value = ''
  if (previewContent.value) return
  if (!derivedUrl) {
    previewError.value = '资源已生成，但后端没有返回可读取的正文地址。'
    return
  }

  previewLoading.value = true
  try {
    const response = await fetch(derivedUrl)
    if (!response.ok) throw new Error(`预览请求失败（${response.status}）`)
    const content = await response.text()
    if (requestId === previewRequestId) previewContent.value = content
  } catch (reason: any) {
    if (requestId === previewRequestId) previewError.value = reason?.message || '资源预览加载失败'
  } finally {
    if (requestId === previewRequestId) previewLoading.value = false
  }
}

function toggleResourceSelection(resourceId: string) {
  selectedResourceIds.value = selectedResourceIds.value.includes(resourceId)
    ? selectedResourceIds.value.filter((item) => item !== resourceId)
    : [...selectedResourceIds.value, resourceId]
}

function toggleSelectAll() {
  const availableIds = visibleResources.value.map((item) => item.id).filter(Boolean)
  selectedResourceIds.value = selectedResourceIds.value.length === availableIds.length ? [] : availableIds
}

async function exportSelected() {
  if (exporting.value || !selectedResourceIds.value.length) return
  exporting.value = true
  error.value = ''
  notice.value = ''
  exportUrl.value = ''
  try {
    exportUrl.value = await exportResourcePackage(studentId.value, selectedResourceIds.value)
    if (!exportUrl.value) throw new Error('后端未返回下载地址')
    notice.value = '资源包已生成。请点击“下载 ZIP”保存到本地。'
  } catch (reason: any) {
    error.value = reason?.message || '资源包导出失败'
  } finally {
    exporting.value = false
  }
}

onMounted(loadOverview)
</script>

<template>
  <div class="competition-page workshop-command-page">
    <section class="shot-workshop" aria-label="资源工坊">
      <div v-if="error" class="shot-notice is-error"><CircleAlert :size="18" />{{ error }}<button type="button" @click="loadOverview">重新同步</button></div>
      <div v-if="notice" class="shot-notice"><Check :size="18" />{{ notice }}</div>

      <div v-if="overviewLoading && !overview" class="shot-loading"><span class="os-spinner"></span><p>正在读取资源清单与协作角色……</p></div>
      <template v-else>
        <main class="shot-workshop__main">
          <header class="shot-workshop-hero">
            <div class="shot-workshop-copy">
              <h1>资源工坊 <span><Sparkles :size="24" /></span></h1>
              <p>AI驱动的个性化学习资源生成中心</p>
              <ul>
                <li><i><Bot :size="20" /></i><span><strong>多智能体协同</strong><small>按用户选择的资源类型调度真实生成智能体与质量审计</small></span></li>
                <li><i><Boxes :size="20" /></i><span><strong>多模态资源</strong><small>支持文档、图谱、题库、视频等多种资源类型</small></span></li>
                <li><i><Sparkles :size="20" /></i><span><strong>个性化定制</strong><small>基于学习画像与需求生成专属学习资源</small></span></li>
              </ul>
            </div>
            <div class="shot-agent-orbit" aria-label="多智能体协同示意">
              <span class="orbit-path" aria-hidden="true"></span>
              <span class="orbit-platform" aria-hidden="true"><b></b></span>
              <span class="orbit-core" aria-hidden="true"><b class="cube-front"><span>AI</span></b><b class="cube-side"><span>AI</span></b><b class="cube-top"></b></span>
              <i class="agent-a"><span><FileQuestion :size="18" /></span><b>需求分析<small>智能体</small></b></i>
              <i class="agent-b"><span><ClipboardCheck :size="18" /></span><b>讲解策划<small>智能体</small></b></i>
              <i class="agent-c"><span><Network :size="18" /></span><b>训练设计<small>智能体</small></b></i>
              <i class="agent-d"><span><BookOpen :size="18" /></span><b>阅读扩展<small>智能体</small></b></i>
              <i class="agent-e"><span><Sparkles :size="18" /></span><b>多模态<small>智能体</small></b></i>
            </div>
          </header>

          <form class="shot-create" @submit.prevent="generateResources"><header><strong>快速创建资源</strong><small>选择资源类型，输入需求，AI 帮你一键生成</small></header>
            <div class="shot-type-grid"><button v-for="item in resourceTypes" :key="item.value" type="button" :class="{ active: selectedTypes.includes(item.value) }" :aria-pressed="selectedTypes.includes(item.value)" @click="toggleResourceType(item.value)"><i :class="`tone-${item.tone}`"><component :is="item.icon" :size="25" /></i><strong>{{ item.label }}</strong><small>{{ item.description }}</small><Check v-if="selectedTypes.includes(item.value)" :size="14" /></button></div>
            <div class="shot-brief-fields"><label><span>课程 / 主题</span><input v-model="course" placeholder="输入要分析的真实课程或主题" /></label><label><span>章节 / 场景</span><input v-model="chapter" placeholder="输入章节、任务或应用场景" /></label></div>
            <textarea v-model="weakPoints" maxlength="500" rows="3" placeholder="请输入你的需求，例如：&#10;“生成《Python 函数》章节的讲解文档，重点讲解函数定义、参数、返回值，并配有示例代码”&#10;或上传参考资料，我们将基于你的需求生成高质量资源。"></textarea>
            <small class="shot-char-count">{{ weakPoints.length }}/500</small>
            <footer><div><button type="button" @click="chooseUpload('reference')"><Upload :size="14" />上传参考资料</button><button type="button" @click="chooseUpload('outline')"><FileInput :size="14" />导入课程大纲</button><input ref="uploadInput" class="shot-file-input" type="file" accept=".txt,.md,.csv,.json" @change="handleUpload" /></div><button class="shot-generate" type="submit" :disabled="generating || !selectedTypes.length || (!course.trim() && !chapter.trim() && !weakPoints.trim())"><LoaderCircle v-if="generating" class="spin" :size="17" /><WandSparkles v-else :size="17" />{{ generating ? '多智能体生成中' : '生成资源' }} <ArrowRight :size="16" /></button></footer>
          </form>

          <section class="shot-records"><header><strong><i class="shot-section-mark"></i>生成记录</strong><button type="button" :disabled="visibleResources.length <= 4" :aria-expanded="showAllRecords" @click="showAllRecords = !showAllRecords">{{ showAllRecords ? '收起' : '查看全部' }} <ArrowRight :size="14" /></button></header><div class="shot-record-grid"><button v-for="resource in displayedResources" :key="resource.id" type="button" :class="{ active: selectedResource?.id === resource.id }" @click="openResource(resource)"><span><strong>{{ resource.title }}</strong><em>{{ resource.type_label || labelForType(resource.type) }}</em></span><small>{{ formatDate(resource.created_at) }}</small><i><Check :size="12" />已完成</i></button><div v-if="!visibleResources.length" class="shot-empty">暂无真实生成记录，提交上方需求后由后端分析并生成。</div></div></section>
        </main>

        <aside class="shot-workshop__side">
        <section class="shot-progress"><header><strong><i class="shot-section-mark"></i>协同生成进度</strong><small>{{ generating ? `正在生成：${selectedTypeLabels.join('、')}` : selectedResource ? `已载入：${selectedResource.title}` : '等待提交真实生成任务' }}</small></header><ol><li v-for="agent in displayTraceItems" :key="agent.key" :class="{ current: agent.status === 'running' }"><i><Check v-if="agent.status === 'completed' || agent.status === 'persisted'" :size="13" /><LoaderCircle v-else-if="agent.status === 'running'" class="spin" :size="13" /><Clock3 v-else :size="13" /></i><span><strong>{{ agent.label }}</strong><small>{{ agent.role }}</small></span><em><LoaderCircle v-if="agent.status === 'running'" class="spin" :size="12" /><Check v-else-if="agent.verified" :size="13" />{{ agent.status === 'running' ? '处理中' : agent.verified ? '已完成' : '等待' }}</em></li></ol><p v-if="!displayTraceItems.length" class="shot-progress-empty">尚无本轮真实处理事件</p></section>
          <section class="shot-preview"><header><strong><i class="shot-section-mark"></i>资源预览</strong></header><div class="shot-preview-paper"><template v-if="selectedResource"><header><span><FileText :size="14" /><strong>{{ selectedResource.title }}</strong><em>{{ resourceTypes.find((item) => item.value === selectedResource?.type)?.short || labelForType(selectedResource.type) }}</em></span></header><div class="shot-preview-content"><div v-if="previewLoading">正在载入正文……</div><MarkdownContent v-else-if="readablePreviewContent" :content="readablePreviewContent" /><p v-else>{{ selectedResource.summary || '该资源没有可预览正文。' }}</p></div></template><p v-else>生成或选择一份资源后查看预览。</p></div><div class="shot-dots"><i></i><i></i><i></i></div></section>
          <section class="shot-smart-recommend"><header><strong><i class="shot-section-mark"></i>内容标签</strong><small>从真实生成资源中提取</small></header><div><span v-for="tag in smartRecommendations" :key="tag">{{ tag }}</span><small v-if="!smartRecommendations.length">暂无可提取标签</small></div></section>
          <section class="shot-export"><button type="button" :disabled="!selectedCount || exporting" @click="exportSelected"><FileArchive :size="16" />{{ exporting ? '打包中' : `导出已选 ${selectedCount || ''}` }}</button><a v-if="exportUrl" :href="exportUrl" target="_blank" rel="noreferrer"><Download :size="16" />下载 ZIP</a></section>
        </aside>
      </template>
    </section>

    <template v-if="false">
    <header class="workshop-topbar">
      <div class="workshop-heading"><span class="os-eyebrow"><WandSparkles :size="14" /> MULTI-AGENT WORKSHOP</span><div><h1>多智能体资源工坊</h1><p>把画像证据编排为可预览、可审计、可批量交付的学习资源。</p></div></div>
      <div class="os-page-actions"><button class="os-button" type="button" :disabled="overviewLoading || overviewRefreshing" @click="loadOverview"><LoaderCircle v-if="overviewRefreshing" class="spin" :size="15" /><RefreshCw v-else :size="15" />{{ overviewRefreshing ? '同步中' : '刷新工坊' }}</button><RouterLink class="os-button os-button-primary" to="/exercise">进入做题诊断 <ArrowRight :size="15" /></RouterLink></div>
    </header>

    <section class="workshop-flowbar" aria-label="资源生产流程">
      <span class="flow-step is-current"><b>01</b><i><strong>定义任务</strong><small>{{ selectedTypes.length }} 类交付类型</small></i></span>
      <span class="flow-step"><b>02</b><i><strong>资源队列</strong><small>{{ visibleResources.length }} 份可用资源</small></i></span>
      <span class="flow-step"><b>03</b><i><strong>实时预览</strong><small>{{ selectedResource ? '已载入当前资源' : '等待选择资源' }}</small></i></span>
      <span class="flow-step flow-delivery"><b>04</b><i><strong>批量交付</strong><small>{{ selectedCount }} 项已加入导出</small></i></span>
    </section>

    <div v-if="error" class="os-alert workshop-alert" role="alert" aria-live="assertive"><CircleAlert :size="18" aria-hidden="true" /><span><strong>当前操作未完成</strong><small>{{ error }}</small></span><button class="os-button" type="button" :disabled="generating || overviewLoading" @click="loadOverview"><RefreshCw :size="14" />重新同步</button></div>
    <div v-if="notice" class="workshop-notice" role="status" aria-live="polite"><Check :size="16" />{{ notice }}</div>

    <section v-if="overviewLoading && !overview" class="os-card os-loading" role="status" aria-live="polite"><div><span class="os-spinner"></span><p>正在读取资源清单、质量状态与协作角色……</p></div></section>

    <template v-else>
      <section class="workshop-telemetry" aria-label="资源工坊概览">
        <span><PackageCheck :size="15" /><i>历史资源</i><strong>{{ overview?.total || 0 }}</strong><small>份</small></span>
        <span><Layers3 :size="15" /><i>资源类型</i><strong>{{ overview?.type_count || 0 }}</strong><small>类</small></span>
        <span><UsersRound :size="15" /><i>协作角色</i><strong>{{ overview?.agents.length || 0 }}</strong><small>个</small></span>
        <span class="quality-telemetry"><BadgeCheck :size="15" /><i>质量状态</i><strong>{{ qualityLabel }}</strong><small v-if="overview?.quality.risk_score">风险 {{ overview.quality.risk_score }}</small></span>
      </section>

      <section class="workshop-shell">
        <aside class="task-rail os-card" aria-label="资源生成任务栏">
          <form class="resource-config" aria-labelledby="resource-config-title" @submit.prevent="generateResources">
            <header class="section-heading"><span class="section-index">01</span><div><span class="os-eyebrow">RESOURCE BRIEF</span><h2 id="resource-config-title">生成任务</h2><p>配置会原样提交给后端资源智能体。</p></div></header>

            <div class="config-grid"><label><span>课程 / 主题 <em>必填</em></span><input v-model="course" required autocomplete="off" placeholder="例如：软件需求分析与建模" /></label><label><span>章节 / 场景 <em>必填</em></span><input v-model="chapter" required autocomplete="off" placeholder="例如：用例建模" /></label></div>
            <label class="field-stack"><span>当前薄弱点 <small>{{ splitWeakPoints().length }} 项</small></span><textarea v-model="weakPoints" rows="3" placeholder="多个薄弱点可用逗号分隔"></textarea></label>
            <label class="field-stack"><span>内容组织偏好</span><input v-model="learningStyle" autocomplete="off" placeholder="例如：图解 + 案例驱动" /></label>

            <fieldset class="resource-type-fieldset"><legend>选择交付类型 <small>至少 1 项</small></legend><div class="resource-type-grid"><button v-for="item in resourceTypes" :key="item.value" class="resource-type-option" :class="{ 'is-selected': selectedTypes.includes(item.value) }" type="button" :aria-pressed="selectedTypes.includes(item.value)" @click="toggleResourceType(item.value)"><span class="type-code">{{ item.short }}</span><span><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span><Check v-if="selectedTypes.includes(item.value)" :size="13" aria-hidden="true" /></button></div></fieldset>

            <div class="generation-summary"><span><Sparkles :size="15" /><i><strong>{{ selectedTypes.length }} 类资源待生成</strong><small>{{ selectedTypeLabels.join(' · ') || '尚未选择资源类型' }}</small></i></span><button class="os-button os-button-primary generate-button" type="submit" :disabled="generating || !selectedTypes.length || (!course.trim() && !chapter.trim() && !weakPoints.trim())"><LoaderCircle v-if="generating" class="spin" :size="15" /><WandSparkles v-else :size="15" />{{ generating ? '后端协同生成中' : '生成资源包' }}</button></div>
            <div v-if="generating" class="generation-live" role="status" aria-live="polite"><span class="indeterminate-track"><i></i></span><span><strong>等待后端返回真实结果</strong><small>当前接口未提供逐阶段百分比。</small></span></div>
          </form>

          <section class="agent-console" aria-labelledby="agent-console-title">
            <header><span><UsersRound :size="14" /> AGENT TRACE</span><span class="agent-console-status"><i :class="{ 'is-live': generating }"></i>{{ generating ? '执行中' : selectedResource?.agent_trace?.length ? '真实轨迹' : '角色职责' }}</span></header>
            <h3 id="agent-console-title">协作与质量审计</h3>
            <div class="agent-list"><article v-for="(item, index) in traceItems" :key="item.key"><span class="agent-index">{{ String(index + 1).padStart(2, '0') }}</span><span><strong>{{ item.label }}</strong><small>{{ item.role }}</small></span><span class="agent-state" :class="{ 'is-verified': item.verified }">{{ item.verified ? item.status : '职责' }}</span></article><div v-if="!traceItems.length" class="agent-empty">暂无协作角色数据</div></div>
            <footer v-if="overview?.quality"><BadgeCheck :size="15" /><span><strong>{{ overview.quality.summary }}</strong><small>当前风险分：{{ overview.quality.risk_score ?? 0 }}</small></span></footer>
          </section>
        </aside>

        <section class="resource-delivery os-card" aria-labelledby="resource-delivery-title">
          <header class="delivery-header">
            <div class="section-heading"><span class="section-index">02</span><div><span class="os-eyebrow">DELIVERY WORKSPACE</span><h2 id="resource-delivery-title">资源队列与实时预览</h2><p>{{ generatedResources.length ? '本轮生成结果' : '最近生成的历史资源' }} · {{ visibleResources.length }} 份</p></div></div>
            <div class="delivery-actions"><button class="os-button" type="button" :disabled="!visibleResources.length" @click="toggleSelectAll">{{ selectedCount === visibleResources.length && visibleResources.length ? '取消全选' : '全选资源' }}</button><button class="os-button os-button-primary" type="button" :disabled="!selectedCount || exporting" @click="exportSelected"><LoaderCircle v-if="exporting" class="spin" :size="15" /><FileArchive v-else :size="15" />{{ exporting ? '打包中' : `导出 ${selectedCount || ''} 项` }}</button></div>
          </header>

          <a v-if="exportUrl" class="download-ready" :href="exportUrl" target="_blank" rel="noreferrer"><Download :size="16" /><span><strong>资源包已就绪</strong><small>点击下载 ZIP 文件</small></span><ArrowRight :size="15" /></a>

          <div v-if="visibleResources.length" class="delivery-grid">
            <aside class="resource-queue">
              <header><span><Boxes :size="14" />资源队列</span><small>{{ selectedCount }} / {{ visibleResources.length }} 已选</small></header>
              <div class="resource-list" role="list" aria-label="可用资源">
                <article v-for="resource in visibleResources" :key="resource.id" :class="{ 'is-active': selectedResource?.id === resource.id }" role="listitem">
                  <label class="resource-check"><input type="checkbox" :checked="selectedResourceIds.includes(resource.id)" :aria-label="`将${resource.title}加入导出`" @change="toggleResourceSelection(resource.id)" /></label>
                  <button class="resource-open" type="button" @click="openResource(resource)"><span class="resource-symbol"><FileText :size="15" /></span><span><small>{{ labelForType(resource.type) }}</small><strong>{{ resource.title }}</strong><em>{{ resource.course || course }}<template v-if="resource.chapter"> · {{ resource.chapter }}</template></em></span><Eye :size="14" aria-hidden="true" /></button>
                  <time :datetime="resource.created_at"><Clock3 :size="11" />{{ formatDate(resource.created_at) }}</time>
                </article>
              </div>
            </aside>

            <article class="resource-preview" aria-live="polite">
              <header><div><span class="os-eyebrow">03 / 在线预览</span><h3>{{ selectedResource?.title || '选择资源查看内容' }}</h3><small v-if="selectedResource">{{ labelForType(selectedResource.type) }} · {{ selectedResource.course || course }}</small></div><a v-if="selectedResource?.preview_url" class="os-button" :href="selectedResource.preview_url" target="_blank" rel="noreferrer"><Download :size="14" />打开原文件</a></header>
              <div v-if="previewLoading" class="preview-state" role="status"><span class="os-spinner"></span><p>正在读取资源正文……</p></div>
              <div v-else-if="previewError" class="preview-state is-error" role="alert"><CircleAlert :size="22" /><p>{{ previewError }}</p><button v-if="selectedResource" class="os-button" type="button" @click="openResource(selectedResource)">重新加载</button></div>
              <div v-else-if="readablePreviewContent" class="preview-scroll"><MarkdownContent :content="readablePreviewContent" /></div>
              <div v-else class="preview-state"><FileText :size="26" /><p>{{ selectedResource ? '该历史资源未提供内嵌正文，可通过原文件查看。' : '从左侧选择一份资源进行预览。' }}</p></div>
            </article>
          </div>
          <div v-else class="cp-empty-state"><span><PackageCheck :size="25" /></span><h3>还没有可交付资源</h3><p>完成左侧任务配置并提交后，真实生成结果会在这里出现。</p></div>
        </section>
      </section>

      <section class="workshop-next os-card-soft"><span><Target :size="18" /></span><div><strong>下一步：用练习验证资源是否真正有效</strong><small>正确率与错因会回流画像和路径，形成持续改进闭环。</small></div><RouterLink class="os-button os-button-primary" to="/exercise">进入做题诊断 <ArrowRight :size="15" /></RouterLink></section>
    </template>
    </template>
  </div>
</template>

<style scoped>
.shot-progress-empty { margin: 34px 0 0; padding: 24px 12px; color: #71849b; border: 1px dashed #d8e6f2; border-radius: 10px; background: #f8fbff; font-size: 11px; text-align: center; }
.workshop-command-page { display: grid; gap: 12px; padding-top: 18px; }.spin { animation: workshop-spin .8s linear infinite; }
.workshop-topbar { display: flex; align-items: center; justify-content: space-between; gap: 24px; min-height: 58px; padding-bottom: 13px; border-bottom: 1px solid var(--cp-line); }.workshop-heading { display: flex; align-items: center; gap: 22px; min-width: 0; }.workshop-heading > div { display: flex; align-items: baseline; gap: 14px; min-width: 0; }.workshop-heading h1 { margin: 0; font-size: clamp(24px,2.2vw,32px); line-height: 1.1; letter-spacing: -.045em; }.workshop-heading p { overflow: hidden; margin: 0; color: var(--cp-muted); font-size: 11px; white-space: nowrap; text-overflow: ellipsis; }.workshop-topbar .os-page-actions { display: flex; flex: 0 0 auto; gap: 8px; }.workshop-topbar .os-button { min-height: 38px; }
.workshop-flowbar { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); overflow: hidden; border: 1px solid var(--cp-line); border-radius: 13px; background: rgba(255,255,255,.9); box-shadow: var(--cp-shadow-soft); }.flow-step { position: relative; display: grid; grid-template-columns: 27px minmax(0,1fr); align-items: center; gap: 9px; min-height: 52px; padding: 7px 14px; }.flow-step:not(:last-child)::after { position: absolute; top: 11px; right: 0; width: 1px; height: 30px; background: var(--cp-line); content: ''; }.flow-step > b { display: grid; place-items: center; width: 27px; height: 27px; color: var(--cp-muted); border-radius: 8px; background: #edf2f8; font-size: 9px; }.flow-step > i { display: grid; gap: 2px; min-width: 0; font-style: normal; }.flow-step strong { font-size: 10px; }.flow-step small { overflow: hidden; color: var(--cp-muted); font-size: 9px; white-space: nowrap; text-overflow: ellipsis; }.flow-step.is-current { color: #fff; background: linear-gradient(120deg,#1769ff,#168ee9); }.flow-step.is-current > b { color: var(--cp-blue); background: #fff; }.flow-step.is-current small { color: #d9ecff; }.flow-step.is-current::after { display: none; }.flow-delivery { color: #f4f9ff; background: #102b4e; }.flow-delivery > b { color: #85cfff; background: rgba(255,255,255,.1); }.flow-delivery small { color: #9db5d0; }
.workshop-alert { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; padding: 10px 13px; }.workshop-alert > span { display: grid; gap: 2px; }.workshop-alert strong { font-size: 11px; }.workshop-alert small { color: var(--os-ink-soft); font-size: 9px; }.workshop-alert .os-button { min-height: 33px; }.workshop-notice { display: flex; align-items: center; gap: 8px; padding: 9px 13px; color: #0f579f; border: 1px solid rgba(23,105,255,.18); border-radius: 10px; background: #edf5ff; font-size: 10px; font-weight: 720; }
.workshop-telemetry { display: grid; grid-template-columns: repeat(3,minmax(130px,.55fr)) minmax(240px,1.2fr); overflow: hidden; border: 1px solid var(--cp-line); border-radius: 11px; background: rgba(255,255,255,.8); }.workshop-telemetry > span { display: flex; align-items: center; gap: 7px; min-width: 0; min-height: 38px; padding: 0 13px; color: var(--cp-blue); }.workshop-telemetry > span + span { border-left: 1px solid var(--cp-line); }.workshop-telemetry i { color: var(--cp-muted); font-size: 9px; font-style: normal; }.workshop-telemetry strong { color: var(--cp-text); font-size: 12px; }.workshop-telemetry small { color: var(--cp-muted); font-size: 8px; }.quality-telemetry strong { overflow: hidden; font-size: 10px; white-space: nowrap; text-overflow: ellipsis; }
.workshop-shell { display: grid; grid-template-columns: minmax(330px,.68fr) minmax(0,1.8fr); align-items: start; gap: 12px; }.task-rail { position: sticky; top: 74px; overflow: hidden; padding: 0; }.resource-config { display: grid; gap: 11px; padding: 15px; }.section-heading { display: flex; align-items: center; gap: 9px; min-width: 0; }.section-heading > div { display: grid; gap: 2px; min-width: 0; }.section-heading h2 { margin: 0; font-size: 16px; letter-spacing: -.02em; }.section-heading p { margin: 0; color: var(--cp-muted); font-size: 9px; }.section-index { display: grid; place-items: center; flex: 0 0 29px; width: 29px; height: 29px; color: var(--cp-blue); border: 1px solid rgba(23,105,255,.17); border-radius: 8px; background: var(--cp-blue-soft); font-size: 9px; font-weight: 850; }
.config-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }.config-grid label,.field-stack { display: grid; gap: 5px; color: var(--cp-text); font-size: 9px; font-weight: 760; }.config-grid em { color: var(--cp-blue); font-style: normal; }.field-stack > span { display: flex; align-items: center; justify-content: space-between; }.field-stack > span small { color: var(--cp-blue); font-size: 8px; }.resource-config :is(input,textarea) { width: 100%; border: 1px solid var(--cp-line-strong); border-radius: 9px; background: #fbfdff; color: var(--cp-text); font: inherit; font-size: 10px; box-sizing: border-box; }.resource-config input { height: 36px; padding: 0 10px; }.resource-config textarea { min-height: 65px; padding: 8px 10px; resize: vertical; line-height: 1.5; }.resource-config :is(input,textarea):focus { border-color: var(--cp-blue); outline: 3px solid rgba(23,105,255,.08); }.resource-type-fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }.resource-type-fieldset legend { width: 100%; margin-bottom: 6px; font-size: 9px; font-weight: 760; }.resource-type-fieldset legend small { margin-left: 4px; color: var(--cp-muted); font-size: 8px; }.resource-type-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }.resource-type-option { display: grid; grid-template-columns: 30px minmax(0,1fr) auto; align-items: center; gap: 7px; min-height: 44px; padding: 5px 7px; color: var(--cp-text); border: 1px solid var(--cp-line); border-radius: 9px; background: #f9fbff; text-align: left; cursor: pointer; }.resource-type-option:hover { border-color: rgba(23,105,255,.35); }.resource-type-option.is-selected { color: var(--cp-blue-ink); border-color: rgba(23,105,255,.38); background: var(--cp-blue-soft); box-shadow: inset 2px 0 0 var(--cp-blue); }.type-code { display: grid; place-items: center; width: 28px; height: 28px; color: var(--cp-blue); border-radius: 7px; background: #fff; font-size: 7px; font-weight: 850; }.resource-type-option > span:nth-child(2) { display: grid; gap: 1px; min-width: 0; }.resource-type-option strong { font-size: 9px; }.resource-type-option small { overflow: hidden; color: var(--cp-muted); font-size: 7px; white-space: nowrap; text-overflow: ellipsis; }.generation-summary { display: grid; gap: 9px; padding-top: 10px; border-top: 1px solid var(--cp-line); }.generation-summary > span { display: flex; align-items: center; gap: 7px; color: var(--cp-blue); }.generation-summary > span i { display: grid; gap: 2px; min-width: 0; font-style: normal; }.generation-summary strong { color: var(--cp-text); font-size: 9px; }.generation-summary small { overflow: hidden; color: var(--cp-muted); font-size: 8px; white-space: nowrap; text-overflow: ellipsis; }.generate-button { width: 100%; min-height: 38px; }.generation-live { display: grid; gap: 7px; padding: 9px; color: #0f579f; border-radius: 9px; background: #eef6ff; }.generation-live > span:last-child { display: flex; justify-content: space-between; gap: 6px; }.generation-live strong,.generation-live small { font-size: 8px; }.generation-live small { color: #607b9c; }.indeterminate-track { position: relative; height: 4px; overflow: hidden; border-radius: 99px; background: #d7e6f8; }.indeterminate-track i { position: absolute; width: 38%; height: 100%; border-radius: inherit; background: linear-gradient(90deg,var(--cp-blue),var(--cp-cyan)); animation: workshop-progress 1.4s ease-in-out infinite; }
.agent-console { display: grid; gap: 7px; padding: 12px 15px 14px; color: #eaf4ff; background: linear-gradient(145deg,#102b4e,#0d223e); }.agent-console > header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }.agent-console > header > span:first-child { display: flex; align-items: center; gap: 6px; color: #7dc8ff; font-size: 8px; font-weight: 800; letter-spacing: .11em; }.agent-console-status { display: flex; align-items: center; gap: 5px; color: #94adc7; font-size: 8px; }.agent-console-status i { width: 5px; height: 5px; border-radius: 50%; background: #6c839e; }.agent-console-status i.is-live { background: #45d4ff; box-shadow: 0 0 0 3px rgba(69,212,255,.12); }.agent-console h3 { margin: 0; font-size: 12px; }.agent-list { display: grid; max-height: 145px; overflow-y: auto; scrollbar-width: thin; }.agent-list article { display: grid; grid-template-columns: 25px minmax(0,1fr) auto; align-items: center; gap: 7px; padding: 6px 0; border-top: 1px solid rgba(137,177,219,.15); }.agent-index { display: grid; place-items: center; width: 23px; height: 23px; color: #80cfff; border: 1px solid rgba(102,191,255,.2); border-radius: 6px; background: rgba(24,83,132,.32); font-size: 8px; font-weight: 800; }.agent-list article > span:nth-child(2) { display: grid; gap: 1px; min-width: 0; }.agent-list strong { font-size: 8px; }.agent-list small { overflow: hidden; color: #8fa8c3; font-size: 7px; white-space: nowrap; text-overflow: ellipsis; }.agent-state { color: #8da6bf; font-size: 7px; text-transform: uppercase; }.agent-state.is-verified { color: #58d5ff; }.agent-empty { padding: 18px 0; color: #8fa8c3; text-align: center; font-size: 8px; }.agent-console > footer { display: flex; align-items: flex-start; gap: 7px; padding: 8px; color: #57cbff; border: 1px solid rgba(72,175,235,.17); border-radius: 8px; background: rgba(17,71,116,.32); }.agent-console > footer span { display: grid; gap: 2px; }.agent-console > footer strong { color: #dceeff; font-size: 8px; }.agent-console > footer small { color: #8fa8c3; font-size: 7px; }
.resource-delivery { min-width: 0; overflow: hidden; padding: 0; }.delivery-header { display: flex; align-items: center; justify-content: space-between; gap: 14px; min-height: 64px; padding: 10px 13px; border-bottom: 1px solid var(--cp-line); }.delivery-actions { display: flex; gap: 7px; }.delivery-actions .os-button { min-height: 34px; }.download-ready { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 8px; margin: 9px 11px 0; padding: 8px 10px; color: #0d559c; border: 1px solid rgba(23,105,255,.2); border-radius: 9px; background: #edf5ff; text-decoration: none; }.download-ready > span { display: grid; gap: 1px; }.download-ready strong { font-size: 9px; }.download-ready small { color: var(--cp-muted); font-size: 8px; }.delivery-grid { display: grid; grid-template-columns: minmax(235px,.62fr) minmax(0,1.5fr); min-height: 602px; }.resource-queue { min-width: 0; border-right: 1px solid var(--cp-line); background: #f8fbff; }.resource-queue > header { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 39px; padding: 0 10px; border-bottom: 1px solid var(--cp-line); }.resource-queue > header > span { display: flex; align-items: center; gap: 6px; color: var(--cp-text); font-size: 9px; font-weight: 800; }.resource-queue > header small { color: var(--cp-muted); font-size: 8px; }.resource-list { display: grid; align-content: start; max-height: 562px; overflow-y: auto; scrollbar-width: thin; }.resource-list article { position: relative; display: grid; grid-template-columns: 28px minmax(0,1fr); align-items: center; min-width: 0; border-bottom: 1px solid var(--cp-line); background: rgba(255,255,255,.78); }.resource-list article:hover { background: #f2f7ff; }.resource-list article.is-active { z-index: 1; background: var(--cp-blue-soft); box-shadow: inset 3px 0 0 var(--cp-blue); }.resource-check { display: grid; place-items: center; align-self: stretch; border-right: 1px solid var(--cp-line); cursor: pointer; }.resource-check input { width: 13px; height: 13px; accent-color: var(--cp-blue); }.resource-open { display: grid; grid-template-columns: 30px minmax(0,1fr) auto; align-items: center; gap: 7px; min-width: 0; padding: 9px 8px; color: var(--cp-text); border: 0; background: transparent; text-align: left; cursor: pointer; }.resource-symbol { display: grid; place-items: center; width: 28px; height: 28px; color: var(--cp-blue); border-radius: 7px; background: #fff; }.resource-open > span:nth-child(2) { display: grid; gap: 2px; min-width: 0; }.resource-open small { color: var(--cp-blue); font-size: 7px; font-weight: 750; }.resource-open strong,.resource-open em { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }.resource-open strong { font-size: 9px; }.resource-open em { color: var(--cp-muted); font-size: 7px; font-style: normal; }.resource-list article > time { grid-column: 2; display: flex; align-items: center; gap: 4px; margin: -5px 8px 7px 38px; color: var(--cp-muted); font-size: 7px; }
.resource-preview { display: grid; grid-template-rows: auto minmax(0,1fr); min-width: 0; overflow: hidden; background: #fff; }.resource-preview > header { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 54px; padding: 9px 13px; border-bottom: 1px solid var(--cp-line); background: #f9fbff; }.resource-preview header > div { display: grid; gap: 2px; min-width: 0; }.resource-preview h3 { overflow: hidden; margin: 0; font-size: 13px; white-space: nowrap; text-overflow: ellipsis; }.resource-preview header small { overflow: hidden; color: var(--cp-muted); font-size: 8px; white-space: nowrap; text-overflow: ellipsis; }.resource-preview > header .os-button { min-height: 32px; }.preview-scroll { height: 547px; overflow: auto; padding: 18px 22px; scrollbar-width: thin; }.preview-state { display: grid; place-items: center; align-content: center; gap: 9px; min-height: 460px; padding: 25px; color: var(--cp-muted); text-align: center; }.preview-state p { max-width: 380px; margin: 0; font-size: 10px; line-height: 1.6; }.preview-state.is-error { color: #b34343; }
.resource-delivery > .cp-empty-state { min-height: 560px; }.workshop-next { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; padding: 10px 13px; }.workshop-next > span { display: grid; place-items: center; width: 34px; height: 34px; color: var(--cp-blue); border-radius: 9px; background: var(--cp-blue-soft); }.workshop-next > div { display: grid; gap: 2px; }.workshop-next strong { font-size: 9px; }.workshop-next small { color: var(--cp-muted); font-size: 8px; }.workshop-next .os-button { min-height: 34px; }
@keyframes workshop-spin { to { transform: rotate(360deg); } } @keyframes workshop-progress { 0% { left: -42%; } 55% { left: 44%; } 100% { left: 105%; } }
@media (max-width: 1180px) { .workshop-heading { align-items: flex-start; flex-direction: column; gap: 3px; }.workshop-shell { grid-template-columns: 1fr; }.task-rail { position: static; display: grid; grid-template-columns: minmax(0,1.65fr) minmax(280px,.7fr); }.agent-console { min-height: 100%; }.resource-type-grid { grid-template-columns: repeat(3,minmax(0,1fr)); } }
@media (max-width: 900px) { .workshop-topbar { align-items: flex-start; }.workshop-heading > div { align-items: flex-start; flex-direction: column; gap: 3px; }.workshop-flowbar { grid-template-columns: 1fr 1fr; }.flow-step:nth-child(2)::after { display: none; }.workshop-telemetry { grid-template-columns: 1fr 1fr; }.workshop-telemetry > span:nth-child(3) { border-left: 0; border-top: 1px solid var(--cp-line); }.workshop-telemetry > span:nth-child(4) { border-top: 1px solid var(--cp-line); }.task-rail { grid-template-columns: 1fr; }.resource-type-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }.delivery-grid { grid-template-columns: 1fr; }.resource-queue { border-right: 0; border-bottom: 1px solid var(--cp-line); }.resource-list { grid-template-columns: 1fr 1fr; max-height: 300px; }.resource-list article:nth-child(odd) { border-right: 1px solid var(--cp-line); }.preview-scroll { height: 480px; } }
@media (max-width: 680px) { .workshop-command-page { padding-top: 12px; }.workshop-topbar { flex-direction: column; }.workshop-topbar .os-page-actions { width: 100%; }.workshop-topbar .os-page-actions .os-button { flex: 1; }.workshop-flowbar { grid-template-columns: 1fr; }.flow-step::after { display: none; }.workshop-alert { grid-template-columns: auto 1fr; }.workshop-alert .os-button { grid-column: span 2; }.workshop-telemetry { grid-template-columns: 1fr 1fr; }.delivery-header { align-items: stretch; flex-direction: column; }.delivery-actions { width: 100%; }.delivery-actions .os-button { flex: 1; }.resource-list { grid-template-columns: 1fr; }.resource-list article:nth-child(odd) { border-right: 0; }.resource-preview > header { align-items: stretch; flex-direction: column; }.workshop-next { grid-template-columns: auto 1fr; }.workshop-next .os-button { grid-column: span 2; } }
@media (max-width: 440px) { .workshop-heading > .os-eyebrow { display: none; }.config-grid,.resource-type-grid,.workshop-telemetry { grid-template-columns: 1fr; }.workshop-telemetry > span + span { border-top: 1px solid var(--cp-line); border-left: 0; }.resource-config { padding: 12px; }.delivery-actions { flex-direction: column; }.workshop-next { grid-template-columns: 1fr; }.workshop-next > span { display: none; }.workshop-next .os-button { grid-column: auto; } }
@media (max-width: 900px) {
  .workshop-topbar { flex-direction: column; }
  .workshop-topbar .os-page-actions { width: 100%; min-width: 0; }
}
</style>
