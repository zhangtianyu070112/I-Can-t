<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts/core'
import { RadarChart } from 'echarts/charts'
import { RadarComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  ChartNoAxesCombined,
  Check,
  CircleAlert,
  CircleDot,
  ClipboardCheck,
  Database,
  Gauge,
  GitCompareArrows,
  History,
  Info,
  Lightbulb,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  TriangleAlert,
  WandSparkles,
} from 'lucide-vue-next'
import LearningLoopContext from '@/components/LearningLoopContext.vue'
import {
  evolveLearningStrategy,
  generateEvaluation,
  getEvaluationOverview,
  type EvaluationOverview,
} from '@/api/learningApi'
import { useStudent } from '@/composables/useStudent'

echarts.use([RadarChart, RadarComponent, TooltipComponent, CanvasRenderer])

const { studentId } = useStudent()
const router = useRouter()
const overview = ref<EvaluationOverview | null>(null)
const latestReport = ref<any>(null)
const evolutionResult = ref<any>(null)
const loading = ref(true)
const refreshing = ref(false)
const evaluating = ref(false)
const evolving = ref(false)
const error = ref('')
const notice = ref('')
const radarEl = ref<HTMLElement | null>(null)
const diagnosisEl = ref<HTMLElement | null>(null)
const activeDiagnosisTab = ref<'conclusion' | 'heat' | 'evidence'>('conclusion')
let radar: echarts.ECharts | null = null

const score = computed(() => clamp(overview.value?.score))
const mastery = computed(() => clamp(overview.value?.mastery))
const accuracy = computed(() => clamp(overview.value?.accuracy))
const engagement = computed(() => clamp(overview.value?.engagement))
const isBusy = computed(() => loading.value || refreshing.value || evaluating.value || evolving.value)
const evidenceTotal = computed(() => {
  const evidence = overview.value?.evidence || {}
  const direct = safeNumber(evidence.total)
  if (direct > 0) return direct
  return ['exercise_attempts', 'knowledge_nodes', 'resource_items', 'feedback_items', 'learning_events']
    .reduce((sum, key) => sum + safeNumber(evidence[key]), 0)
})
const hasEvidence = computed(() => evidenceTotal.value > 0)
const scoreTone = computed(() => {
  if (!hasEvidence.value) return '证据不足'
  if (score.value >= 80) return '表现优秀'
  if (score.value >= 65) return '稳定提升'
  if (score.value >= 50) return '需要强化'
  return '优先干预'
})

const dimensions = computed(() => (overview.value?.dimensions || []).map((item) => ({
  label: String(item.label || '未命名维度'),
  value: clamp(item.value),
})))

const evidenceCards = computed(() => {
  const evidence = overview.value?.evidence || {}
  return [
    { key: 'exercise_attempts', label: '练习作答', value: safeNumber(evidence.exercise_attempts), icon: ClipboardCheck, detail: '已提交的有效作答记录' },
    { key: 'knowledge_nodes', label: '知识节点', value: safeNumber(evidence.knowledge_nodes), icon: BrainCircuit, detail: '存在掌握度记录的节点' },
    { key: 'resource_items', label: '资源成果', value: safeNumber(evidence.resource_items), icon: Database, detail: '已进入资源库存的成果' },
    { key: 'feedback_items', label: '资源反馈', value: safeNumber(evidence.feedback_items), icon: Activity, detail: '可用于策略判断的行为' },
    { key: 'learning_events', label: '学习事件', value: safeNumber(evidence.learning_events), icon: History, detail: '画像、路径、辅导与评估事件' },
  ]
})

const reportSummary = computed(() => String(
  latestReport.value?.summary
  || latestReport.value?.conclusion
  || latestReport.value?.notes
  || '',
))
const reportFindings = computed(() => toTextList(
  latestReport.value?.findings
  || latestReport.value?.recommendations
  || latestReport.value?.next_actions,
))
const evolutionUpdates = computed(() => Object.entries(evolutionResult.value?.profile_updates || {}).map(([key, value]) => ({ key, value: String(value ?? '') })))
const evaluationModeLabel = computed(() => latestReport.value?.analysis_mode === 'llm' ? '大模型综合分析' : '本地证据规则分析')
const diagnosisItems = computed(() => {
  if (activeDiagnosisTab.value === 'heat') {
    return [...dimensions.value]
      .sort((a, b) => a.value - b.value)
      .slice(0, 5)
      .map((item) => ({ title: item.label, detail: `当前证据计算值 ${item.value}%`, severity: item.value < 60 ? '高' : '中' }))
  }
  if (activeDiagnosisTab.value === 'evidence') {
    return evidenceCards.value
      .filter((item) => item.value > 0)
      .map((item) => ({ title: item.label, detail: `${item.detail}：${item.value} 条`, severity: '证据' }))
  }
  return (overview.value?.weak_points || []).slice(0, 5).map((item) => ({
    title: item,
    detail: reportFindings.value.find((finding) => finding.includes(item)) || '来自错题标签、知识节点或画像证据',
    severity: '关注',
  }))
})
const radarDescription = computed(() => dimensions.value.length
  ? `能力雷达：${dimensions.value.map((item) => `${item.label} ${item.value} 分`).join('，')}`
  : '暂无可绘制的评估维度')

async function loadEvaluation(options: { background?: boolean } = {}) {
  const background = Boolean(options.background && overview.value)
  if (background) refreshing.value = true
  else loading.value = true
  error.value = ''
  try {
    const data = await getEvaluationOverview(studentId.value)
    overview.value = data
    if (!evaluating.value) latestReport.value = data.latest_report || null
    await nextTick()
    renderRadar()
  } catch (reason: any) {
    error.value = reason?.message || '评估证据加载失败'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

async function runEvaluation() {
  if (isBusy.value) return
  evaluating.value = true
  error.value = ''
  notice.value = ''
  evolutionResult.value = null
  try {
    const result = await generateEvaluation(studentId.value)
    latestReport.value = result?.report || result || null
    await loadEvaluation({ background: true })
    notice.value = '最新评估报告已由后端生成；评估事件已进入证据时间线。'
  } catch (reason: any) {
    error.value = reason?.message || '评估报告生成失败'
  } finally {
    evaluating.value = false
  }
}

async function evolveStrategy() {
  if (!overview.value || isBusy.value) return
  evolving.value = true
  error.value = ''
  notice.value = ''
  try {
    evolutionResult.value = await evolveLearningStrategy(studentId.value, {
      score: score.value,
      topic: overview.value.weak_points?.[0] || '当前课程',
      weak_points: overview.value.weak_points || [],
      action: score.value < 60 ? 'negative' : 'review',
      evidence: overview.value.evidence || {},
    })
    notice.value = evolutionResult.value?.evolved
      ? '后端已写入新的画像快照，后续资源和路径将读取新版本。'
      : evolutionResult.value?.reason || '当前证据未达到画像进化阈值，系统保持原策略并继续观察。'
    await loadEvaluation({ background: true })
  } catch (reason: any) {
    error.value = reason?.message || '策略进化失败'
  } finally {
    evolving.value = false
  }
}

function startReinforcement() {
  void router.push({ path: '/profile', query: { round: String(Date.now()), source: 'evaluate' } })
}

function showEvidence() {
  activeDiagnosisTab.value = 'evidence'
  void nextTick(() => diagnosisEl.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
}

function renderRadar() {
  radar?.dispose()
  radar = null
  if (!radarEl.value || !dimensions.value.length) return
  radar = echarts.init(radarEl.value)
  radar.setOption({
    animationDuration: 520,
    tooltip: { trigger: 'item', formatter: '{b}<br/>{c}' },
    radar: {
      radius: '66%',
      center: ['50%', '52%'],
      splitNumber: 4,
      indicator: dimensions.value.map((item) => ({ name: item.label, max: 100 })),
      axisName: { color: '#61728a', fontSize: 10, fontWeight: 600 },
      splitArea: { areaStyle: { color: ['#fbfdff', '#f1f6ff'] } },
      splitLine: { lineStyle: { color: '#dbe6f4' } },
      axisLine: { lineStyle: { color: '#cbdbea' } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: dimensions.value.map((item) => item.value),
        name: '当前能力',
        areaStyle: { color: 'rgba(23,105,255,.2)' },
        lineStyle: { color: '#1769ff', width: 2.5 },
        itemStyle: { color: '#00aeea', borderColor: '#fff', borderWidth: 2 },
        symbolSize: 6,
      }],
    }],
  })
}

function safeNumber(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? Math.max(0, number) : 0
}

function clamp(value: unknown) {
  return Math.max(0, Math.min(100, safeNumber(value)))
}

function toTextList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => typeof item === 'string' ? item : JSON.stringify(item)).filter(Boolean)
  if (typeof value === 'string' && value.trim()) return [value.trim()]
  return []
}

function safeRoute(route: unknown) {
  const value = String(route || '')
  return /^\/(profile|workshop|exercise|knowledge|path|tutor|multimodal|evaluate)$/.test(value) ? value : '/path'
}

function formatTime(value: string) {
  if (!value) return '已记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

function timelineTone(value: string) {
  const allowed = ['primary', 'amber', 'cyan', 'indigo', 'evolution', 'green', 'neutral']
  return allowed.includes(value) ? `tone-${value}` : 'tone-neutral'
}

function handleResize() { radar?.resize() }

onMounted(() => {
  void loadEvaluation()
  window.addEventListener('resize', handleResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  radar?.dispose()
})
</script>

<template>
  <div class="competition-page evaluate-command-page">
    <section class="shot-evaluate" aria-label="学习效果评估与策略进化">
      <header class="shot-evaluate__head"><div><span><Activity :size="15" /> LEARNING INTELLIGENCE</span><h1>学习效果评估与策略进化</h1><p>融合画像、知识掌握、练习表现与资源反馈，形成可解释、可执行、可追踪的学习优化闭环。</p></div><div class="shot-actions"><em><Check :size="13" />本地证据已同步</em><button type="button" :disabled="isBusy" @click="loadEvaluation({ background: true })"><RefreshCw :size="16" />刷新证据</button><button class="is-primary" type="button" :disabled="isBusy" @click="runEvaluation"><LoaderCircle v-if="evaluating" class="spin" :size="16" /><WandSparkles v-else :size="16" />{{ evaluating ? '评估生成中' : '生成智能评估' }}</button></div></header>
      <div v-if="error" class="shot-notice is-error"><CircleAlert :size="18" />{{ error }}<button type="button" @click="loadEvaluation()">重新加载</button></div><div v-if="notice" class="shot-notice"><Check :size="18" />{{ notice }}</div>
      <div v-if="loading && !overview" class="shot-loading"><span class="os-spinner"></span><p>正在汇总学习证据与能力维度……</p></div>
      <template v-else-if="overview">
        <main class="shot-evaluate-main">
          <section class="shot-score-row">
            <article class="shot-score"><header><CircleDot :size="14" />综合学习指数 <Info :size="14" /></header><div class="shot-score-ring" :style="{ '--score-angle': `${score * 3.6}deg` }"><span><strong>{{ Math.round(score) }}</strong><small>/ 100</small></span></div><h2>{{ scoreTone }}</h2><p>读取 {{ evidenceTotal }} 条本地证据<br>{{ latestReport ? evaluationModeLabel : '尚未生成分析报告' }}</p><div><span v-for="item in overview.weak_points.slice(0, 2)" :key="item"><TriangleAlert :size="13" />{{ item }}</span></div><footer><button type="button" @click="showEvidence"><ClipboardCheck :size="14" />查看证据</button><button type="button" @click="startReinforcement"><TrendingUp :size="14" />启动补强</button></footer></article>
            <article class="shot-capability"><header><strong><BrainCircuit class="shot-panel-icon" :size="17" />多维能力画像</strong><small>所有数值均由现有证据计算</small></header><div class="shot-capability__body"><div ref="radarEl" class="shot-evaluate-radar" role="img" :aria-label="radarDescription"></div><ul><li v-for="item in dimensions.slice(0,4)" :key="item.label"><span>{{ item.label }}</span><i><b :style="{ width: `${item.value}%` }"></b></i><strong>{{ item.value }}</strong></li></ul></div></article>
            <article class="shot-evidence-version"><header><strong><ShieldCheck class="shot-panel-icon is-green" :size="17" />评估证据版本</strong><small>所有结论均可追溯</small></header><div v-for="item in evidenceCards.slice(0,3)" :key="item.key"><component :is="item.icon" :size="23" /><span><strong>{{ item.value }}</strong><small>{{ item.label }}</small></span></div><footer><strong>评估可信度：{{ overview.confidence?.label || '暂无证据' }}</strong><small>当前累计 {{ evidenceTotal }} 条可追溯证据。</small></footer></article>
          </section>

          <section class="shot-diagnosis-row"><article ref="diagnosisEl" class="shot-diagnosis"><nav><button type="button" :class="{ active: activeDiagnosisTab === 'conclusion' }" @click="activeDiagnosisTab = 'conclusion'">诊断结论</button><button type="button" :class="{ active: activeDiagnosisTab === 'heat' }" @click="activeDiagnosisTab = 'heat'">薄弱点热区</button><button type="button" :class="{ active: activeDiagnosisTab === 'evidence' }" @click="activeDiagnosisTab = 'evidence'">证据明细</button></nav><h3>{{ activeDiagnosisTab === 'evidence' ? '证据来源' : '关键问题' }}</h3><ol><li v-for="(item,index) in diagnosisItems" :key="`${item.title}-${index}`"><i>{{ index+1 }}</i><span><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></span><em>{{ item.severity }}</em></li><li v-if="!diagnosisItems.length"><span><strong>暂无可分析内容</strong><small>请先完成练习、知识学习或资源反馈。</small></span></li></ol></article>
            <article class="shot-action-plan"><header><strong><ClipboardCheck class="shot-panel-icon" :size="17" />闭环行动计划</strong></header><ul><li v-for="(item,index) in overview.suggestions.slice(0,4)" :key="`${item.title}-${index}`"><i>{{ index+1 }}</i><span><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></span><em>待执行</em></li><li v-if="!overview.suggestions.length"><span>当前证据不足，暂不生成行动计划。</span></li></ul></article></section>

          <section class="shot-eval-timeline"><header><strong><History class="shot-panel-icon" :size="17" />闭环进化时间线</strong></header><div><article v-for="(item,index) in overview.timeline.slice(0,5)" :key="item.id || index" :class="{ active: index === 2 }"><i><component :is="[Database,BrainCircuit,Target,Gauge,TrendingUp][index]" :size="22" /></i><strong>{{ ['采集证据','生成评估','定位问题','调整策略','追踪反馈'][index] }}</strong><small>{{ item.detail || item.title }}</small><time>{{ formatTime(item.created_at) }}</time></article></div></section>
        </main>

        <aside class="shot-engine"><header><h2>策略进化引擎</h2><span>ADAPTIVE ENGINE</span><em>证据规则 + 可选 LLM</em></header><ul><li v-for="item in evidenceCards" :key="item.key"><component :is="item.icon" :size="24" /><span><strong>{{ item.label }}</strong><small>{{ item.detail }}：{{ item.value }}</small></span></li></ul><section><h3>关联知识点</h3><div><span v-for="item in overview.weak_points.slice(0,3)" :key="item">{{ item }}</span><span v-if="!overview.weak_points.length">暂无</span></div><h3>后端判定结果</h3><dl v-if="evolutionUpdates.length"><div v-for="item in evolutionUpdates" :key="item.key"><dt>{{ item.key }}</dt><dd>{{ item.value }}</dd></div></dl><p v-else>{{ evolutionResult?.reason || '点击下方按钮后，后端会依据当前证据判定是否需要写入新画像快照。' }}</p></section><button type="button" :disabled="isBusy || !hasEvidence" @click="evolveStrategy"><LoaderCircle v-if="evolving" class="spin" :size="16" /><GitCompareArrows v-else :size="16" />{{ evolving ? '进化判定中' : '提交进化判定' }}</button></aside>
      </template>
    </section>

    <template v-if="false">
    <header class="os-page-header">
      <div class="os-page-title">
        <span class="os-eyebrow"><ChartNoAxesCombined :size="15" /> EVIDENCE & EVOLUTION</span>
        <h1>学习效果评估</h1>
        <p>汇总画像、知识、练习、资源与反馈证据，形成可解释的能力判断；只有达到后端进化阈值时，系统才会写入新的画像策略。</p>
      </div>
      <div class="os-page-actions">
        <button class="os-button" type="button" :disabled="isBusy" @click="loadEvaluation({ background: true })"><LoaderCircle v-if="refreshing" class="spin" :size="15" /><RefreshCw v-else :size="15" />{{ refreshing ? '同步中' : '刷新证据' }}</button>
        <button class="os-button os-button-primary" type="button" :disabled="isBusy" @click="runEvaluation"><LoaderCircle v-if="evaluating" class="spin" :size="15" /><WandSparkles v-else :size="15" />{{ evaluating ? '评估生成中' : '生成最新评估' }}</button>
      </div>
    </header>

    <LearningLoopContext
      class="evaluation-loop-context"
      stage="08"
      stage-label="效果评估"
      task="汇总证据并判断下一轮学习策略"
      input="全流程行为、掌握度、练习与反馈证据"
      process="评估智能体分析，进化引擎独立判定"
      :output="overview ? `${score} 分 · ${evidenceTotal} 条证据` : '等待证据汇总'"
      next-to="/profile"
      next-label="新一轮画像"
      status="评估结果回流下一轮学习闭环"
    />

    <div v-if="error" class="os-alert evaluation-alert" role="alert" aria-live="assertive"><CircleAlert :size="18" /><span><strong>当前操作未完成</strong><small>{{ error }}</small></span><button class="os-button" type="button" :disabled="isBusy" @click="loadEvaluation()"><RefreshCw :size="14" />重新加载</button></div>
    <div v-if="notice" class="evaluation-notice" role="status" aria-live="polite"><Check :size="16" />{{ notice }}</div>

    <section v-if="loading && !overview" class="os-card os-loading" role="status" aria-live="polite"><div><span class="os-spinner"></span><p>正在汇总学习证据与能力维度……</p></div></section>

    <section v-else-if="overview" class="evaluation-workbench" aria-label="学习效果分析工作台">
      <header class="evaluation-hero" aria-labelledby="evaluation-score-title">
        <div class="score-panel">
          <div class="score-orbit" :style="{ '--score-angle': `${score * 3.6}deg` }"><span><strong>{{ Math.round(score) }}</strong><em>/ 100</em></span></div>
          <div><span class="os-eyebrow">OVERALL SCORE</span><h2 id="evaluation-score-title">{{ scoreTone }}</h2><p>{{ hasEvidence ? `本轮共汇总 ${evidenceTotal} 条可计数证据` : '证据不足，当前分数仅作为基线参考' }}</p></div>
        </div>
        <div class="summary-metrics">
          <article><BrainCircuit :size="16" /><span><small>知识掌握</small><strong>{{ mastery.toFixed(1) }}%</strong></span></article>
          <article><Target :size="16" /><span><small>练习正确率</small><strong>{{ accuracy.toFixed(1) }}%</strong></span></article>
          <article><Activity :size="16" /><span><small>学习投入</small><strong>{{ engagement.toFixed(1) }}%</strong></span></article>
          <article><Database :size="16" /><span><small>有效证据</small><strong>{{ evidenceTotal }} <em>条</em></strong></span></article>
        </div>
        <div class="hero-actions">
          <span><ShieldCheck :size="17" /><small>评估与进化独立执行</small></span>
          <button type="button" :disabled="isBusy" @click="evolveStrategy"><LoaderCircle v-if="evolving" class="spin" :size="15" /><GitCompareArrows v-else :size="15" />{{ evolving ? '进化判定中' : '判断是否进化' }}</button>
        </div>
      </header>

      <div class="evaluation-workspace-grid">
        <article class="radar-card" aria-labelledby="radar-title">
          <header class="panel-heading"><div><span class="os-eyebrow"><Gauge :size="14" /> CAPABILITY RADAR</span><h2 id="radar-title">能力维度</h2></div><span class="cp-status">{{ dimensions.length }} 维</span></header>
          <div v-if="dimensions.length" ref="radarEl" class="radar-chart" role="img" :aria-label="radarDescription"></div>
          <div v-else class="cp-empty-state compact"><span><Gauge :size="24" /></span><h3>暂无能力维度</h3><p>完成练习或生成评估后再刷新查看。</p></div>
          <ul class="dimension-list" aria-label="能力维度数值列表"><li v-for="item in dimensions" :key="item.label"><span>{{ item.label }}</span><span class="os-progress"><i :style="{ width: `${item.value}%` }"></i></span><strong>{{ item.value.toFixed(1) }}</strong></li></ul>
        </article>

        <div class="diagnosis-column">
          <article class="diagnostic-card" aria-labelledby="diagnostic-title">
            <header class="panel-heading"><div><span class="os-eyebrow"><CircleAlert :size="14" /> PRIORITY SIGNALS</span><h2 id="diagnostic-title">优先补强</h2></div><span class="cp-status">{{ overview.weak_points.length }} 项</span></header>
            <ol v-if="overview.weak_points.length" class="weakness-list"><li v-for="(item, index) in overview.weak_points" :key="`${item}-${index}`"><span>{{ String(index + 1).padStart(2, '0') }}</span><span><strong>{{ item }}</strong><small>先确认概念边界，再用练习或案例形成证据。</small></span><RouterLink to="/workshop">生成资源 <ArrowRight :size="12" /></RouterLink></li></ol>
            <div v-else class="cp-empty-state compact"><span><Check :size="23" /></span><h3>暂无明确薄弱点</h3><p>继续积累练习与知识节点证据。</p></div>
            <div class="diagnostic-conclusion"><Lightbulb :size="17" /><span><small>证据解释</small><strong>{{ hasEvidence ? `当前判断基于 ${evidenceTotal} 条可计数证据。` : '当前没有可计数证据，不应视为真实掌握。' }}</strong></span></div>
          </article>

          <article class="report-result" aria-labelledby="report-title">
            <header><span class="os-eyebrow"><ChartNoAxesCombined :size="14" /> LATEST REPORT</span><span v-if="latestReport?.generated_at">{{ formatTime(latestReport.generated_at) }}</span></header>
            <template v-if="latestReport"><h2 id="report-title">后端评估报告</h2><p>{{ reportSummary || '后端已返回结构化评估数据，但没有提供摘要字段。' }}</p><ul v-if="reportFindings.length"><li v-for="(item, index) in reportFindings" :key="`${item}-${index}`"><span>{{ index + 1 }}</span>{{ item }}</li></ul></template>
            <div v-else class="report-empty"><ClipboardCheck :size="22" /><span><strong id="report-title">还没有本轮详细报告</strong><small>点击“生成最新评估”形成结构化结论。</small></span></div>
          </article>
        </div>

        <aside class="decision-column">
          <section class="evidence-ledger" aria-labelledby="evidence-title">
            <header class="panel-heading"><div><span class="os-eyebrow"><Database :size="14" /> EVIDENCE LEDGER</span><h2 id="evidence-title">证据来源</h2></div><strong>{{ evidenceTotal }}</strong></header>
            <div class="evidence-metric-grid" aria-label="证据来源统计"><article v-for="item in evidenceCards" :key="item.key"><component :is="item.icon" :size="16" /><span><small>{{ item.label }}</small><strong>{{ item.value }} <em>条</em></strong></span></article></div>
          </section>

          <article class="evolution-result" :class="{ 'is-evolved': evolutionResult?.evolved }">
            <header><span><GitCompareArrows :size="17" /></span><div><small>EVOLUTION DECISION</small><h2 v-if="evolutionResult">{{ evolutionResult.evolved ? '已写入新画像策略' : '保持当前画像策略' }}</h2><h2 v-else>等待进化判定</h2></div></header>
            <template v-if="evolutionResult"><p>{{ evolutionResult.reason || '后端未提供本轮判定理由。' }}</p><div v-if="evolutionResult.recommended_action" class="recommended-action"><Target :size="15" /><span><small>建议动作</small><strong>{{ evolutionResult.recommended_action }}</strong></span></div><dl v-if="evolutionUpdates.length"><div v-for="item in evolutionUpdates" :key="item.key"><dt>{{ item.key }}</dt><dd>{{ item.value }}</dd></div></dl><small class="decision-mode">判定模式：{{ evolutionResult.mode || '未说明' }}</small></template>
            <p v-else>进化引擎会根据证据阈值决定是否写入新画像策略。</p>
          </article>

          <section class="suggestion-card" aria-labelledby="suggestion-title">
            <header class="panel-heading"><div><span class="os-eyebrow"><TrendingUp :size="14" /> NEXT ACTION</span><h2 id="suggestion-title">下一步行动</h2></div></header>
            <div v-if="overview.suggestions.length" class="suggestion-grid"><RouterLink v-for="(item, index) in overview.suggestions" :key="`${item.title}-${index}`" :to="safeRoute(item.route)"><span>{{ String(index + 1).padStart(2, '0') }}</span><span><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></span><ArrowRight :size="14" /></RouterLink></div>
            <div v-else class="cp-empty-state compact"><span><Target :size="22" /></span><h3>暂无行动建议</h3><p>生成最新评估后再次查看。</p></div>
          </section>
        </aside>
      </div>

      <section class="evidence-timeline" aria-labelledby="timeline-title">
        <header class="panel-heading"><div><span class="os-eyebrow"><History :size="14" /> EVIDENCE TIMELINE</span><h2 id="timeline-title">学习证据时间线</h2></div><span class="cp-status">{{ overview.timeline.length }} 条事件</span></header>
        <div v-if="overview.timeline.length" class="timeline-track" role="list"><article v-for="item in overview.timeline" :key="item.id || `${item.type}-${item.created_at}`" role="listitem"><span class="timeline-dot" :class="timelineTone(item.tone)"></span><span><small>{{ item.type || 'learning_event' }}</small><strong>{{ item.title }}</strong><p>{{ item.detail }}</p><time>{{ formatTime(item.created_at) }}</time></span><i></i></article></div>
        <div v-else class="timeline-empty"><History :size="18" />还没有学习事件，完成画像、资源、练习或答疑后会在此累积。</div>
      </section>

      <footer class="evaluation-next"><Sparkles :size="18" /><div><strong>闭环完成，回到画像开启下一轮</strong><small>新快照将在资源工坊与学习路径的下次加载中生效。</small></div><RouterLink class="os-button os-button-primary" to="/profile">查看新一轮画像 <ArrowRight :size="15" /></RouterLink></footer>
    </section>

    <section v-else class="os-card cp-empty-state"><span><ChartNoAxesCombined :size="25" /></span><h3>评估数据暂不可用</h3><p>请重新加载，或先完成一次诊断练习以积累证据。</p><button class="os-button os-button-primary" type="button" @click="loadEvaluation()"><RefreshCw :size="14" />重新加载</button></section>
    </template>
  </div>
</template>

<style scoped>
.evaluate-command-page { display: grid; gap: 17px; }
.evaluation-alert { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px; padding: 13px 15px; }.evaluation-alert > span { display: grid; gap: 2px; }.evaluation-alert small { color: var(--cp-muted); }.evaluation-notice { display: flex; align-items: center; gap: 9px; padding: 12px 15px; color: #0f579f; border: 1px solid rgba(23,105,255,.18); border-radius: 13px; background: #edf5ff; font-size: 12px; font-weight: 720; }
.evaluation-hero { display: grid; grid-template-columns: minmax(360px,1.05fr) minmax(430px,1.2fr) minmax(210px,.58fr); min-height: 186px; overflow: hidden; border-radius: 19px; }.score-panel { display: grid; grid-template-columns: 126px 1fr; align-items: center; gap: 18px; padding: 24px 27px; }.score-orbit { display: grid; place-items: center; width: 122px; height: 122px; border-radius: 50%; background: conic-gradient(#45ceff var(--score-angle),rgba(117,165,214,.16) 0); }.score-orbit::before { grid-area: 1/1; width: 94px; height: 94px; border-radius: 50%; background: #102b4c; content: ''; }.score-orbit span { z-index: 1; grid-area: 1/1; display: grid; place-items: center; }.score-orbit strong { color: #fff; font-size: 37px; line-height: 1; }.score-orbit em { color: #7fb6e8; font-size: 10px; font-style: normal; }.score-panel > div:last-child { display: grid; gap: 6px; }.score-panel .os-eyebrow,.report-result .os-eyebrow { color: #75ceff; }.score-panel h2 { margin: 0; color: #f4f9ff; font-size: 25px; letter-spacing: -.04em; }.score-panel p { margin: 0; color: #91a9c3; font-size: 10px; line-height: 1.6; }
.summary-metrics { display: grid; grid-template-columns: 1fr 1fr; border-left: 1px solid rgba(122,165,211,.17); }.summary-metrics article { display: grid; grid-template-columns: 34px 1fr; align-items: center; gap: 10px; padding: 17px; border-right: 1px solid rgba(122,165,211,.12); border-bottom: 1px solid rgba(122,165,211,.12); }.summary-metrics article:nth-child(n+3) { border-bottom: 0; }.summary-metrics article > span { display: grid; place-items: center; width: 34px; height: 34px; color: #55ceff; border-radius: 10px; background: rgba(37,102,158,.35); }.summary-metrics article > div { display: grid; grid-template-columns: auto auto; align-items: baseline; justify-content: start; gap: 3px; }.summary-metrics small { grid-column: span 2; color: #7f9ab6; font-size: 10px; }.summary-metrics strong { color: #ecf6ff; font-size: 15px; }.summary-metrics em { color: #7f9ab6; font-size: 10px; font-style: normal; }
.hero-actions { display: grid; align-content: center; gap: 13px; padding: 22px; border-left: 1px solid rgba(122,165,211,.17); background: rgba(8,31,58,.55); }.hero-actions > div { display: flex; align-items: flex-start; gap: 9px; color: #57cdff; }.hero-actions > div span { display: grid; gap: 4px; }.hero-actions small { color: #7896b6; font-size: 10px; }.hero-actions strong { color: #dcefff; font-size: 10px; line-height: 1.45; }.hero-actions button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 42px; color: #fff; border: 1px solid rgba(84,197,255,.28); border-radius: 11px; background: rgba(16,105,166,.55); font-size: 10px; font-weight: 760; cursor: pointer; }.hero-actions button:hover:not(:disabled) { background: rgba(21,123,190,.68); }.hero-actions button:disabled { opacity: .55; cursor: not-allowed; }
.evidence-metric-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 11px; }.evidence-metric-grid article { display: grid; grid-template-columns: 39px 1fr; align-items: center; gap: 11px; min-height: 91px; padding: 15px; }.evidence-metric-grid article > span:first-child { display: grid; place-items: center; width: 39px; height: 39px; color: var(--cp-blue); border-radius: 12px; background: var(--cp-blue-soft); }.evidence-metric-grid article > span:last-child { display: grid; grid-template-columns: auto auto; justify-content: start; align-items: baseline; column-gap: 4px; }.evidence-metric-grid small { grid-column: span 2; color: var(--cp-muted); font-size: 10px; }.evidence-metric-grid strong { font-size: 20px; }.evidence-metric-grid em { color: var(--cp-muted); font-size: 10px; font-style: normal; }.evidence-metric-grid p { grid-column: span 2; margin: 2px 0 0; color: #8292a6; font-size: 10px; }
.evaluation-layout { display: grid; grid-template-columns: minmax(0,1.15fr) minmax(360px,.85fr); gap: 14px; }.radar-card,.diagnostic-card,.suggestion-card,.evidence-timeline { padding: 21px; }.panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 15px; padding-bottom: 14px; border-bottom: 1px solid var(--cp-line); }.panel-heading > div { display: grid; gap: 4px; }.panel-heading h2 { margin: 0; font-size: 16px; }.panel-heading p { margin: 0; color: var(--cp-muted); font-size: 10px; }.radar-chart { width: 100%; height: 300px; }.dimension-list { display: grid; grid-template-columns: 1fr 1fr; gap: 7px 17px; margin: 0; padding: 14px 0 0; border-top: 1px solid var(--cp-line); list-style: none; }.dimension-list li { display: grid; grid-template-columns: 70px 1fr 30px; align-items: center; gap: 8px; }.dimension-list li > span:first-child { color: var(--cp-muted); font-size: 10px; }.dimension-list .os-progress { height: 5px; overflow: hidden; border-radius: 99px; }.dimension-list .os-progress i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg,var(--cp-blue),var(--cp-cyan)); }.dimension-list strong { font-size: 10px; text-align: right; }
.weakness-list { display: grid; margin: 8px 0 0; padding: 0; list-style: none; }.weakness-list li { display: grid; grid-template-columns: 29px 1fr auto; align-items: center; gap: 10px; padding: 12px 0; border-bottom: 1px solid var(--cp-line); }.weakness-list li > span:first-child { display: grid; place-items: center; width: 28px; height: 28px; color: #aa6b13; border-radius: 8px; background: #fff4df; font-size: 10px; font-weight: 800; }.weakness-list li > span:nth-child(2) { display: grid; gap: 3px; }.weakness-list strong { font-size: 10px; }.weakness-list small { color: var(--cp-muted); font-size: 10px; line-height: 1.45; }.weakness-list a { display: inline-flex; align-items: center; gap: 4px; color: var(--cp-blue); font-size: 10px; text-decoration: none; }.diagnostic-conclusion { display: flex; align-items: flex-start; gap: 9px; margin-top: 14px; padding: 12px; color: var(--cp-blue); border-radius: 11px; background: #eef5ff; }.diagnostic-conclusion span { display: grid; gap: 3px; }.diagnostic-conclusion small { color: #66809e; font-size: 10px; }.diagnostic-conclusion strong { color: #274e78; font-size: 10px; line-height: 1.5; }.compact { min-height: 165px !important; }
.result-layout { display: grid; grid-template-columns: 1.15fr .85fr; gap: 14px; }.report-result,.evolution-result { padding: 22px; border-radius: 18px; }.report-result > header { display: flex; align-items: center; justify-content: space-between; color: #819dbb; font-size: 10px; }.report-result h2 { margin: 17px 0 7px; color: #f3f8ff; font-size: 22px; }.report-result > p { margin: 0; color: #9cb1c8; font-size: 10px; line-height: 1.65; }.report-result ul { display: grid; gap: 7px; margin: 15px 0 0; padding: 0; list-style: none; }.report-result li { display: grid; grid-template-columns: 26px 1fr; align-items: start; gap: 8px; padding: 9px; color: #afc2d7; border-radius: 9px; background: rgba(24,65,105,.43); font-size: 10px; line-height: 1.5; }.report-result li span { display: grid; place-items: center; width: 24px; height: 24px; color: #65ccff; border-radius: 7px; background: rgba(16,103,161,.43); }.report-result footer { display: flex; align-items: center; gap: 6px; margin-top: 13px; color: #7694b3; font-size: 10px; }
.evolution-result { border: 1px solid var(--cp-line); background: #fff; }.evolution-result.is-evolved { border-color: rgba(23,105,255,.3); background: linear-gradient(145deg,#fff,#f1f7ff); }.evolution-result > header { display: flex; align-items: center; gap: 10px; }.evolution-result header > span { display: grid; place-items: center; width: 40px; height: 40px; color: var(--cp-blue); border-radius: 12px; background: var(--cp-blue-soft); }.evolution-result header > div { display: grid; gap: 3px; }.evolution-result header small { color: var(--cp-blue); font-size: 10px; letter-spacing: .08em; }.evolution-result h2 { margin: 0; font-size: 17px; }.evolution-result > p { margin: 15px 0 0; color: var(--cp-muted); font-size: 10px; line-height: 1.65; }.recommended-action { display: flex; gap: 8px; margin-top: 13px; padding: 11px; color: var(--cp-blue); border-radius: 10px; background: #eef5ff; }.recommended-action span { display: grid; gap: 3px; }.recommended-action small { color: #66809e; font-size: 10px; }.recommended-action strong { color: #274e78; font-size: 10px; }.evolution-result dl { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; margin: 13px 0 0; }.evolution-result dl div { padding: 8px; border: 1px solid var(--cp-line); border-radius: 8px; }.evolution-result dt { color: var(--cp-blue); font-size: 10px; }.evolution-result dd { margin: 4px 0 0; color: var(--cp-muted); font-size: 10px; line-height: 1.4; }.decision-mode { display: block; margin-top: 11px; color: #8b9aae; font-size: 10px; }
.suggestion-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 9px; margin-top: 15px; }.suggestion-grid a { display: grid; grid-template-columns: 31px 1fr auto; align-items: center; gap: 9px; min-height: 78px; padding: 11px; color: var(--cp-text); border: 1px solid var(--cp-line); border-radius: 11px; background: #fbfdff; text-decoration: none; }.suggestion-grid a:hover { border-color: rgba(23,105,255,.36); background: #f2f7ff; }.suggestion-grid a > span:first-child { display: grid; place-items: center; width: 30px; height: 30px; color: var(--cp-blue); border-radius: 9px; background: var(--cp-blue-soft); font-size: 10px; font-weight: 800; }.suggestion-grid a > span:nth-child(2) { display: grid; gap: 4px; }.suggestion-grid strong { font-size: 10px; }.suggestion-grid small { color: var(--cp-muted); font-size: 10px; line-height: 1.45; }
.timeline-track { display: flex; margin-top: 20px; overflow-x: auto; padding: 2px 0 8px; }.timeline-track article { position: relative; display: grid; grid-template-columns: 28px minmax(125px,1fr); gap: 8px; min-width: 200px; padding-right: 20px; }.timeline-dot { position: relative; z-index: 2; width: 25px; height: 25px; border: 6px solid #fff; border-radius: 50%; background: #8292a6; box-shadow: 0 0 0 1px #cbd8e7; box-sizing: border-box; }.timeline-dot.tone-primary,.timeline-dot.tone-green { background: var(--cp-blue); }.timeline-dot.tone-cyan { background: var(--cp-cyan); }.timeline-dot.tone-indigo { background: #6a6bd6; }.timeline-dot.tone-amber { background: #e89a24; }.timeline-dot.tone-evolution { background: #9a64db; }.timeline-track article > span:nth-child(2) { display: grid; align-content: start; gap: 3px; }.timeline-track small { color: var(--cp-blue); font-size: 10px; }.timeline-track strong { font-size: 10px; }.timeline-track p { display: -webkit-box; overflow: hidden; margin: 0; color: var(--cp-muted); font-size: 10px; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }.timeline-track time { color: #8c9aab; font-size: 10px; }.timeline-track article > i { position: absolute; top: 12px; left: 25px; width: calc(100% - 7px); height: 1px; background: #d8e2ee; }
.evaluation-next { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 13px; padding: 16px 18px; border: 1px solid var(--cp-line); border-radius: 15px; }.evaluation-next > span { display: grid; place-items: center; width: 40px; height: 40px; color: var(--cp-blue); border-radius: 11px; background: var(--cp-blue-soft); }.evaluation-next > div { display: grid; gap: 3px; }.evaluation-next strong { font-size: 11px; }.evaluation-next small { color: var(--cp-muted); font-size: 10px; }
.spin { animation: evaluation-spin .8s linear infinite; } @keyframes evaluation-spin { to { transform: rotate(360deg); } }
@media (max-width: 1150px) { .evaluation-hero { grid-template-columns: 1fr 1fr; }.hero-actions { grid-column: span 2; grid-template-columns: 1fr auto; align-items: center; border-top: 1px solid rgba(122,165,211,.17); border-left: 0; }.evaluation-layout { grid-template-columns: 1fr; }.result-layout { grid-template-columns: 1fr; } }
@media (max-width: 820px) { .evaluation-hero { grid-template-columns: 1fr; }.summary-metrics { border-top: 1px solid rgba(122,165,211,.17); border-left: 0; }.hero-actions { grid-column: auto; }.evidence-metric-grid { grid-template-columns: 1fr 1fr; }.suggestion-grid { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .evaluation-alert { grid-template-columns: auto 1fr; }.evaluation-alert .os-button { grid-column: span 2; }.score-panel { grid-template-columns: 108px 1fr; padding: 21px; }.score-orbit { width: 104px; height: 104px; }.score-orbit::before { width: 80px; height: 80px; }.score-orbit strong { font-size: 31px; }.hero-actions { grid-template-columns: 1fr; }.evidence-metric-grid { grid-template-columns: 1fr; }.dimension-list { grid-template-columns: 1fr; }.weakness-list li { grid-template-columns: 29px 1fr; }.weakness-list a { grid-column: 2; }.suggestion-card,.evidence-timeline,.radar-card,.diagnostic-card { padding: 17px; }.panel-heading { align-items: flex-start; flex-direction: column; }.evolution-result dl { grid-template-columns: 1fr; }.evaluation-next { grid-template-columns: auto 1fr; }.evaluation-next .os-button { grid-column: span 2; } }
@media (max-width: 400px) { .score-panel { grid-template-columns: 1fr; justify-items: center; text-align: center; }.summary-metrics { grid-template-columns: 1fr; }.summary-metrics article { border-right: 0; }.summary-metrics article:nth-child(n+3) { border-bottom: 1px solid rgba(122,165,211,.12); }.summary-metrics article:last-child { border-bottom: 0; }.evaluation-next { grid-template-columns: 1fr; }.evaluation-next > span { display: none; }.evaluation-next .os-button { grid-column: auto; } }

/* Continuous evaluation workbench ----------------------------------------- */
.evaluate-command-page { gap: 12px; }
.evaluation-loop-context { margin: 0; }
.evaluation-workbench {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto auto;
  min-height: 740px;
  height: min(860px, calc(100vh - 145px));
  overflow: hidden;
  border: 1px solid #dce6f2;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 18px 48px rgba(36, 74, 120, .08);
}
.evaluation-workbench .evaluation-hero {
  display: grid;
  grid-template-columns: minmax(300px, .9fr) minmax(480px, 1.35fr) 218px;
  min-height: 132px;
  overflow: visible;
  color: #142a43;
  border: 0;
  border-bottom: 1px solid #dce6f2;
  border-radius: 0;
  background: linear-gradient(105deg, #f7fbff 0%, #fff 68%);
  box-shadow: none;
}
.evaluation-workbench .score-panel { grid-template-columns: 92px 1fr; gap: 14px; padding: 17px 21px; }
.evaluation-workbench .score-orbit { width: 88px; height: 88px; background: conic-gradient(#1769ff var(--score-angle), #e1eaf5 0); }
.evaluation-workbench .score-orbit::before { width: 68px; height: 68px; background: #fff; }
.evaluation-workbench .score-orbit strong { color: #1769ff; font-size: 28px; }
.evaluation-workbench .score-orbit em { color: #8497ab; }
.evaluation-workbench .score-panel .os-eyebrow { color: var(--cp-blue); }
.evaluation-workbench .score-panel h2 { color: #162e49; font-size: 22px; }
.evaluation-workbench .score-panel p { color: #72869d; font-size: 10px; }
.evaluation-workbench .summary-metrics { display: grid; grid-template-columns: repeat(4, 1fr); border-left: 1px solid #dce6f2; }
.evaluation-workbench .summary-metrics article,
.evaluation-workbench .summary-metrics article:nth-child(n+3) { display: grid; grid-template-columns: auto 1fr; align-content: center; gap: 7px; min-width: 0; padding: 16px 12px; color: #1769ff; border-right: 1px solid #e1e8f1; border-bottom: 0; }
.evaluation-workbench .summary-metrics article > span { display: grid; gap: 4px; min-width: 0; }
.evaluation-workbench .summary-metrics small { grid-column: auto; color: #7c8fa5; font-size: 9px; }
.evaluation-workbench .summary-metrics strong { color: #1b334d; font-size: 15px; }
.evaluation-workbench .summary-metrics em { color: #7c8fa5; font-size: 9px; }
.evaluation-workbench .hero-actions { display: grid; align-content: center; gap: 11px; padding: 17px; border-left: 0; background: #f5f8fc; }
.evaluation-workbench .hero-actions > span { display: flex; align-items: center; gap: 7px; color: #1769ff; }
.evaluation-workbench .hero-actions small { color: #657b93; font-size: 9px; }
.evaluation-workbench .hero-actions button { min-height: 39px; color: #fff; border: 0; border-radius: 7px; background: #1769ff; }
.evaluation-workspace-grid { display: grid; grid-template-columns: minmax(360px, 1.08fr) minmax(340px, .92fr) minmax(300px, .78fr); min-height: 0; }
.radar-card,
.diagnosis-column,
.decision-column { min-width: 0; min-height: 0; }
.evaluation-workbench .panel-heading { min-height: 59px; padding: 11px 15px; border-bottom: 1px solid #dce6f2; }
.evaluation-workbench .panel-heading h2 { font-size: 14px; }
.evaluation-workbench .panel-heading p { display: none; }
.radar-card { display: grid; grid-template-rows: auto minmax(230px, 1fr) auto; overflow: hidden; border-right: 1px solid #dce6f2; }
.evaluation-workbench .radar-chart { width: 100%; height: 100%; min-height: 230px; }
.evaluation-workbench .dimension-list { grid-template-columns: 1fr 1fr; gap: 7px 15px; max-height: 145px; overflow-y: auto; margin: 0; padding: 12px 16px 14px; border-top: 1px solid #dce6f2; }
.evaluation-workbench .dimension-list li { grid-template-columns: 68px 1fr 28px; }
.evaluation-workbench .dimension-list li > span:first-child,
.evaluation-workbench .dimension-list strong { font-size: 9px; }
.diagnosis-column { display: grid; grid-template-rows: minmax(240px, 1.05fr) minmax(210px, .95fr); overflow: hidden; border-right: 1px solid #dce6f2; }
.diagnostic-card { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; min-height: 0; overflow: hidden; }
.evaluation-workbench .weakness-list { overflow-y: auto; margin: 0; padding: 0 15px; }
.evaluation-workbench .weakness-list li { grid-template-columns: 26px 1fr auto; gap: 8px; padding: 10px 0; }
.evaluation-workbench .weakness-list li > span:first-child { width: 25px; height: 25px; border-radius: 5px; }
.evaluation-workbench .weakness-list strong,
.evaluation-workbench .weakness-list small,
.evaluation-workbench .weakness-list a { font-size: 9px; }
.evaluation-workbench .diagnostic-conclusion { margin: 0; padding: 9px 14px; border-top: 1px solid #dce6f2; border-radius: 0; background: #f3f7fc; }
.evaluation-workbench .diagnostic-conclusion strong { font-size: 9px; }
.report-result { overflow-y: auto; padding: 15px 17px; color: #dcecff; border-top: 1px solid #dce6f2; border-radius: 0; background: linear-gradient(145deg, #102b4c, #14395f); }
.evaluation-workbench .report-result > header { display: flex; align-items: center; justify-content: space-between; color: #88a4c2; font-size: 9px; }
.evaluation-workbench .report-result h2 { margin: 10px 0 5px; color: #f3f8ff; font-size: 16px; }
.evaluation-workbench .report-result > p { margin: 0; color: #a7bad0; font-size: 9px; line-height: 1.55; }
.evaluation-workbench .report-result ul { display: grid; gap: 0; margin: 10px 0 0; padding: 0; list-style: none; }
.evaluation-workbench .report-result li { display: grid; grid-template-columns: 21px 1fr; gap: 7px; padding: 7px 0; color: #b8cade; border-top: 1px solid rgba(153, 188, 224, .15); border-radius: 0; background: transparent; font-size: 9px; }
.evaluation-workbench .report-result li span { display: grid; place-items: center; width: 19px; height: 19px; color: #65ccff; border-radius: 4px; background: rgba(16, 103, 161, .43); }
.report-empty { display: flex; align-items: center; gap: 10px; min-height: 112px; color: #65ccff; }
.report-empty span { display: grid; gap: 4px; }
.report-empty strong { color: #ecf6ff; font-size: 11px; }
.report-empty small { color: #90a9c3; font-size: 9px; }
.decision-column { display: grid; grid-template-rows: auto auto minmax(0, 1fr); overflow-y: auto; background: #fbfcfe; }
.evidence-ledger { border-bottom: 1px solid #dce6f2; }
.evidence-ledger .panel-heading > strong { color: #1769ff; font-size: 23px; }
.evaluation-workbench .evidence-metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
.evaluation-workbench .evidence-metric-grid article { display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 8px; min-height: 57px; padding: 10px 13px; color: #1769ff; border-right: 1px solid #e1e8f1; border-bottom: 1px solid #e1e8f1; }
.evaluation-workbench .evidence-metric-grid article:nth-child(2n) { border-right: 0; }
.evaluation-workbench .evidence-metric-grid article > span { display: grid; gap: 2px; }
.evaluation-workbench .evidence-metric-grid small { color: #788ba1; font-size: 9px; }
.evaluation-workbench .evidence-metric-grid strong { color: #203850; font-size: 13px; }
.evaluation-workbench .evidence-metric-grid em { color: #8496a9; font-size: 9px; font-style: normal; }
.evaluation-workbench .evolution-result { padding: 13px 15px; border: 0; border-bottom: 1px solid #dce6f2; border-radius: 0; background: #fff; }
.evaluation-workbench .evolution-result.is-evolved { border-color: #dce6f2; background: #f2f7ff; }
.evaluation-workbench .evolution-result > header { gap: 8px; }
.evaluation-workbench .evolution-result header > span { width: 31px; height: 31px; border-radius: 7px; }
.evaluation-workbench .evolution-result h2 { font-size: 13px; }
.evaluation-workbench .evolution-result > p { margin-top: 9px; font-size: 9px; }
.evaluation-workbench .recommended-action { margin-top: 8px; padding: 8px; border-radius: 6px; }
.evaluation-workbench .evolution-result dl { grid-template-columns: 1fr; gap: 0; margin-top: 8px; }
.evaluation-workbench .evolution-result dl div { padding: 6px 0; border: 0; border-top: 1px solid #e1e8f1; border-radius: 0; }
.evaluation-workbench .decision-mode { margin-top: 7px; }
.evaluation-workbench .suggestion-card { min-height: 0; overflow: hidden; padding: 0; }
.evaluation-workbench .suggestion-grid { display: grid; grid-template-columns: 1fr; gap: 0; margin: 0; overflow-y: auto; }
.evaluation-workbench .suggestion-grid a { grid-template-columns: 27px 1fr auto; min-height: 62px; padding: 9px 13px; border: 0; border-bottom: 1px solid #e1e8f1; border-radius: 0; background: transparent; }
.evaluation-workbench .suggestion-grid a:hover { background: #eef5ff; }
.evaluation-workbench .suggestion-grid a > span:first-child { width: 26px; height: 26px; border-radius: 5px; }
.evaluation-workbench .suggestion-grid strong,
.evaluation-workbench .suggestion-grid small { font-size: 9px; }
.evaluation-workbench .evidence-timeline { display: grid; grid-template-columns: 176px 1fr; min-height: 102px; max-height: 130px; overflow: hidden; padding: 0; border-top: 1px solid #dce6f2; }
.evaluation-workbench .evidence-timeline .panel-heading { align-items: flex-start; min-height: 0; padding: 13px 15px; border-right: 1px solid #dce6f2; border-bottom: 0; }
.evaluation-workbench .timeline-track { margin: 0; overflow-x: auto; padding: 17px 15px 8px; }
.evaluation-workbench .timeline-track article { min-width: 180px; }
.evaluation-workbench .timeline-track p { -webkit-line-clamp: 1; }
.timeline-empty { display: flex; align-items: center; gap: 8px; padding: 0 18px; color: #7b8da1; font-size: 10px; }
.evaluation-workbench .evaluation-next { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; min-height: 55px; padding: 8px 13px 8px 17px; color: #1769ff; border: 0; border-top: 1px solid #dce6f2; border-radius: 0; background: #f6f9fd; }
.evaluation-workbench .evaluation-next > div { display: grid; gap: 1px; }
.evaluation-workbench .evaluation-next strong { color: #213950; font-size: 10px; }
.evaluation-workbench .evaluation-next small { color: #72859b; font-size: 9px; }

@media (max-width: 1180px) {
  .evaluation-workbench { height: auto; min-height: 0; overflow: visible; }
  .evaluation-workbench .evaluation-hero { grid-template-columns: minmax(300px, .8fr) minmax(450px, 1.2fr); }
  .evaluation-workbench .hero-actions { grid-column: span 2; grid-template-columns: 1fr auto; align-items: center; border-top: 1px solid #dce6f2; }
  .evaluation-workspace-grid { grid-template-columns: minmax(360px, 1fr) minmax(350px, 1fr); }
  .radar-card { min-height: 560px; }
  .diagnosis-column { min-height: 560px; border-right: 0; }
  .decision-column { grid-column: span 2; grid-template-columns: .8fr 1fr 1.2fr; grid-template-rows: auto; overflow: visible; border-top: 1px solid #dce6f2; }
  .evidence-ledger,
  .evaluation-workbench .evolution-result { border-right: 1px solid #dce6f2; border-bottom: 0; }
}
@media (max-width: 780px) {
  .evaluation-loop-context { display: none; }
  .evaluation-workbench .evaluation-hero { grid-template-columns: 1fr; }
  .evaluation-workbench .summary-metrics { border-top: 1px solid #dce6f2; border-left: 0; }
  .evaluation-workbench .hero-actions { grid-column: auto; }
  .evaluation-workspace-grid { grid-template-columns: 1fr; }
  .radar-card,
  .diagnosis-column { min-height: 0; border-right: 0; border-bottom: 1px solid #dce6f2; }
  .evaluation-workbench .radar-chart { height: 300px; }
  .decision-column { grid-column: auto; grid-template-columns: 1fr; }
  .evidence-ledger,
  .evaluation-workbench .evolution-result { border-right: 0; border-bottom: 1px solid #dce6f2; }
  .evaluation-workbench .evidence-timeline { grid-template-columns: 1fr; max-height: none; }
  .evaluation-workbench .evidence-timeline .panel-heading { border-right: 0; border-bottom: 1px solid #dce6f2; }
}
@media (max-width: 520px) {
  .evaluation-workbench { border-right: 0; border-left: 0; border-radius: 0; }
  .evaluation-workbench .score-panel { grid-template-columns: 82px 1fr; text-align: left; }
  .evaluation-workbench .score-orbit { width: 78px; height: 78px; }
  .evaluation-workbench .score-orbit::before { width: 60px; height: 60px; }
  .evaluation-workbench .summary-metrics { grid-template-columns: 1fr 1fr; }
  .evaluation-workbench .summary-metrics article { border-bottom: 1px solid #e1e8f1; }
  .evaluation-workbench .summary-metrics article:nth-child(n+3) { border-bottom: 0; }
  .evaluation-workbench .hero-actions { grid-template-columns: 1fr; }
  .evaluation-workbench .dimension-list { grid-template-columns: 1fr; }
  .evaluation-workbench .weakness-list li { grid-template-columns: 26px 1fr; }
  .evaluation-workbench .weakness-list a { grid-column: 2; }
  .evaluation-workbench .evaluation-next { grid-template-columns: 1fr; padding: 12px; }
  .evaluation-workbench .evaluation-next > svg { display: none; }
}
</style>
