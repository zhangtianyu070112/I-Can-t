<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Bot,
  Boxes,
  BookOpenCheck,
  ChartNoAxesCombined,
  Check,
  ChevronDown,
  CircleAlert,
  CirclePlay,
  Clock3,
  Compass,
  Download,
  FileText,
  Flag,
  Gauge,
  GitBranch,
  Heart,
  Layers3,
  LayoutGrid,
  Lightbulb,
  ListChecks,
  LoaderCircle,
  LockKeyhole,
  Map,
  RefreshCw,
  Route,
  ShieldCheck,
  Sparkles,
  Target,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  UserRound,
} from 'lucide-vue-next'
import LearningLoopContext from '@/components/LearningLoopContext.vue'
import {
  getPathOverview,
  getEvaluationOverview,
  getProfileOverview,
  getPushFeed,
  planLearningPath,
  removePushedResource,
  sendResourceFeedback,
  type PathOverview,
  type ProfileOverview,
  type EvaluationOverview,
} from '@/api/learningApi'
import { useStudent } from '@/composables/useStudent'
import { renderMarkdown } from '@/utils/markdownRenderer'
import { localizeProfileOverview } from '@/utils/profileLocalization'

type PathMeta = {
  strategy: string[]
  dynamicRules: string[]
  rationale: string
}

const { studentId, goals } = useStudent()
const router = useRouter()
const overview = ref<PathOverview | null>(null)
const profileOverview = ref<ProfileOverview | null>(null)
const evaluationOverview = ref<EvaluationOverview | null>(null)
const recommendations = ref<any[]>([])
const pathLoading = ref(true)
const feedLoading = ref(true)
const pathRefreshing = ref(false)
const planning = ref(false)
const feedbackPending = ref('')
const removingResourceId = ref('')
const pathError = ref('')
const feedError = ref('')
const actionError = ref('')
const notice = ref('')
const selectedNodeId = ref('')
const selectedResourceId = ref('')
const showRules = ref(true)
const showAllRecommendations = ref(false)
const goalInput = ref(goals.value || '')
const planMeta = ref<PathMeta>({ strategy: [], dynamicRules: [], rationale: '' })
const recommendationPreviewLimit = 6
const showRecommendationReason = ref(true)
const feedLoadedSuccessfully = ref(false)
let pathSyncInFlight = false
let pathRefreshTimer: number | null = null

const pathResourceLabels: Record<string, string> = {
  lecture_doc: '讲解文档',
  mindmap: '思维导图',
  question_bank: '练习题库',
  reading: '拓展阅读',
  practice_case: '实操案例',
  video_script: '视频脚本',
  quality_check: '质量审查',
}

function localizePathText(value: unknown) {
  return String(value || '')
    .replace(/\blecture_doc\b/gi, '讲解文档')
    .replace(/\bmindmap\b/gi, '思维导图')
    .replace(/\bquestion_bank\b/gi, '练习题库')
    .replace(/\bpractice_case\b/gi, '实操案例')
    .replace(/\bvideo_script\b/gi, '视频脚本')
    .replace(/\bquality_check\b/gi, '质量审查')
    .replace(/\bassessment\b/gi, '阶段测试')
    .replace(/\bstep\b/gi, '阶段')
}

const selectedNode = computed(() => overview.value?.nodes.find((item: any) => nodeId(item) === selectedNodeId.value) || overview.value?.nodes[0] || null)
const selectedResource = computed(() => recommendations.value.find((item) => resourceId(item) === selectedResourceId.value) || recommendations.value[0] || null)
const completedCount = computed(() => overview.value?.nodes.filter((item: any) => ['completed', 'done'].includes(String(item.status))).length || 0)
const pathProgress = computed(() => overview.value?.nodes.length ? Math.round((completedCount.value / overview.value.nodes.length) * 100) : 0)
const currentPathStage = computed(() => overview.value?.current_stage || overview.value?.nodes.find((item: any) => ['current', 'active', 'warning'].includes(String(item.status))) || null)
const currentPathMastery = computed(() => {
  const selected = selectedNode.value || currentPathStage.value
  return Math.max(0, Math.min(100, Math.round(Number(selected?.mastery) || 0)))
})
const currentStageIndex = computed(() => {
  if (!overview.value?.nodes.length || !selectedNode.value) return 0
  return Math.max(0, overview.value.nodes.findIndex((item: any) => nodeId(item) === nodeId(selectedNode.value)))
})
const visibleRules = computed(() => (
  planMeta.value.dynamicRules.length ? planMeta.value.dynamicRules : overview.value?.rules || []
).map(localizePathText))
const displayedRecommendations = computed(() => showAllRecommendations.value ? recommendations.value : recommendations.value.slice(0, recommendationPreviewLimit))
const displayStages = computed(() => (overview.value?.nodes || []).map((node: any, index) => ({
  ...node,
  id: nodeId(node),
  mastery: Number.isFinite(Number(node.mastery)) ? `${Number(node.mastery)}%` : '--',
  step: node.step || index + 1,
})))
const learnerDimensions = computed(() => Object.fromEntries((profileOverview.value?.dimensions || []).map((item) => [item.key, item.value])))
const pathRadarDimensions = computed(() => {
  const source = evaluationOverview.value?.dimensions || []
  const defaults = ['知识掌握', '迁移应用', '学习投入', '资源匹配', '策略稳定']
  return defaults.map((fallback, index) => ({
    label: source[index]?.label || fallback,
    value: Math.max(0, Math.min(100, Number(source[index]?.value) || 0)),
  }))
})

function pathRadarPoint(index: number, value = 100) {
  const angle = -Math.PI / 2 + index * Math.PI * 2 / 5
  const radius = 54 * Math.max(0, Math.min(100, value)) / 100
  return {
    x: Number((119 + Math.cos(angle) * radius).toFixed(2)),
    y: Number((78 + Math.sin(angle) * radius).toFixed(2)),
  }
}

function pathRadarPolygon(values: number[]) {
  return values.map((value, index) => {
    const point = pathRadarPoint(index, value)
    return `${point.x},${point.y}`
  }).join(' ')
}

const pathRadarAxes = Array.from({ length: 5 }, (_, index) => pathRadarPoint(index))
const pathRadarValues = computed(() => pathRadarDimensions.value.map((item) => item.value))

async function loadPath(options: { background?: boolean; silent?: boolean } = {}) {
  if (pathSyncInFlight) return
  pathSyncInFlight = true
  const background = Boolean(options.background && overview.value)
  const silent = Boolean(options.silent)
  if (!silent) {
    if (background) pathRefreshing.value = true
    else pathLoading.value = true
    pathError.value = ''
  }
  try {
    const data = await getPathOverview(studentId.value)
    const normalizedNodes = (data.nodes || []).map(normalizeNode)
    const previousNodeId = selectedNodeId.value
    overview.value = { ...data, nodes: normalizedNodes }
    planMeta.value = {
      strategy: Array.isArray(data.strategy) ? data.strategy.map(localizePathText) : [],
      dynamicRules: Array.isArray(data.rules) ? data.rules.map(localizePathText) : [],
      rationale: localizePathText(data.rationale),
    }
    selectedNodeId.value = normalizedNodes.some((node: any) => nodeId(node) === previousNodeId)
      ? previousNodeId
      : nodeId(data.current_stage || normalizedNodes[0])
  } catch (reason: any) {
    if (!silent) pathError.value = reason?.message || '学习路径加载失败'
  } finally {
    pathSyncInFlight = false
    if (!silent) {
      pathLoading.value = false
      pathRefreshing.value = false
    }
  }
}

function syncVisiblePath() {
  if (document.visibilityState === 'visible') void loadPath({ background: true, silent: true })
}

async function loadFeed(options: { preserveSelection?: boolean } = {}) {
  feedLoading.value = true
  feedError.value = ''
  const previousId = options.preserveSelection ? selectedResourceId.value : ''
  try {
    const feed = await getPushFeed(studentId.value)
    feedLoadedSuccessfully.value = true
    recommendations.value = feed
    selectedResourceId.value = recommendations.value.some((item) => resourceId(item) === previousId)
      ? previousId
      : resourceId(recommendations.value[0])
  } catch (reason: any) {
    feedError.value = reason?.message || '动态推荐加载失败'
    if (!recommendations.value.length && overview.value?.recommendations?.length) {
      recommendations.value = overview.value.recommendations
      selectedResourceId.value = resourceId(recommendations.value[0])
    }
  } finally {
    feedLoading.value = false
  }
}

async function refreshAll() {
  await Promise.allSettled([loadPath({ background: true }), loadFeed({ preserveSelection: true }), loadLearnerEvidence()])
}

async function loadLearnerEvidence() {
  const [profile, evaluation] = await Promise.all([
    getProfileOverview(studentId.value),
    getEvaluationOverview(studentId.value),
  ])
  profileOverview.value = localizeProfileOverview(profile)
  evaluationOverview.value = evaluation
}

async function generatePath() {
  const goal = goalInput.value.trim()
  if (planning.value) return
  if (!goal) {
    actionError.value = '请先填写本轮学习目标。'
    return
  }

  planning.value = true
  actionError.value = ''
  notice.value = ''
  goals.value = goal
  try {
    const data = await planLearningPath(studentId.value, goal)
    const path = data?.path || data?.plan || data || {}
    const rawNodes = path?.nodes || path?.steps || []
    const normalizedNodes = Array.isArray(rawNodes) ? rawNodes.map(normalizeNode) : []
    const currentStage = normalizedNodes.find((item: any) => ['current', 'active'].includes(String(item.status))) || normalizedNodes[0] || {}
    const previous = overview.value

    overview.value = {
      has_plan: true,
      title: path?.title || data?.title || previous?.title || '个性化学习路径',
      updated_at: new Date().toISOString(),
      stage_count: normalizedNodes.length,
      current_stage: currentStage,
      nodes: normalizedNodes,
      recommendations: previous?.recommendations || [],
      rules: Array.isArray(path?.dynamic_rules) && path.dynamic_rules.length ? path.dynamic_rules : previous?.rules || [],
    }
    planMeta.value = {
      strategy: Array.isArray(path?.strategy) ? path.strategy.map(localizePathText) : [],
      dynamicRules: Array.isArray(path?.dynamic_rules) ? path.dynamic_rules.map(localizePathText) : [],
      rationale: localizePathText(path?.rationale),
    }
    selectedNodeId.value = nodeId(currentStage)
    if (Array.isArray(data?.recommendations) && data.recommendations.length) {
      recommendations.value = data.recommendations
      selectedResourceId.value = resourceId(recommendations.value[0])
    } else {
      void loadFeed({ preserveSelection: true })
    }
    notice.value = normalizedNodes.length
      ? `后端已生成 ${normalizedNodes.length} 个路径阶段，学习目标已同步到本地学习身份。`
      : '后端已完成规划，但没有返回可展示的阶段。请调整目标后重试。'
  } catch (reason: any) {
    actionError.value = reason?.message || '路径生成失败'
  } finally {
    planning.value = false
  }
}

function normalizeNode(raw: any, index = 0) {
  return {
    ...raw,
    id: raw?.id || `stage-${raw?.step || raw?.order || index + 1}`,
    step: raw?.step || raw?.order || index + 1,
    title: raw?.title || raw?.objective || `学习阶段 ${index + 1}`,
    goal: raw?.goal || raw?.objective || '',
    status: raw?.status || (index === 0 ? 'current' : 'locked'),
    resources: Array.isArray(raw?.resources) ? raw.resources : [],
    tasks: Array.isArray(raw?.tasks) ? raw.tasks : [],
    checkpoint: raw?.checkpoint || raw?.assessment || '',
  }
}

async function feedback(action: 'like' | 'dislike') {
  if (!selectedResource.value || feedbackPending.value) return
  const id = resourceId(selectedResource.value)
  if (!id) {
    actionError.value = '该推荐缺少资源标识，暂时无法提交反馈。'
    return
  }
  feedbackPending.value = action
  actionError.value = ''
  notice.value = ''
  try {
    await sendResourceFeedback(studentId.value, id, action)
    notice.value = action === 'like'
      ? '正向反馈已写入，推荐流已按最新权重刷新。'
      : '负向反馈已写入，系统会降低同类资源权重并判断是否需要策略进化。'
    await loadFeed({ preserveSelection: true })
  } catch (reason: any) {
    actionError.value = reason?.message || '反馈提交失败'
  } finally {
    feedbackPending.value = ''
  }
}

function nodeId(item: any) { return String(item?.id || item?.step || item?.order || '') }
function resourceId(item: any) { return String(item?.resource_id || item?.id || item?.resource?.id || '') }
function resourceTitle(item: any) { return item?.title || item?.resource?.title || item?.resource_title || '个性化学习资源' }
function resourceReason(item: any) { return localizePathText(item?.reason || item?.recommend_reason || item?.resource?.summary || '该历史资源来自当前学习路径的资源清单。') }
function resourceType(item: any) {
  const type = String(item?.type || item?.resource?.type || '')
  return item?.type_label || pathResourceLabels[type] || localizePathText(type) || '学习资源'
}
function resourceScore(item: any) {
  const score = Number(item?.recommend_score)
  return Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : null
}
function resourceUrl(item: any) {
  const contentUri = item?.content_uri || item?.resource?.content_uri || ''
  return String(item?.preview_url || item?.download_url || item?.resource?.preview_url || item?.resource?.download_url || (contentUri ? `/${String(contentUri).replace(/^\/+/, '')}` : ''))
}
function resourceTiming(item: any) { return item?.use_timing || item?.timing || '当前路径阶段可用' }
function resourceTags(item: any): string[] {
  const tags = Array.isArray(item?.tags) ? item.tags : Array.isArray(item?.resource?.tags) ? item.resource.tags : []
  return tags.map(localizePathText)
}

async function replaceResource() {
  const currentId = selectedResourceId.value
  await loadFeed({ preserveSelection: false })
  if (recommendations.value.length > 1) {
    const index = recommendations.value.findIndex((item) => resourceId(item) === currentId)
    selectedResourceId.value = resourceId(recommendations.value[(index + 1 + recommendations.value.length) % recommendations.value.length])
  }
  notice.value = recommendations.value.length ? '已根据最新画像与反馈切换到下一条真实推荐。' : '当前没有可替换的推荐资源。'
}

async function removeCurrentResource() {
  const item = selectedResource.value
  const id = resourceId(item)
  if (!item || !id || removingResourceId.value) return
  const title = resourceTitle(item)
  const currentIndex = recommendations.value.findIndex((resource) => resourceId(resource) === id)
  removingResourceId.value = id
  actionError.value = ''
  notice.value = ''
  try {
    await removePushedResource(studentId.value, id)
    recommendations.value = recommendations.value.filter((resource) => resourceId(resource) !== id)
    const nextIndex = Math.min(Math.max(currentIndex, 0), recommendations.value.length - 1)
    selectedResourceId.value = resourceId(recommendations.value[nextIndex])
    notice.value = `已从当前推送中删除“${title}”，资源工坊中的原资源仍然保留。`
  } catch (reason: any) {
    actionError.value = reason?.message || '推送资源删除失败'
  } finally {
    removingResourceId.value = ''
  }
}

async function startResourceReading() {
  if (!selectedResource.value) return
  if (isQuestionResource(selectedResource.value)) {
    const stage = currentPathStage.value
    if (!stage) {
      actionError.value = '当前没有可学习的路径阶段，请先生成学习路径。'
      return
    }
    const stageBanks = Array.isArray(stage.question_bank_ids) ? stage.question_bank_ids.map(String) : []
    const selectedBankId = resourceId(selectedResource.value)
    await router.push({
      path: '/exercise',
      query: {
        stage: nodeId(stage),
        autostart: '1',
        ...(stageBanks.includes(selectedBankId) ? { bank: selectedBankId } : {}),
      },
    })
    return
  }
  const url = resourceUrl(selectedResource.value)
  if (!url) {
    window.open('/workshop', '_blank', 'noopener,noreferrer')
    return
  }
  const readingWindow = window.open('', '_blank')
  if (!readingWindow) {
    actionError.value = '浏览器拦截了新窗口，请允许弹出窗口后重试。'
    return
  }
  readingWindow.document.write('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>资料载入中</title></head><body style="font-family:Microsoft YaHei,sans-serif;padding:40px;color:#334155">正在载入学习资料…</body></html>')
  if (!/\.(md|markdown|txt|json)(?:$|[?#])/i.test(url)) {
    readingWindow.location.href = url
    return
  }
  try {
    const response = await fetch(url)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const text = await response.text()
    const title = resourceTitle(selectedResource.value)
    const safeTitle = title.replace(/[&<>"']/g, (char: string) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char] || char))
    const content = renderMarkdown(text)
    readingWindow.document.open()
    readingWindow.document.write(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${safeTitle}</title><style>body{margin:0;background:#f4f7fb;color:#20344f;font-family:"Microsoft YaHei","PingFang SC",sans-serif;line-height:1.8}.reader{box-sizing:border-box;width:min(920px,calc(100% - 32px));min-height:100vh;margin:0 auto;padding:48px 56px;background:#fff;box-shadow:0 0 40px rgba(31,70,120,.08)}h1,h2,h3,h4{color:#102a4c;line-height:1.35;margin-top:1.5em}h1{margin-top:0;font-size:30px}p,li{font-size:16px}pre{overflow:auto;padding:18px;border-radius:12px;background:#102033;color:#ecf5ff;font:14px/1.65 Consolas,monospace}code{font-family:Consolas,monospace}blockquote{margin:18px 0;padding:10px 18px;border-left:4px solid #2f74ff;background:#f1f6ff}table{width:100%;border-collapse:collapse}th,td{padding:10px;border:1px solid #dce7f5;text-align:left}@media(max-width:640px){.reader{width:100%;padding:28px 20px}}</style></head><body><main class="reader"><h1>${safeTitle}</h1>${content}</main></body></html>`)
    readingWindow.document.close()
  } catch (reason: any) {
    readingWindow.close()
    actionError.value = reason?.message || '学习资料打开失败'
  }
}

function statusLabel(status: string) {
  if (['completed', 'done'].includes(status)) return '已完成'
  if (['current', 'active'].includes(status)) return '进行中'
  if (status === 'warning') return '需补强'
  return '待学习'
}

function stageIcon(status: string) {
  if (['completed', 'done'].includes(status)) return Check
  if (['current', 'active'].includes(status)) return Compass
  if (status === 'warning') return CircleAlert
  return Flag
}

function stageRoute(node: any) {
  const types = Array.isArray(node?.resources) ? node.resources.map(String) : []
  if (types.includes('question_bank') || /诊断|练习|测试/.test(String(node?.title || node?.goal || ''))) return '/exercise'
  if (/评估|复盘/.test(String(node?.title || node?.goal || ''))) return '/evaluate'
  return '/workshop'
}

function isQuestionResource(item: any) {
  const type = String(item?.type || item?.resource?.type || item?.type_label || '').toLowerCase()
  return type === 'question_bank' || /题库|练习|测试|诊断/.test(type)
}

async function startStage(node: any) {
  if (!node || String(node.status) === 'locked') {
    actionError.value = '该阶段尚未解锁，请先完成当前阶段测试。'
    return
  }
  if (stageRoute(node) === '/exercise') {
    const bankIds = Array.isArray(node.question_bank_ids) ? node.question_bank_ids.map(String).filter(Boolean) : []
    await router.push({
      path: '/exercise',
      query: {
        stage: nodeId(node),
        autostart: '1',
        ...(bankIds.length ? { bank: bankIds[bankIds.length - 1] } : {}),
      },
    })
    return
  }
  await router.push(stageRoute(node))
}

function formatDate(value: string) {
  if (!value) return '尚未持久化更新时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

onMounted(() => {
  void loadPath().then(() => {
    if (!feedLoadedSuccessfully.value && !recommendations.value.length && overview.value?.recommendations.length) {
      recommendations.value = overview.value.recommendations
      selectedResourceId.value = resourceId(recommendations.value[0])
    }
  })
  void loadFeed()
  void loadLearnerEvidence().catch((reason: any) => { actionError.value = reason?.message || '学习证据加载失败' })
  window.addEventListener('focus', syncVisiblePath)
  document.addEventListener('visibilitychange', syncVisiblePath)
  pathRefreshTimer = window.setInterval(syncVisiblePath, 5000)
})

onBeforeUnmount(() => {
  window.removeEventListener('focus', syncVisiblePath)
  document.removeEventListener('visibilitychange', syncVisiblePath)
  if (pathRefreshTimer !== null) window.clearInterval(pathRefreshTimer)
})
</script>

<template>
  <div class="competition-page path-command-page">
    <form class="shot-path-goal" @submit.prevent="generatePath"><label for="path-real-goal">学习目标</label><input id="path-real-goal" v-model="goalInput" placeholder="输入希望达成的真实能力或项目成果" /><button type="submit" :disabled="planning || !goalInput.trim()"><LoaderCircle v-if="planning" class="spin" :size="15" /><Sparkles v-else :size="15" />{{ overview?.has_plan ? '重新规划' : '生成路径' }}</button></form>
    <section class="shot-path" aria-label="本周学习路径">
      <div v-if="pathError || feedError || actionError" class="shot-notice is-error"><CircleAlert :size="18" />{{ actionError || pathError || feedError }}<button type="button" @click="refreshAll">重新加载</button></div>
      <div v-if="notice" class="shot-notice"><Check :size="18" />{{ notice }}</div>
      <div v-if="pathLoading && !overview" class="shot-loading"><span class="os-spinner"></span><p>正在合并画像、诊断、知识与资源证据……</p></div>
      <template v-else-if="overview">
        <aside class="shot-path-profile">
          <header><strong><span><UserRound :size="15" /></span>学习画像</strong></header>
          <div class="shot-path-person"><span class="shot-path-avatar-photo" role="img" aria-label="学习者头像"></span><div><h2>{{ profileOverview?.learner.display_name || '同学' }}，你好！</h2><small>画像版本 {{ profileOverview?.learner.profile_version || '尚未生成' }}</small></div></div>
          <dl>
            <div><dt><Target :size="13" />当前目标</dt><dd>{{ goals || '尚未设置' }}</dd></div>
            <div><dt><Clock3 :size="13" />学习节奏</dt><dd>{{ learnerDimensions.pace_preference || '待识别' }}</dd></div>
            <div><dt><BookOpenCheck :size="13" />知识基础</dt><dd>{{ learnerDimensions.knowledge_base_level || '待识别' }}</dd></div>
            <div><dt><Lightbulb :size="13" />认知偏好</dt><dd>{{ learnerDimensions.cognitive_style || '待识别' }}</dd></div>
            <div><dt><CircleAlert :size="13" />易错点</dt><dd>{{ profileOverview?.focus.weak_points[0] || '暂无证据' }}</dd></div>
          </dl>
          <div class="shot-path-bars"><label><span><Gauge :size="13" />最近正确率</span><b>{{ evaluationOverview?.accuracy || 0 }}%</b></label><i><b :style="{ width: `${evaluationOverview?.accuracy || 0}%` }"></b></i><label><span><Clock3 :size="13" />画像完整度</span><b>{{ profileOverview?.completeness || 0 }}%</b></label><i><b :style="{ width: `${profileOverview?.completeness || 0}%` }"></b></i></div>
          <div class="shot-path-radar"><strong><Target :size="14" />能力证据</strong><div class="shot-path-radar-canvas"><svg viewBox="0 0 238 156" role="img" aria-label="学习路径能力雷达图"><g class="path-radar-grid"><polygon v-for="level in [25,50,75,100]" :key="level" :points="pathRadarPolygon(Array(5).fill(level))" /><line v-for="(point,index) in pathRadarAxes" :key="index" x1="119" y1="78" :x2="point.x" :y2="point.y" /></g><polygon class="path-radar-series" :points="pathRadarPolygon(pathRadarValues)" /><circle v-for="(item,index) in pathRadarDimensions" :key="item.label" :cx="pathRadarPoint(index,item.value).x" :cy="pathRadarPoint(index,item.value).y" r="2.8" /></svg><label class="radar-concept">{{ pathRadarDimensions[0].label }}<b>{{ pathRadarDimensions[0].value }}</b></label><label class="radar-apply">{{ pathRadarDimensions[1].label }}<b>{{ pathRadarDimensions[1].value }}</b></label><label class="radar-practice">{{ pathRadarDimensions[2].label }}<b>{{ pathRadarDimensions[2].value }}</b></label><label class="radar-memory">{{ pathRadarDimensions[3].label }}<b>{{ pathRadarDimensions[3].value }}</b></label><label class="radar-logic">{{ pathRadarDimensions[4].label }}<b>{{ pathRadarDimensions[4].value }}</b></label></div></div>
        </aside>

        <main class="shot-path-main"><header><div><h1>为你生成的本周学习路径</h1><p>基于学习画像、练习表现和资源反馈动态调整</p></div><button type="button" :disabled="pathRefreshing || feedLoading" @click="refreshAll"><RefreshCw :size="15" />路径总览</button></header>
          <section class="shot-path-metrics"><article><small>当前掌握度</small><strong>{{ currentPathMastery }}%</strong><i class="metric-ring" :style="{ background: `conic-gradient(#1769ff 0 ${currentPathMastery}%, #dce8f6 ${currentPathMastery}% 100%)` }"><b></b></i></article><article class="metric-resources"><small>推荐资源</small><strong>{{ recommendations.length }}<em>个</em></strong><Layers3 :size="36" /></article></section>
          <section v-if="displayStages.length" class="shot-route-track">
            <svg class="shot-route-wave" viewBox="0 0 860 90" preserveAspectRatio="none" aria-hidden="true"><path class="wave-base" d="M0 52 C38 52 43 38 70 42 S112 62 150 48 S177 27 194 42 S250 74 302 24 S360 58 426 45 S488 66 558 45 S620 63 686 48 S765 58 860 50"/><path class="wave-done" d="M0 52 C38 52 43 38 70 42 S112 62 150 48 S177 27 194 42 S250 74 302 24"/></svg>
            <button v-for="(node,index) in displayStages" :key="node.id" type="button" :class="[`is-${node.status}`,{ active: node.id === selectedNodeId }]" @click="selectedNodeId = node.id">
              <mark v-if="node.status === 'warning'">需补强</mark>
              <div v-if="node.branches?.length" class="shot-route-branch-chain" :aria-label="`从${node.title}展开的学习分支`">
                <span><GitBranch :size="13" /></span>
                <small>{{ node.branches[0].title }}<b v-if="node.branches.length > 1"> +{{ node.branches.length - 1 }}</b></small>
              </div>
              <i>{{ index + 1 }}</i>
              <span>
                <strong>{{ node.title }}</strong><em>{{ statusLabel(String(node.status)) }}</em>
                <small>掌握度 <b>{{ node.mastery }}</b></small>
              </span>
            </button>
            <footer class="shot-route-legend"><span><i></i>已完成</span><span><i></i>当前学习</span><span><i></i>需重点补强</span><span><i></i>待学习</span></footer>
          </section>
          <div v-else class="shot-empty">尚未生成学习路径。请在上方输入真实目标并启动规划。</div>
        </main>

        <aside class="shot-path-resource"><header><h2>当前推送资源</h2></header><template v-if="selectedResource"><div class="shot-current-resource"><span><FileText :size="25" /></span><div><strong>{{ resourceTitle(selectedResource) }}</strong></div><b>{{ resourceScore(selectedResource) ?? '--' }}%</b><div class="shot-resource-tags"><em>{{ resourceType(selectedResource) }}</em><em v-for="tag in resourceTags(selectedResource).slice(0, 3)" :key="tag">{{ tag }}</em></div></div><section><h3>推荐理由</h3><p v-if="showRecommendationReason">{{ resourceReason(selectedResource) }}</p><h3>资源组合</h3><div class="shot-resource-chips"><span v-for="item in recommendations.slice(0, 4)" :key="resourceId(item)"><FileText :size="13" />{{ resourceType(item) }}</span></div></section><footer><button type="button" @click="startResourceReading"><CirclePlay :size="16" />开始学习</button><button type="button" :disabled="feedLoading" @click="replaceResource"><RefreshCw :size="15" />替换资源</button><button type="button" :aria-expanded="showRecommendationReason" @click="showRecommendationReason = !showRecommendationReason"><BookOpenCheck :size="15" />推荐依据</button><button type="button" :disabled="Boolean(feedbackPending)" @click="feedback('like')"><ThumbsUp :size="15" />有帮助</button><button type="button" :disabled="Boolean(feedbackPending)" @click="feedback('dislike')"><ThumbsDown :size="15" />暂缓推送</button><button class="shot-resource-delete" type="button" :disabled="Boolean(removingResourceId)" :aria-label="`从当前推送中删除${resourceTitle(selectedResource)}`" @click="removeCurrentResource"><LoaderCircle v-if="removingResourceId" class="spin" :size="15" /><Trash2 v-else :size="15" />{{ removingResourceId ? '删除中' : '删除推送' }}</button></footer></template><div v-else class="shot-empty">暂无推荐资源，先进入资源工坊生成内容。</div></aside>

        <section class="shot-dynamic-rules"><header><strong><ShieldCheck :size="17" />动态调整规则</strong><button type="button" aria-label="展开或收起动态调整规则" @click="showRules = !showRules"><ChevronDown :size="16" /></button></header><div v-if="showRules"><article v-for="(rule, index) in visibleRules" :key="rule" :class="{ active: index === 0 }"><strong>规则 {{ index + 1 }}</strong><p>{{ rule }}</p></article><article v-if="!visibleRules.length"><p>本次规划没有返回动态调整规则。</p></article></div></section>
        <section class="shot-agent-chain"><header><strong><Bot :size="17" />多智能体协同</strong></header><div><article><i><UserRound :size="22" /></i><span><strong>画像智能体</strong><small>分析学习行为<br>构建学习画像</small></span></article><b><ArrowRight :size="20" /></b><article><i><GitBranch :size="22" /></i><span><strong>路径智能体</strong><small>规划学习路径<br>动态调整节点</small></span></article><b><ArrowRight :size="20" /></b><article><i><Layers3 :size="22" /></i><span><strong>资源智能体</strong><small>匹配优质资源<br>组合推送内容</small></span></article><b><ArrowRight :size="20" /></b><article><i><ChartNoAxesCombined :size="22" /></i><span><strong>评估智能体</strong><small>评估学习效果<br>反馈优化策略</small></span></article></div><footer><LockKeyhole :size="13" />多智能体协同驱动，持续优化个性化学习路径</footer></section>
      </template>
    </section>

    <template v-if="false">
    <header class="os-page-header">
      <div class="os-page-title">
        <span class="os-eyebrow"><Route :size="15" /> ADAPTIVE LEARNING ROUTE</span>
        <h1>自适应学习路径</h1>
        <p>把画像、知识掌握、练习表现与资源反馈编排成可执行阶段；每次规划都保留策略依据，并让资源推荐随反馈重新排序。</p>
      </div>
      <div class="os-page-actions">
        <button class="os-button" type="button" :disabled="pathRefreshing || feedLoading" @click="refreshAll">
          <LoaderCircle v-if="pathRefreshing" class="spin" :size="15" /><RefreshCw v-else :size="15" />{{ pathRefreshing ? '同步中' : '刷新证据' }}
        </button>
        <RouterLink class="os-button os-button-primary" to="/tutor">进入智能伴学 <ArrowRight :size="15" /></RouterLink>
      </div>
    </header>

    <LearningLoopContext
      class="path-loop-context"
      stage="05"
      stage-label="路径规划"
      task="将多源学习证据编排为下一步行动"
      input="画像、知识掌握、诊断与资源反馈"
      process="路径规划智能体生成阶段与动态规则"
      :output="overview?.nodes.length ? `${overview.nodes.length} 个学习阶段` : '等待路径规划'"
      next-to="/tutor"
      next-label="智能伴学"
      status="路径执行中的问题进入伴学"
    />

    <div v-if="pathError || feedError || actionError" class="os-alert path-alert" role="alert" aria-live="assertive">
      <CircleAlert :size="18" />
      <span><strong>部分数据或操作未完成</strong><small>{{ actionError || pathError || feedError }}</small></span>
      <button class="os-button" type="button" :disabled="pathLoading || feedLoading" @click="refreshAll"><RefreshCw :size="14" />重新加载</button>
    </div>
    <div v-if="notice" class="path-notice" role="status" aria-live="polite"><Check :size="16" />{{ notice }}</div>

    <section v-if="pathLoading && !overview" class="os-card os-loading" role="status" aria-live="polite"><div><span class="os-spinner"></span><p>正在合并画像、诊断、知识与资源证据……</p></div></section>

    <section v-else-if="overview" class="path-workspace" aria-label="学习路径执行工作台">
      <aside class="path-learner-panel" aria-label="学习画像摘要">
        <h1 class="path-page-name">自适应学习路径</h1>
        <header>
          <span class="learner-portrait">{{ String(studentId || '学').slice(0, 1).toUpperCase() }}</span>
          <div><h2>同学，你好！</h2><p>Lv. 4 勤学者 · 实时画像</p></div>
        </header>
        <dl class="learner-facts">
          <div><dt>当前目标</dt><dd>{{ overview.title || '完成本周学习路径' }}</dd></div>
          <div><dt>学习节奏</dt><dd>中速</dd></div>
          <div><dt>知识基础</dt><dd>{{ pathProgress >= 60 ? '良好' : '一般' }}</dd></div>
          <div><dt>认知偏好</dt><dd>图解 + 案例</dd></div>
          <div><dt>易错点</dt><dd>{{ selectedNode?.title || '待识别' }}</dd></div>
        </dl>
        <div class="learner-radar" aria-label="能力雷达摘要">
          <strong>能力雷达</strong>
          <div class="learner-radar-shape"><span>{{ Math.max(42, pathProgress || 62) }}</span></div>
          <small>概念理解 · 逻辑思维 · 实践操作</small>
        </div>
      </aside>
      <header class="path-hero" aria-labelledby="path-plan-title">
        <div class="path-goal-panel">
          <span class="os-eyebrow"><Target :size="14" /> CURRENT OBJECTIVE</span>
          <h2 id="path-plan-title">{{ overview?.title || '生成你的第一条可执行学习路径' }}</h2>
          <p>{{ planMeta.rationale || '系统会结合当前画像、知识图谱掌握度、资源库存与反馈行为生成路径；证据不足时保留默认阶段并明确说明。' }}</p>
          <form class="goal-composer" @submit.prevent="generatePath">
            <label for="path-goal-input">本轮学习目标</label>
            <div><input id="path-goal-input" v-model="goalInput" :disabled="planning" placeholder="描述希望达成的能力或项目成果" /><button type="submit" :disabled="planning || !goalInput.trim()"><LoaderCircle v-if="planning" class="spin" :size="15" /><Sparkles v-else :size="15" />{{ planning ? '正在规划' : '重新规划' }}</button></div>
          </form>
        </div>
        <div class="path-progress-panel">
          <div class="progress-copy"><span>路径进度</span><strong>{{ pathProgress }}%</strong></div>
          <div class="progress-line" aria-hidden="true"><i :style="{ width: `${pathProgress}%` }"></i></div>
          <dl>
            <div><dt>已完成</dt><dd>{{ completedCount }} / {{ overview?.nodes.length || 0 }}</dd></div>
            <div><dt>当前阶段</dt><dd>{{ selectedNode?.step || currentStageIndex + 1 }}</dd></div>
            <div><dt>最近更新</dt><dd>{{ formatDate(overview?.updated_at || '') }}</dd></div>
          </dl>
        </div>
        <button class="rules-button" type="button" :aria-expanded="showRules" aria-controls="path-rules" @click="showRules = !showRules"><ShieldCheck :size="16" /><span><small>DYNAMIC POLICY</small><strong>{{ visibleRules.length }} 条动态调整规则</strong></span><ChevronDown :size="15" :class="{ 'is-open': showRules }" /></button>
      </header>

      <section v-if="showRules" id="path-rules" class="rules-panel" aria-label="动态调整规则">
        <header><ShieldCheck :size="17" /><div><strong>路径调整边界</strong><small>规则来自路径接口，不代表当前已触发。</small></div></header>
        <ol><li v-for="(rule, index) in visibleRules" :key="`${rule}-${index}`"><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ rule }}</li></ol>
      </section>

      <div class="path-workspace-grid">
        <nav class="path-stage-board" aria-labelledby="path-stage-title">
          <header class="board-heading"><div><span class="os-eyebrow"><GitBranch :size="14" /> EXECUTION MAP</span><h2 id="path-stage-title">阶段轨道</h2></div><span class="cp-status">{{ overview.nodes.length }} 阶段</span></header>
          <div v-if="overview.nodes.length" class="stage-rail" role="list" aria-label="学习路径阶段">
            <article v-for="(node, index) in overview.nodes" :key="nodeId(node)" :class="[`is-${node.status || 'locked'}`, { 'is-selected': nodeId(node) === nodeId(selectedNode) }]" role="listitem">
              <button type="button" :aria-current="nodeId(node) === nodeId(selectedNode) ? 'step' : undefined" @click="selectedNodeId = nodeId(node)">
                <span class="stage-marker"><component :is="stageIcon(String(node.status))" :size="15" /></span>
                <span class="stage-copy"><small>STEP {{ String(node.step || index + 1).padStart(2, '0') }} · {{ statusLabel(String(node.status)) }}</small><strong>{{ node.title }}</strong><em>{{ node.goal || node.checkpoint || '等待阶段目标' }}</em></span>
              </button>
              <i v-if="index < overview.nodes.length - 1"></i>
            </article>
          </div>
          <div v-else class="cp-empty-state compact"><span><Map :size="25" /></span><h3>尚无路径阶段</h3><p>填写学习目标并点击“重新规划”。</p></div>
        </nav>

        <main class="stage-focus">
          <article v-if="selectedNode" class="stage-brief">
            <header><span class="stage-number">{{ String(selectedNode.step || currentStageIndex + 1).padStart(2, '0') }}</span><div><span class="os-eyebrow">CURRENT STAGE</span><h2>{{ selectedNode.title }}</h2></div><span class="stage-status">{{ statusLabel(String(selectedNode.status)) }}</span></header>
            <p>{{ selectedNode.goal || '当前阶段尚未提供详细目标。' }}</p>
            <div class="stage-checkpoint"><Gauge :size="18" /><span><small>阶段验收标准</small><strong>{{ selectedNode.checkpoint || '完成阶段任务并形成可检查证据' }}</strong></span></div>
            <div class="stage-lists">
              <div><strong><ListChecks :size="14" />执行任务</strong><ul v-if="selectedNode.tasks?.length"><li v-for="task in selectedNode.tasks" :key="String(task)">{{ task }}</li></ul><p v-else>后端未返回独立任务清单，可按阶段目标执行。</p></div>
              <div><strong><BookOpenCheck :size="14" />资源类型</strong><div class="resource-chips" v-if="selectedNode.resources?.length"><span v-for="resource in selectedNode.resources" :key="String(resource)">{{ resource }}</span></div><p v-else>当前阶段未绑定指定资源类型。</p></div>
            </div>
            <button class="os-button os-button-primary stage-action" type="button" :disabled="selectedNode.status === 'locked'" @click="startStage(selectedNode)">进入对应学习模块 <ArrowRight :size="15" /></button>
          </article>
          <section class="strategy-panel" aria-label="本轮编排策略">
            <header><Lightbulb :size="15" /><strong>本轮编排策略</strong></header>
            <ol v-if="planMeta.strategy.length"><li v-for="(item, index) in planMeta.strategy" :key="`${item}-${index}`"><span>{{ index + 1 }}</span>{{ item }}</li></ol>
            <p v-else>当前概览未提供策略说明，重新规划后将在此显示。</p>
          </section>
        </main>

        <aside class="recommendation-board" aria-labelledby="recommendation-title">
          <header class="board-heading"><div><span class="os-eyebrow"><Sparkles :size="14" /> EVIDENCE-BASED PUSH</span><h2 id="recommendation-title">推荐资源</h2></div><span class="cp-status">{{ feedLoading ? '刷新中' : `${recommendations.length} 条` }}</span></header>
          <div v-if="feedLoading && !recommendations.length" class="recommend-loading" role="status"><span class="os-spinner"></span><p>正在计算资源匹配权重……</p></div>
          <template v-else-if="recommendations.length">
            <div class="recommendation-list" role="list" aria-label="推荐资源列表">
              <button v-for="item in displayedRecommendations" :key="resourceId(item) || resourceTitle(item)" type="button" :class="{ 'is-selected': resourceId(item) === resourceId(selectedResource) }" role="listitem" @click="selectedResourceId = resourceId(item)">
                <span class="recommend-icon"><BookOpenCheck :size="15" /></span><span><small>{{ resourceType(item) }}</small><strong>{{ resourceTitle(item) }}</strong><em>{{ resourceTiming(item) }}</em></span><b v-if="resourceScore(item) !== null">{{ resourceScore(item) }}</b>
              </button>
              <button v-if="recommendations.length > recommendationPreviewLimit" class="recommend-more" type="button" role="listitem" @click="showAllRecommendations = !showAllRecommendations"><span>{{ showAllRecommendations ? '收起推荐列表' : `查看其余 ${recommendations.length - recommendationPreviewLimit} 条` }}</span><ChevronDown :size="14" :class="{ 'is-open': showAllRecommendations }" /></button>
            </div>
            <article v-if="selectedResource" class="recommendation-detail">
              <header><div><span class="os-eyebrow">WHY THIS RESOURCE</span><h3>{{ resourceTitle(selectedResource) }}</h3></div><span v-if="resourceScore(selectedResource) !== null" class="score-badge"><small>推荐分</small><strong>{{ resourceScore(selectedResource) }}</strong></span></header>
              <div class="recommend-reason"><Compass :size="17" /><span><small>推荐理由</small><strong>{{ resourceReason(selectedResource) }}</strong></span></div>
              <dl><div><dt><Clock3 :size="13" />使用时机</dt><dd>{{ resourceTiming(selectedResource) }}</dd></div><div><dt><Target :size="13" />关联标签</dt><dd><span v-for="tag in resourceTags(selectedResource)" :key="tag">{{ tag }}</span><em v-if="!resourceTags(selectedResource).length">接口未返回标签</em></dd></div></dl>
              <div class="recommend-actions">
                <a v-if="resourceUrl(selectedResource)" class="os-button os-button-primary" :href="resourceUrl(selectedResource)" target="_blank" rel="noreferrer"><Download :size="15" />打开资源</a>
                <RouterLink v-else class="os-button os-button-primary" to="/workshop"><BookOpenCheck :size="15" />资源工坊</RouterLink>
                <button class="feedback-button is-like" type="button" :disabled="Boolean(feedbackPending)" @click="feedback('like')"><LoaderCircle v-if="feedbackPending === 'like'" class="spin" :size="14" /><ThumbsUp v-else :size="14" />有帮助</button>
                <button class="feedback-button" type="button" :disabled="Boolean(feedbackPending)" @click="feedback('dislike')"><LoaderCircle v-if="feedbackPending === 'dislike'" class="spin" :size="14" /><ThumbsDown v-else :size="14" />不匹配</button>
              </div>
            </article>
          </template>
          <div v-else class="cp-empty-state compact"><span><Heart :size="25" /></span><h3>暂无可推荐资源</h3><p>先在资源工坊生成资源，或刷新推荐流。</p><RouterLink class="os-button os-button-primary" to="/workshop">前往资源工坊 <ArrowRight :size="15" /></RouterLink></div>
        </aside>
      </div>

      <footer class="path-next"><span><Sparkles :size="18" /></span><div><strong>路径会随新证据演进</strong><small>伴学提问、资源反馈与练习结果都会进入下一轮规划。</small></div><RouterLink class="os-button os-button-primary" to="/tutor">进入智能伴学 <ArrowRight :size="15" /></RouterLink></footer>
    </section>

    <section v-else class="os-card cp-empty-state"><span><Map :size="25" /></span><h3>路径数据暂不可用</h3><p>请重新加载，或输入学习目标生成新路径。</p><button class="os-button os-button-primary" type="button" @click="loadPath()"><RefreshCw :size="14" />重新加载</button></section>
    </template>
  </div>
</template>

<style scoped>
.path-command-page { display: grid; gap: 17px; }
.shot-path-goal { display: grid; grid-template-columns: auto minmax(260px, 1fr) auto; align-items: center; gap: 10px; margin: 0 0 12px; padding: 10px 12px; border: 1px solid #dce7f5; border-radius: 12px; background: #fff; }
.shot-path-goal label { color: #243b5a; font-size: 12px; font-weight: 800; }
.shot-path-goal input { min-width: 0; height: 38px; padding: 0 12px; border: 1px solid #d7e3f2; border-radius: 9px; outline: none; color: #10284a; background: #f8fbff; }
.shot-path-goal input:focus { border-color: #2674ff; box-shadow: 0 0 0 3px rgba(38,116,255,.1); }
.shot-path-goal button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-width: 108px; height: 38px; padding: 0 15px; border: 0; border-radius: 9px; color: #fff; background: linear-gradient(135deg,#1467ff,#2799ef); font-weight: 800; cursor: pointer; }
.shot-path-goal button:disabled { opacity: .5; cursor: not-allowed; }
.path-alert { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px; padding: 13px 15px; }.path-alert > span { display: grid; gap: 2px; }.path-alert small { color: var(--cp-muted); }
.path-notice { display: flex; align-items: center; gap: 9px; padding: 12px 15px; color: #0f579f; border: 1px solid rgba(23,105,255,.18); border-radius: 13px; background: #edf5ff; font-size: 12px; font-weight: 720; }
.path-hero { display: grid; grid-template-columns: minmax(0,1.55fr) 290px 240px; align-items: stretch; overflow: hidden; border-radius: 19px; }
.path-goal-panel { padding: 24px 27px; }.path-goal-panel .os-eyebrow,.strategy-panel .os-eyebrow { color: #7cc9ff; }.path-goal-panel h2 { max-width: 720px; margin: 13px 0 7px; color: #f5f9ff; font-size: clamp(22px,2.2vw,31px); line-height: 1.15; letter-spacing: -.045em; }.path-goal-panel > p { max-width: 760px; margin: 0; color: #9ab1cb; font-size: 10px; line-height: 1.65; }
.goal-composer { display: grid; gap: 6px; margin-top: 17px; }.goal-composer label { color: #96afd0; font-size: 10px; font-weight: 720; }.goal-composer > div { display: grid; grid-template-columns: 1fr auto; gap: 7px; }.goal-composer input { min-width: 0; height: 42px; padding: 0 13px; color: #eaf4ff; border: 1px solid rgba(125,174,228,.25); border-radius: 11px; background: rgba(5,25,50,.6); font: inherit; font-size: 11px; }.goal-composer input::placeholder { color: #6f89a7; }.goal-composer button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 15px; color: #fff; border: 0; border-radius: 11px; background: linear-gradient(135deg,#1769ff,#008edc); font-size: 10px; font-weight: 760; cursor: pointer; }.goal-composer button:disabled { opacity: .55; cursor: not-allowed; }
.path-progress-panel { display: grid; grid-template-columns: 118px 1fr; align-items: center; gap: 13px; padding: 20px; border-left: 1px solid rgba(113,158,210,.18); background: rgba(14,48,84,.55); }.progress-orbit { display: grid; place-items: center; width: 112px; height: 112px; border-radius: 50%; background: conic-gradient(#44c7ff var(--progress),rgba(125,170,215,.16) 0); }.progress-orbit::before { grid-area: 1/1; width: 88px; height: 88px; border-radius: 50%; background: #102b4c; content: ''; }.progress-orbit > span { z-index: 1; grid-area: 1/1; display: grid; grid-template-columns: auto auto; align-items: baseline; justify-content: center; }.progress-orbit strong { color: #fff; font-size: 27px; }.progress-orbit em { color: #66cbff; font-size: 10px; font-style: normal; }.progress-orbit small { grid-column: span 2; color: #87a3c1; font-size: 10px; text-align: center; }.path-progress-panel dl { display: grid; gap: 9px; margin: 0; }.path-progress-panel dl div { display: grid; gap: 2px; padding-bottom: 8px; border-bottom: 1px solid rgba(117,158,201,.15); }.path-progress-panel dt { color: #7895b4; font-size: 10px; }.path-progress-panel dd { overflow: hidden; margin: 0; color: #e9f4ff; font-size: 10px; line-height: 1.4; text-overflow: ellipsis; }
.rules-button { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 9px; min-width: 0; padding: 20px; color: #cfe7ff; border: 0; border-left: 1px solid rgba(113,158,210,.18); background: rgba(9,31,57,.72); text-align: left; cursor: pointer; }.rules-button:hover { background: rgba(17,52,88,.85); }.rules-button > span { display: grid; gap: 4px; min-width: 0; }.rules-button small { color: #67caff; font-size: 10px; letter-spacing: .08em; }.rules-button strong { font-size: 10px; }.rules-button svg:last-child { transition: transform .2s ease; }.rules-button svg:last-child.is-open { transform: rotate(180deg); }
.rules-panel { display: grid; grid-template-columns: 250px 1fr; gap: 20px; padding: 18px 20px; }.rules-panel > header { display: flex; align-items: flex-start; gap: 10px; }.rules-panel > header > span { display: grid; place-items: center; width: 36px; height: 36px; color: var(--cp-blue); border-radius: 10px; background: var(--cp-blue-soft); }.rules-panel header div { display: grid; gap: 3px; }.rules-panel strong { font-size: 10px; }.rules-panel small { color: var(--cp-muted); font-size: 10px; line-height: 1.45; }.rules-panel ol { display: grid; grid-template-columns: repeat(3,1fr); gap: 8px; margin: 0; padding: 0; list-style: none; }.rules-panel li { display: grid; grid-template-columns: 24px 1fr; align-items: start; gap: 7px; padding: 10px; color: #536780; border-radius: 9px; background: #f5f8fd; font-size: 10px; line-height: 1.5; }.rules-panel li span { color: var(--cp-blue); font-weight: 800; }
.path-stage-board,.recommendation-board { padding: 21px; }.board-heading { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding-bottom: 15px; border-bottom: 1px solid var(--cp-line); }.board-heading > div { display: grid; gap: 4px; }.board-heading h2 { margin: 0; color: var(--cp-text); font-size: 17px; letter-spacing: -.02em; }.board-heading p { margin: 0; color: var(--cp-muted); font-size: 10px; }
.stage-rail { display: grid; grid-template-columns: repeat(auto-fit,minmax(155px,1fr)); gap: 0; margin-top: 21px; overflow-x: auto; padding: 2px 0 5px; }.stage-rail article { position: relative; min-width: 150px; }.stage-rail article > button { display: grid; justify-items: start; gap: 10px; width: 100%; min-height: 140px; padding: 5px 15px 12px 3px; color: var(--cp-text); border: 0; background: transparent; text-align: left; cursor: pointer; }.stage-marker { position: relative; z-index: 2; display: grid; place-items: center; width: 34px; height: 34px; color: #7890aa; border: 2px solid #fff; border-radius: 50%; background: #e8eef6; box-shadow: 0 0 0 1px #ccd8e7; }.stage-copy { display: grid; gap: 5px; min-width: 0; }.stage-copy small { color: #8092a8; font-size: 10px; font-weight: 780; }.stage-copy strong { font-size: 10px; line-height: 1.35; }.stage-copy em { display: -webkit-box; overflow: hidden; color: var(--cp-muted); font-size: 10px; font-style: normal; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }.stage-rail article > i { position: absolute; top: 21px; left: 34px; width: calc(100% - 18px); height: 1px; background: #d9e3ef; }.stage-rail article.is-completed .stage-marker,.stage-rail article.is-done .stage-marker { color: #fff; background: #2377e9; box-shadow: 0 0 0 1px #2377e9; }.stage-rail article.is-current .stage-marker,.stage-rail article.is-active .stage-marker { color: #fff; background: #00aeea; box-shadow: 0 0 0 5px rgba(0,174,234,.12); }.stage-rail article.is-selected > button { border-radius: 11px; background: #f4f8ff; }.stage-rail article.is-selected .stage-copy strong { color: var(--cp-blue); }
.stage-detail-layout { display: grid; grid-template-columns: minmax(0,1.45fr) minmax(300px,.65fr); gap: 14px; }.stage-brief { padding: 22px; }.stage-brief > header { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 11px; }.stage-number { display: grid; place-items: center; width: 43px; height: 43px; color: var(--cp-blue); border-radius: 12px; background: var(--cp-blue-soft); font-size: 13px; font-weight: 850; }.stage-brief header > div { display: grid; gap: 3px; }.stage-brief h2 { margin: 0; font-size: 17px; }.stage-status { padding: 6px 9px; color: var(--cp-blue-ink); border-radius: 99px; background: var(--cp-blue-soft); font-size: 10px; font-weight: 780; }.stage-brief > p { margin: 17px 0 0; color: var(--cp-muted); font-size: 10px; line-height: 1.65; }.stage-checkpoint { display: flex; align-items: flex-start; gap: 10px; margin-top: 15px; padding: 13px; color: var(--cp-blue); border-radius: 11px; background: #eef5ff; }.stage-checkpoint span { display: grid; gap: 3px; }.stage-checkpoint small { color: #6880a0; font-size: 10px; }.stage-checkpoint strong { color: #23496f; font-size: 10px; line-height: 1.5; }.stage-lists { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 15px; }.stage-lists > div { padding: 13px; border: 1px solid var(--cp-line); border-radius: 11px; background: #fbfdff; }.stage-lists > div > strong { display: flex; align-items: center; gap: 6px; font-size: 10px; }.stage-lists ul { display: grid; gap: 6px; margin: 9px 0 0; padding-left: 17px; color: var(--cp-muted); font-size: 10px; line-height: 1.5; }.stage-lists p { margin: 9px 0 0; color: var(--cp-muted); font-size: 10px; line-height: 1.5; }.resource-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }.resource-chips span { padding: 5px 7px; color: var(--cp-blue-ink); border-radius: 7px; background: var(--cp-blue-soft); font-size: 10px; }.stage-action { width: fit-content; margin-top: 15px; }
.strategy-panel { padding: 22px; border-radius: 18px; }.strategy-panel h2 { margin: 13px 0 16px; color: #f3f8ff; font-size: 21px; }.strategy-panel ol { display: grid; gap: 0; margin: 0; padding: 0; list-style: none; }.strategy-panel li { display: grid; grid-template-columns: 27px 1fr; gap: 9px; padding: 11px 0; color: #a8bdd4; border-top: 1px solid rgba(137,177,219,.15); font-size: 10px; line-height: 1.55; }.strategy-panel li span { display: grid; place-items: center; width: 25px; height: 25px; color: #6dccff; border-radius: 7px; background: rgba(29,100,154,.35); font-weight: 800; }.strategy-empty { display: grid; place-items: center; gap: 10px; min-height: 180px; color: #6dcaff; text-align: center; }.strategy-empty p { max-width: 270px; margin: 0; color: #92aac3; font-size: 10px; line-height: 1.6; }.strategy-empty code { color: #76ceff; }
.recommendation-layout { display: grid; grid-template-columns: minmax(285px,.78fr) minmax(0,1.3fr); gap: 14px; margin-top: 15px; }.recommend-loading { display: grid; place-items: center; align-content: center; gap: 10px; min-height: 250px; color: var(--cp-muted); }.recommendation-list { display: grid; align-content: start; gap: 7px; max-height: 410px; overflow: auto; }.recommendation-list button { display: grid; grid-template-columns: 35px 1fr auto; align-items: center; gap: 9px; min-height: 69px; padding: 10px; color: var(--cp-text); border: 1px solid var(--cp-line); border-radius: 11px; background: #fbfdff; text-align: left; cursor: pointer; }.recommendation-list button:hover,.recommendation-list button.is-selected { border-color: rgba(23,105,255,.38); background: #f1f7ff; }.recommend-icon { display: grid; place-items: center; width: 34px; height: 34px; color: var(--cp-blue); border-radius: 10px; background: var(--cp-blue-soft); }.recommendation-list button > span:nth-child(2) { display: grid; gap: 3px; min-width: 0; }.recommendation-list small { color: var(--cp-blue); font-size: 10px; }.recommendation-list strong { overflow: hidden; font-size: 10px; white-space: nowrap; text-overflow: ellipsis; }.recommendation-list em { overflow: hidden; color: var(--cp-muted); font-size: 10px; font-style: normal; white-space: nowrap; text-overflow: ellipsis; }.recommendation-list b { display: grid; place-items: center; width: 31px; height: 31px; color: var(--cp-blue-ink); border-radius: 9px; background: #e8f2ff; font-size: 10px; }
.recommendation-list .recommend-more { display: flex; align-items: center; justify-content: center; gap: 7px; min-height: 41px; color: var(--cp-blue); border-style: dashed; background: #f6f9ff; text-align: center; font-size: 10px; font-weight: 760; }.recommend-more svg { transition: transform .2s ease; }.recommend-more svg.is-open { transform: rotate(180deg); }
.recommendation-detail { padding: 19px; border: 1px solid var(--cp-line); border-radius: 13px; background: #fff; }.recommendation-detail > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }.recommendation-detail header > div { display: grid; gap: 4px; min-width: 0; }.recommendation-detail h3 { margin: 0; font-size: 16px; line-height: 1.35; }.score-badge { display: grid; place-items: center; flex: 0 0 56px; width: 56px; height: 56px; color: var(--cp-blue); border-radius: 16px; background: var(--cp-blue-soft); }.score-badge small { font-size: 10px; }.score-badge strong { font-size: 18px; }.recommend-reason { display: flex; align-items: flex-start; gap: 10px; margin-top: 16px; padding: 13px; color: var(--cp-blue); border-radius: 11px; background: #eef5ff; }.recommend-reason span { display: grid; gap: 3px; }.recommend-reason small { color: #6880a0; font-size: 10px; }.recommend-reason strong { color: #23496f; font-size: 10px; line-height: 1.5; }.recommendation-detail dl { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 13px 0 0; }.recommendation-detail dl div { padding: 11px; border: 1px solid var(--cp-line); border-radius: 10px; }.recommendation-detail dt { display: flex; align-items: center; gap: 5px; color: var(--cp-muted); font-size: 10px; }.recommendation-detail dd { display: flex; flex-wrap: wrap; gap: 5px; margin: 8px 0 0; color: var(--cp-text); font-size: 10px; line-height: 1.45; }.recommendation-detail dd span { padding: 4px 6px; color: var(--cp-blue-ink); border-radius: 6px; background: var(--cp-blue-soft); font-size: 10px; }.recommendation-detail dd em { color: var(--cp-muted); font-style: normal; }.recommend-actions { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 14px; }.feedback-button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 41px; padding: 0 12px; color: #687b91; border: 1px solid var(--cp-line); border-radius: 11px; background: #fff; font-size: 10px; font-weight: 720; cursor: pointer; }.feedback-button:hover:not(:disabled) { color: var(--cp-blue); border-color: rgba(23,105,255,.35); }.feedback-button.is-like { margin-left: auto; }.feedback-button:disabled { opacity: .55; cursor: not-allowed; }
.path-next { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 13px; padding: 16px 18px; border: 1px solid var(--cp-line); border-radius: 15px; }.path-next > span { display: grid; place-items: center; width: 40px; height: 40px; color: var(--cp-blue); border-radius: 11px; background: var(--cp-blue-soft); }.path-next > div { display: grid; gap: 3px; }.path-next strong { font-size: 11px; }.path-next small { color: var(--cp-muted); font-size: 10px; }
.spin { animation: path-spin .8s linear infinite; } @keyframes path-spin { to { transform: rotate(360deg); } }
@media (max-width: 1160px) { .path-hero { grid-template-columns: 1fr 290px; }.rules-button { grid-column: span 2; border-top: 1px solid rgba(113,158,210,.18); border-left: 0; }.rules-panel { grid-template-columns: 1fr; }.stage-detail-layout { grid-template-columns: 1fr; }.strategy-panel { min-height: auto; } }
@media (max-width: 850px) { .path-hero { grid-template-columns: 1fr; }.path-progress-panel,.rules-button { grid-column: auto; border-top: 1px solid rgba(113,158,210,.18); border-left: 0; }.rules-panel ol { grid-template-columns: 1fr; }.recommendation-layout { grid-template-columns: 1fr; }.recommendation-list { grid-template-columns: 1fr 1fr; max-height: 520px; } }
@media (max-width: 650px) { .path-alert { grid-template-columns: auto 1fr; }.path-alert .os-button { grid-column: span 2; }.goal-composer > div { grid-template-columns: 1fr; }.goal-composer button { min-height: 42px; }.path-progress-panel { grid-template-columns: 112px 1fr; }.board-heading { align-items: flex-start; flex-direction: column; }.stage-rail { grid-template-columns: 1fr; overflow: visible; }.stage-rail article { min-width: 0; }.stage-rail article > button { grid-template-columns: 34px 1fr; align-items: start; min-height: auto; padding: 10px; }.stage-copy { grid-column: 2; grid-row: 1; }.stage-rail article > i { top: 43px; left: 26px; width: 1px; height: calc(100% - 26px); }.stage-brief > header { grid-template-columns: auto 1fr; }.stage-status { grid-column: span 2; width: fit-content; }.stage-lists,.recommendation-detail dl { grid-template-columns: 1fr; }.recommendation-list { grid-template-columns: 1fr; }.recommend-actions .os-button { flex: 1 1 100%; }.feedback-button.is-like { margin-left: 0; }.path-next { grid-template-columns: auto 1fr; }.path-next .os-button { grid-column: span 2; } }
@media (max-width: 420px) { .path-progress-panel { grid-template-columns: 1fr; justify-items: center; }.path-progress-panel dl { width: 100%; }.path-goal-panel { padding: 21px; }.recommend-actions { display: grid; grid-template-columns: 1fr 1fr; }.recommend-actions .os-button { grid-column: span 2; }.path-next { grid-template-columns: 1fr; }.path-next > span { display: none; }.path-next .os-button { grid-column: auto; } }

/* Continuous route workspace ------------------------------------------------ */
.path-command-page { gap: 12px; }
.path-loop-context { margin: 0; }
.path-workspace {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  min-height: 720px;
  height: min(820px, calc(100vh - 150px));
  overflow: hidden;
  border: 1px solid #dce6f2;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 18px 48px rgba(36, 74, 120, .08);
}
.path-workspace .path-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) 300px 220px;
  align-items: stretch;
  min-height: 154px;
  overflow: visible;
  color: var(--cp-text);
  border: 0;
  border-bottom: 1px solid #dce6f2;
  border-radius: 0;
  background: linear-gradient(105deg, #f8fbff 0%, #fff 67%);
  box-shadow: none;
}
.path-workspace .path-goal-panel { padding: 19px 22px 17px; }
.path-workspace .path-goal-panel .os-eyebrow { color: var(--cp-blue); }
.path-workspace .path-goal-panel h2 { max-width: none; margin: 8px 0 4px; color: #142a43; font-size: clamp(20px, 1.7vw, 27px); }
.path-workspace .path-goal-panel > p { max-width: 820px; color: #657a92; font-size: 11px; line-height: 1.55; }
.path-workspace .goal-composer { grid-template-columns: 118px 1fr; align-items: center; gap: 9px; margin-top: 12px; }
.path-workspace .goal-composer label { color: #536b85; font-size: 11px; }
.path-workspace .goal-composer input { height: 38px; color: #1b3049; border-color: #d5e1ef; border-radius: 7px; background: #fff; font-size: 11px; }
.path-workspace .goal-composer input::placeholder { color: #8b9bad; }
.path-workspace .goal-composer button { border-radius: 7px; }
.path-workspace .path-progress-panel { display: grid; grid-template-columns: 1fr; align-content: center; gap: 8px; padding: 18px 20px; border-left: 1px solid #dce6f2; background: #fff; }
.progress-copy { display: flex; align-items: baseline; justify-content: space-between; color: #6a7f97; font-size: 11px; }
.progress-copy strong { color: #1769ff; font-size: 24px; }
.progress-line { height: 6px; overflow: hidden; border-radius: 99px; background: #e8eff7; }
.progress-line i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #1769ff, #00b4df); }
.path-workspace .path-progress-panel dl { grid-template-columns: auto auto 1fr; gap: 0; }
.path-workspace .path-progress-panel dl div { gap: 1px; padding: 0 11px; border: 0; border-left: 1px solid #e1e8f1; }
.path-workspace .path-progress-panel dl div:first-child { padding-left: 0; border-left: 0; }
.path-workspace .path-progress-panel dt { color: #8a9bae; font-size: 9px; }
.path-workspace .path-progress-panel dd { color: #283e56; font-size: 10px; }
.path-workspace .rules-button { padding: 18px; color: #27435f; border-left: 1px solid #dce6f2; background: #f5f8fc; }
.path-workspace .rules-button:hover { background: #eef4fb; }
.path-workspace .rules-button small { color: var(--cp-blue); }
.path-workspace .rules-panel { display: grid; grid-template-columns: 230px 1fr; gap: 14px; padding: 11px 18px; border-bottom: 1px solid #dce6f2; background: #f8fbff; }
.path-workspace .rules-panel > header { align-items: center; }
.path-workspace .rules-panel > header > svg { color: var(--cp-blue); }
.path-workspace .rules-panel ol { display: flex; gap: 0; overflow-x: auto; }
.path-workspace .rules-panel li { flex: 0 0 min(280px, 28vw); padding: 7px 12px; border-left: 1px solid #dce6f2; border-radius: 0; background: transparent; }
.path-workspace-grid { display: grid; grid-template-columns: 248px minmax(360px, 1fr) minmax(320px, .82fr); min-height: 0; }
.path-stage-board,
.stage-focus,
.recommendation-board { min-width: 0; min-height: 0; }
.path-stage-board { display: grid; grid-template-rows: auto minmax(0, 1fr); border-right: 1px solid #dce6f2; background: #f8fafc; }
.path-workspace .board-heading { min-height: 63px; padding: 12px 15px; border-bottom: 1px solid #dce6f2; }
.path-workspace .board-heading h2 { font-size: 15px; }
.path-workspace .board-heading p { display: none; }
.path-stage-board .stage-rail { display: block; margin: 0; overflow-y: auto; padding: 8px 0; }
.path-stage-board .stage-rail article { min-width: 0; }
.path-stage-board .stage-rail article > button { display: grid; grid-template-columns: 32px 1fr; align-items: start; gap: 10px; min-height: 82px; padding: 10px 13px; border-left: 3px solid transparent; border-radius: 0; }
.path-stage-board .stage-rail article.is-selected > button { border-left-color: #1769ff; border-radius: 0; background: #eaf2ff; }
.path-stage-board .stage-marker { width: 30px; height: 30px; }
.path-stage-board .stage-copy { grid-column: 2; grid-row: 1; gap: 3px; }
.path-stage-board .stage-copy strong { font-size: 11px; }
.path-stage-board .stage-copy em { font-size: 9px; -webkit-line-clamp: 1; }
.path-stage-board .stage-rail article > i { top: 40px; left: 28px; width: 1px; height: calc(100% - 18px); }
.stage-focus { display: grid; grid-template-rows: minmax(0, 1fr) auto; overflow: hidden; border-right: 1px solid #dce6f2; background: #fff; }
.path-workspace .stage-brief { overflow-y: auto; padding: 20px 22px 15px; }
.path-workspace .stage-brief > header { grid-template-columns: auto 1fr auto; }
.path-workspace .stage-brief > p { margin-top: 13px; font-size: 11px; }
.path-workspace .stage-number { width: 38px; height: 38px; border-radius: 8px; }
.path-workspace .stage-checkpoint { margin-top: 13px; padding: 11px 0; border-top: 1px solid #e1e8f1; border-bottom: 1px solid #e1e8f1; border-radius: 0; background: transparent; }
.path-workspace .stage-lists { margin-top: 11px; }
.path-workspace .stage-lists > div { padding: 0 14px 0 0; border: 0; border-right: 1px solid #e1e8f1; border-radius: 0; background: transparent; }
.path-workspace .stage-lists > div:last-child { padding: 0 0 0 2px; border-right: 0; }
.path-workspace .stage-action { margin-top: 12px; }
.path-workspace .strategy-panel { display: grid; grid-template-columns: 175px 1fr; align-items: start; gap: 12px; max-height: 146px; overflow-y: auto; padding: 13px 18px; color: #233b55; border: 0; border-top: 1px solid #dce6f2; border-radius: 0; background: #f7faff; }
.path-workspace .strategy-panel > header { display: flex; align-items: center; gap: 7px; color: #1769ff; }
.path-workspace .strategy-panel ol { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; padding: 0; list-style: none; }
.path-workspace .strategy-panel li { display: grid; grid-template-columns: 22px 1fr; gap: 7px; padding: 4px 10px; color: #576e87; border: 0; border-left: 1px solid #dce6f2; font-size: 9px; line-height: 1.45; }
.path-workspace .strategy-panel li span { display: grid; place-items: center; width: 20px; height: 20px; color: #1769ff; border-radius: 5px; background: #e6f0ff; font-weight: 800; }
.path-workspace .strategy-panel > p { margin: 0; color: #7b8ea3; font-size: 10px; }
.recommendation-board { display: grid; grid-template-rows: auto minmax(132px, .85fr) minmax(230px, 1.15fr); overflow: hidden; background: #fbfcfe; }
.recommendation-board > .recommend-loading,
.recommendation-board > .cp-empty-state { grid-row: 2 / 4; }
.path-workspace .recommendation-list { max-height: none; overflow-y: auto; gap: 0; border-bottom: 1px solid #dce6f2; }
.path-workspace .recommendation-list button { min-height: 58px; padding: 8px 13px; border: 0; border-bottom: 1px solid #e4ebf3; border-radius: 0; background: transparent; }
.path-workspace .recommendation-list button:hover,
.path-workspace .recommendation-list button.is-selected { border-color: #e4ebf3; box-shadow: inset 3px 0 #1769ff; background: #eef5ff; }
.path-workspace .recommend-icon { width: 31px; height: 31px; border-radius: 7px; }
.path-workspace .recommendation-detail { overflow-y: auto; padding: 15px 16px; border: 0; border-radius: 0; background: #fff; }
.path-workspace .recommendation-detail h3 { font-size: 14px; }
.path-workspace .score-badge { flex-basis: 48px; width: 48px; height: 48px; border-radius: 8px; }
.path-workspace .recommend-reason { margin-top: 11px; padding: 9px 0; border-top: 1px solid #e1e8f1; border-bottom: 1px solid #e1e8f1; border-radius: 0; background: transparent; }
.path-workspace .recommendation-detail dl { gap: 0; margin-top: 8px; }
.path-workspace .recommendation-detail dl div { padding: 8px 9px; border: 0; border-right: 1px solid #e1e8f1; border-radius: 0; }
.path-workspace .recommendation-detail dl div:last-child { border-right: 0; }
.path-workspace .recommend-actions { margin-top: 9px; }
.path-workspace .feedback-button { min-height: 36px; border-radius: 7px; }
.path-workspace .feedback-button.is-like { margin-left: 0; }
.path-workspace .path-next { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; min-height: 55px; padding: 8px 13px 8px 17px; border: 0; border-top: 1px solid #dce6f2; border-radius: 0; background: #f6f9fd; }
.path-workspace .path-next > span { display: grid; place-items: center; width: 30px; height: 30px; color: #1769ff; border-radius: 7px; background: #e6f0ff; }
.path-workspace .path-next > div { display: grid; gap: 1px; }
.path-workspace .path-next strong { font-size: 10px; }
.path-workspace .path-next small { color: #72859b; font-size: 9px; }

@media (max-width: 1180px) {
  .path-workspace { height: auto; min-height: 0; overflow: visible; }
  .path-workspace .path-hero { grid-template-columns: minmax(0, 1fr) 280px; }
  .path-workspace .rules-button { grid-column: span 2; min-height: 58px; border-top: 1px solid #dce6f2; border-left: 0; }
  .path-workspace-grid { grid-template-columns: 220px minmax(0, 1fr); }
  .stage-focus { min-height: 520px; border-right: 0; }
  .recommendation-board { grid-column: span 2; grid-template-columns: minmax(300px, .8fr) minmax(0, 1.2fr); grid-template-rows: auto minmax(300px, auto); border-top: 1px solid #dce6f2; }
  .recommendation-board .board-heading { grid-column: span 2; }
  .recommendation-board .recommendation-list { border-right: 1px solid #dce6f2; border-bottom: 0; }
}
@media (max-width: 760px) {
  .shot-path-goal { grid-template-columns: 1fr; }
  .shot-path-goal button { width: 100%; }
  .path-loop-context { display: none; }
  .path-workspace .path-hero { grid-template-columns: 1fr; }
  .path-workspace .path-progress-panel,
  .path-workspace .rules-button { grid-column: auto; border-top: 1px solid #dce6f2; border-left: 0; }
  .path-workspace .goal-composer { grid-template-columns: 1fr; }
  .path-workspace .rules-panel { grid-template-columns: 1fr; }
  .path-workspace-grid { grid-template-columns: 1fr; }
  .path-stage-board { border-right: 0; }
  .path-stage-board .stage-rail { display: flex; overflow-x: auto; overflow-y: hidden; padding: 0; }
  .path-stage-board .stage-rail article { flex: 0 0 205px; }
  .path-stage-board .stage-rail article > i { top: 24px; left: 43px; width: calc(100% - 25px); height: 1px; }
  .stage-focus { min-height: 0; border-top: 1px solid #dce6f2; }
  .path-workspace .strategy-panel { grid-template-columns: 1fr; max-height: none; }
  .path-workspace .strategy-panel ol { grid-template-columns: 1fr; }
  .recommendation-board { grid-column: auto; grid-template-columns: 1fr; grid-template-rows: auto auto auto; }
  .recommendation-board .board-heading { grid-column: auto; }
  .recommendation-board .recommendation-list { max-height: 330px; border-right: 0; border-bottom: 1px solid #dce6f2; }
}
@media (max-width: 520px) {
  .path-workspace { border-right: 0; border-left: 0; border-radius: 0; }
  .path-workspace .path-progress-panel dl { grid-template-columns: 1fr 1fr; }
  .path-workspace .path-progress-panel dl div:last-child { grid-column: span 2; margin-top: 8px; padding-top: 8px; border-top: 1px solid #e1e8f1; border-left: 0; }
  .path-workspace .stage-brief > header { grid-template-columns: auto 1fr; }
  .path-workspace .stage-status { grid-column: span 2; }
  .path-workspace .stage-lists,
  .path-workspace .recommendation-detail dl { grid-template-columns: 1fr; }
  .path-workspace .stage-lists > div,
  .path-workspace .recommendation-detail dl div { padding: 9px 0; border-right: 0; border-bottom: 1px solid #e1e8f1; }
  .path-workspace .path-next { grid-template-columns: 1fr; padding: 12px; }
  .path-workspace .path-next > span { display: none; }
}
</style>
