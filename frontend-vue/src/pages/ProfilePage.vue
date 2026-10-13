<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  ArrowRight,
  BadgeCheck,
  Brain,
  Box,
  Check,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  Clock3,
  Database,
  History,
  Heart,
  Image,
  Lightbulb,
  LoaderCircle,
  MessageSquareText,
  Radar,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  TriangleAlert,
  UserRoundSearch,
} from 'lucide-vue-next'
import { getProfileOverview, updateProfile, type ProfileDimension, type ProfileOverview } from '@/api/learningApi'
import { useStudent } from '@/composables/useStudent'
import { localizeProfileOverview } from '@/utils/profileLocalization'

type ConversationMessage = { role: 'user' | 'assistant'; content: string; time: string }

const { studentId, major, goals } = useStudent()
const profile = ref<ProfileOverview | null>(null)
const loading = ref(true)
const refreshing = ref(false)
const updating = ref(false)
const error = ref('')
const statusNotice = ref('')
const showProfileRules = ref(false)
const showAllHistory = ref(false)
const failedDraft = ref('')
const selectedKey = ref('knowledge_base_level')
const inputRef = ref<HTMLTextAreaElement | null>(null)
const input = ref('')
const messages = ref<ConversationMessage[]>([
  {
    role: 'assistant',
    content: '告诉我你正在学习什么、哪里容易卡住，以及你更喜欢怎样的讲解方式。我会把自然语言转成可追踪的六维学习画像。',
    time: '现在',
  },
])

const selectedDimension = computed<ProfileDimension | null>(() =>
  profile.value?.dimensions.find((item) => item.key === selectedKey.value) || profile.value?.dimensions[0] || null,
)

const identifiedCount = computed(() => profile.value?.dimensions.filter((item) => item.status === 'ready').length || 0)

const radarGridLevels = [0.25, 0.5, 0.75, 1]
const radarCurrentValues = computed(() => (profile.value?.dimensions || []).map((dimension) => percentValue(dimension.confidence)))
const radarPreviousValues = computed(() => {
  const previous = profile.value?.comparison?.previous_dimensions || {}
  if (!Object.keys(previous).length) return []
  return (profile.value?.dimensions || []).map((dimension) => percentValue(previous[dimension.key]))
})
const profileTags = computed(() => {
  const learner = profile.value?.learner || {}
  return [learner.major, ...(profile.value?.focus.keywords || []), ...(profile.value?.focus.weak_points || [])]
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .filter((item, index, values) => values.indexOf(item) === index)
    .slice(0, 4)
})
const quickPrompts = computed(() => {
  const learner = profile.value?.learner
  const learnerMajor = major.value.trim() || String(learner?.major || '').trim()
  const learnerGoal = goals.value.trim() || String(learner?.goals || '').trim()
  const context = [
    learnerMajor ? `专业方向是${learnerMajor}` : '',
    learnerGoal ? `学习目标是${learnerGoal}` : '',
  ].filter(Boolean).join('，') || '请结合我的当前用户设置'

  return [
    { label: '描述学习目标', text: `${context}。请结合这些设置分析并更新我的学习目标画像。` },
    { label: '告诉我薄弱点', text: `${context}。请结合当前画像和学习记录，告诉我最需要优先改进的薄弱点。` },
    { label: '我更喜欢图解', text: `${context}，我更喜欢通过图解和具体案例学习。请据此更新我的学习偏好。` },
    { label: '给我安排练习', text: `${context}。请围绕该目标和当前薄弱点，为我安排针对性练习。` },
  ]
})
const profileChanges = computed(() => profile.value?.comparison?.changes || [])

function radarCoordinates(values: number[]) {
  const centerX = 140
  const centerY = 105
  const radius = 78
  return values.map((value, index) => {
    const angle = -Math.PI / 2 + index * Math.PI / 3
    const scale = Math.max(0, Math.min(100, value)) / 100
    return {
      x: Number((centerX + Math.cos(angle) * radius * scale).toFixed(2)),
      y: Number((centerY + Math.sin(angle) * radius * scale).toFixed(2)),
    }
  })
}

function radarPolygon(values: number[]) {
  return radarCoordinates(values).map((point) => `${point.x},${point.y}`).join(' ')
}

const radarAxisPoints = radarCoordinates([100, 100, 100, 100, 100, 100])
const radarCurrentPoints = computed(() => radarCoordinates(radarCurrentValues.value))

async function loadProfile(): Promise<ProfileOverview | null> {
  const isInitialLoad = !profile.value
  if (isInitialLoad) loading.value = true
  else refreshing.value = true
  error.value = ''

  try {
    const nextProfile = localizeProfileOverview(await getProfileOverview(studentId.value))
    profile.value = nextProfile

    if (!nextProfile.dimensions.some((item) => item.key === selectedKey.value)) {
      selectedKey.value = nextProfile.dimensions[0]?.key || selectedKey.value
    }

    major.value = nextProfile.learner.major || major.value
    goals.value = nextProfile.learner.goals || goals.value
    return nextProfile
  } catch (reason: any) {
    error.value = reason?.message || '画像加载失败'
    return null
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

async function submitProfile() {
  const text = input.value.trim()
  if (!text || updating.value) return

  const previousVersion = profile.value?.learner.profile_version || ''
  updating.value = true
  error.value = ''
  statusNotice.value = ''
  failedDraft.value = ''
  messages.value.push({ role: 'user', content: text, time: nowTime() })
  input.value = ''

  try {
    const result = await updateProfile({
      student_id: studentId.value,
      messages: messages.value.map((item) => ({ role: item.role, content: item.content })),
      major: major.value || undefined,
      goals: goals.value || undefined,
    })
    const rationale = result?.rationale || result?.summary || '已完成本轮学习特征分析，结果将作为后续资源生成与路径规划的参考。'
    messages.value.push({ role: 'assistant', content: `本轮分析结果：${rationale}`, time: nowTime() })

    const refreshedProfile = await loadProfile()
    const nextVersion = refreshedProfile?.learner.profile_version || ''
    if (previousVersion && nextVersion && previousVersion !== nextVersion) {
      statusNotice.value = `本轮分析已确认写入画像，版本由 ${previousVersion} 更新为 ${nextVersion}。`
    } else if (refreshedProfile) {
      statusNotice.value = '本轮分析已完成；当前未检测到画像版本变化，持久化结果请以版本记录与最新证据为准。'
    } else {
      statusNotice.value = '本轮分析已返回，但最新画像快照刷新失败；分析内容已保留，可稍后重新加载确认。'
    }
  } catch (reason: any) {
    error.value = reason?.message || '本轮画像分析失败'
    failedDraft.value = text
    input.value = text
    messages.value.push({ role: 'assistant', content: `本轮分析未完成：${error.value}。原输入已恢复，可以直接重试。`, time: nowTime() })
    await nextTick()
    inputRef.value?.focus()
  } finally {
    updating.value = false
  }
}

function retryLastAction() {
  if (failedDraft.value && input.value.trim()) {
    void submitProfile()
    return
  }
  void loadProfile()
}

function usePrompt(text: string) {
  input.value = text
  failedDraft.value = ''
  statusNotice.value = ''
  void nextTick(() => inputRef.value?.focus())
}

function handleComposerKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault()
    void submitProfile()
  }
}

function nowTime() {
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date())
}

function percentValue(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0
}

function formatDate(value: string) {
  if (!value) return '尚未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

function exportProfile() {
  if (!profile.value) return
  const blob = new Blob([JSON.stringify(profile.value, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${studentId.value || 'learner'}-profile.json`
  anchor.click()
  URL.revokeObjectURL(url)
  statusNotice.value = '当前画像快照已导出为 JSON 文件。'
}

onMounted(loadProfile)
</script>

<template>
  <div class="competition-page profile-command-page">
    <section class="shot-profile" aria-label="用户画像中枢">
      <header class="shot-profile__head">
        <div><div class="shot-title-row"><h1>用户画像中枢</h1><span><BadgeCheck :size="14" />实时画像</span></div><p>基于多模态学习行为与对话的动态学生画像，助力个性化教学与精准资源推荐</p></div>
        <div class="shot-actions">
          <button class="is-primary" type="button" :disabled="loading || refreshing" @click="loadProfile"><LoaderCircle v-if="refreshing" class="spin" :size="17" /><RefreshCw v-else :size="17" />{{ refreshing ? '更新中' : '更新画像' }}</button>
          <button type="button" :disabled="!profile" @click="exportProfile"><Database :size="17" />导出画像</button>
          <button type="button" :aria-expanded="showProfileRules" @click="showProfileRules = !showProfileRules"><History :size="17" />查看画像规则</button>
        </div>
      </header>

      <div v-if="error" class="shot-notice is-error"><CircleAlert :size="18" />{{ error }}<button type="button" @click="retryLastAction">重试</button></div>
      <div v-if="statusNotice" class="shot-notice"><Check :size="18" />{{ statusNotice }}</div>
      <div v-if="showProfileRules" class="shot-rule"><strong>画像更新规则</strong><span>画像对话、练习诊断、知识掌握和资源反馈共同生成版本化快照；新增证据不会直接覆盖已验证判断。</span></div>

      <div v-if="loading && !profile" class="shot-loading"><span class="os-spinner"></span><p>正在读取画像与学习证据……</p></div>
      <template v-else-if="profile">
        <div class="shot-profile__top">
          <article class="shot-identity">
            <div class="shot-avatar"><span class="shot-avatar-photo" role="img" aria-label="用户头像"></span><i></i></div>
            <div class="shot-identity__copy"><h2>{{ profile.learner.display_name || '未设置姓名' }} <small><BadgeCheck :size="15" /></small></h2><p>ID: {{ profile.learner.student_id }}</p>
              <dl><div><dt>专业</dt><dd>{{ profile.learner.major || '未记录' }}</dd></div><div><dt>当前课程</dt><dd>{{ profile.learner.current_course || '未记录' }}</dd></div><div><dt>学习阶段</dt><dd>{{ profile.learner.grade || '未记录' }}</dd></div></dl>
              <strong>学习目标：{{ profile.learner.goals || '尚未采集学习目标' }}</strong>
            </div>
            <div class="shot-tags"><small>画像标签</small><div><span v-for="tag in profileTags" :key="tag">{{ tag }}</span><span v-if="!profileTags.length">等待分析</span></div><em>易混淆：{{ profile.focus.weak_points[0] || '暂无有效证据' }}</em></div>
          </article>

          <article class="shot-timeline"><header><strong><History class="shot-panel-icon" :size="17" />画像更新时间线</strong><button type="button" :disabled="profile.history.length <= 3" :aria-expanded="showAllHistory" @click="showAllHistory = !showAllHistory">{{ showAllHistory ? '收起' : '查看更多' }}</button></header>
            <ol><li v-for="(item, index) in (showAllHistory ? profile.history : profile.history.slice(0, 3))" :key="item.id"><i :class="`tone-${index}`"></i><time>{{ formatDate(item.created_at) }}</time><span>{{ item.reason }}</span></li><li v-if="!profile.history.length"><span>尚未生成画像快照</span></li></ol>
          </article>
        </div>

        <div class="shot-profile__middle">
          <article class="shot-interview"><header><strong><MessageSquareText class="shot-panel-icon" :size="17" />画像采集对话</strong><button type="button" :disabled="messages.length <= 1" @click="messages = messages.slice(0, 1)">清空对话</button></header>
            <p class="shot-ai-tip"><Brain :size="17" />请用自然语言描述你的专业、课程章节、学习目标、薄弱点和偏好的资源形式。系统会把这些信息转为动态用户画像。</p>
            <form @submit.prevent="submitProfile"><textarea ref="inputRef" v-model="input" rows="4" placeholder="描述你的专业、目标、薄弱点和学习偏好" @keydown="handleComposerKeydown"></textarea><footer><small>{{ input.length }}/1000</small><button type="submit" :disabled="!input.trim() || updating"><LoaderCircle v-if="updating" class="spin" :size="16" /><Send v-else :size="16" />{{ updating ? '分析中' : '分析并更新' }}</button></footer></form>
            <div class="shot-prompts"><small>快速示例：</small><button v-for="prompt in quickPrompts" :key="prompt.label" type="button" @click="usePrompt(prompt.text)">{{ prompt.label }}</button></div>
          </article>

          <article class="shot-matrix"><header><strong><Brain class="shot-panel-icon is-violet" :size="17" />画像维度矩阵</strong><span>{{ identifiedCount }}/{{ profile.dimensions.length }} 维度已识别</span></header>
            <div class="shot-dimensions"><button v-for="(dimension, index) in profile.dimensions" :key="dimension.key" type="button" :class="[`tone-${index}`, { active: selectedDimension?.key === dimension.key }]" @click="selectedKey = dimension.key"><i><component :is="[Box, Lightbulb, TriangleAlert, Image, Clock3, Heart][index]" :size="22" /></i><span><strong>{{ dimension.label }}</strong><small>{{ dimension.value }}</small></span></button></div>
          </article>
        </div>

        <div class="shot-profile__bottom">
          <article class="shot-radar">
            <header><strong><Radar class="shot-panel-icon" :size="17" />学习特征雷达图</strong><span title="展示六个画像维度的当前值、上次值与同龄平均值">?</span></header>
            <div class="shot-radar__plot">
              <label>知识基础</label><label>认知风格</label><label>易错模式</label><label>模态偏好</label><label>学习节奏</label><label>动机类型</label>
              <svg viewBox="0 0 280 210" role="img" aria-label="六维学习特征雷达图">
                <g class="shot-radar__grid">
                  <polygon v-for="level in radarGridLevels" :key="level" :points="radarPolygon(Array(6).fill(level * 100))" />
                </g>
                <g class="shot-radar__axes">
                  <line v-for="(point, index) in radarAxisPoints" :key="index" x1="140" y1="105" :x2="point.x" :y2="point.y" />
                </g>
                <g class="shot-radar__series">
                  <polygon v-if="radarPreviousValues.length" class="is-previous" :points="radarPolygon(radarPreviousValues)" />
                  <polygon class="is-current" :points="radarPolygon(radarCurrentValues)" />
                </g>
                <g class="shot-radar__points">
                  <circle v-for="(point, index) in radarCurrentPoints" :key="index" :cx="point.x" :cy="point.y" r="2.6" />
                </g>
              </svg>
            </div>
            <footer><i></i>当前画像　<template v-if="radarPreviousValues.length"><em></em>上次画像</template></footer>
          </article>
          <article class="shot-explain"><header><strong><Lightbulb class="shot-panel-icon is-green" :size="17" />画像更新解释</strong></header><p>基于本轮对话内容，系统对画像进行了以下识别与更新：</p><ul><li v-for="dimension in profile.dimensions.slice(0, 5)" :key="dimension.key"><span><Check :size="12" /></span><strong>{{ dimension.label }}：</strong>{{ dimension.description }}</li></ul></article>
          <article class="shot-change"><header><strong><TrendingUp class="shot-panel-icon is-violet" :size="17" />本轮变化</strong><span class="shot-change-legend"><i></i>来自最近两个快照</span></header><ul><li v-for="change in profileChanges.slice(0, 5)" :key="change.key"><strong>{{ change.label }}</strong><em>{{ change.before ? '调整' : '新增' }}</em><span>{{ change.before || '未识别' }} → {{ change.after || '未识别' }}</span></li><li v-if="!profileChanges.length"><span>暂无可比较的画像变化</span></li></ul></article>
          <article class="shot-recommend"><header><strong><Sparkles class="shot-panel-icon" :size="17" />推荐动作</strong></header><RouterLink to="/workshop"><i class="shot-action-icon"><Box :size="17" /></i><span>资源推荐<small>为你优先推荐图解与案例类学习资源</small></span><ArrowRight :size="18" /></RouterLink><RouterLink to="/path"><i class="shot-action-icon"><Target :size="17" /></i><span>学习路径<small>生成需求分析与建模专项提升路径</small></span><ArrowRight :size="18" /></RouterLink><RouterLink to="/exercise"><i class="shot-action-icon"><ClipboardCheck :size="17" /></i><span>练习诊断<small>安排用例图与需求访谈对比练习</small></span><ArrowRight :size="18" /></RouterLink><RouterLink class="shot-recommend-all" to="/workshop">查看全部推荐 <ArrowRight :size="15" /></RouterLink></article>
        </div>
        <footer class="shot-profile-footer"><ShieldCheck :size="14" />慧思智学平台 · AI赋能教育，精准成就每一位学习者</footer>
      </template>
    </section>

    <template v-if="false">
    <header class="profile-topbar">
      <div class="profile-heading">
      <span class="os-eyebrow"><UserRoundSearch :size="14" /> 动态画像 · 画像证据台</span>
        <div><h1>用户画像中枢</h1><p>汇集学习描述、练习行为与版本证据，持续维护可执行的六维学习画像。</p></div>
      </div>
      <div class="os-page-actions">
        <button class="os-button" type="button" :disabled="loading || refreshing" @click="loadProfile">
          <LoaderCircle v-if="refreshing" class="spin" :size="15" /><RefreshCw v-else :size="15" />{{ refreshing ? '正在同步' : '更新画像' }}
        </button>
        <button class="os-button" type="button" :disabled="!profile" @click="exportProfile"><Database :size="15" />导出画像</button>
        <button class="os-button" type="button" :aria-expanded="showProfileRules" @click="showProfileRules = !showProfileRules"><History :size="15" />查看画像规则</button>
      </div>
    </header>

    <section v-if="showProfileRules" class="profile-rule-strip" aria-label="画像更新规则">
      <strong>画像更新规则</strong><span>对话补充、练习诊断、知识掌握与资源反馈共同形成版本化画像；新增证据不会直接覆盖已有可靠判断。</span>
      <RouterLink to="/workshop">用画像生成资源 <ArrowRight :size="14" /></RouterLink>
    </section>

    <nav class="profile-flowbar" aria-label="画像工作流">
      <span class="flow-step is-current"><b>01</b><i><strong>采集证据</strong><small>描述、错题与偏好</small></i></span>
      <span class="flow-step"><b>02</b><i><strong>形成画像</strong><small>{{ profile ? `${percentValue(profile.completeness)}% 完整度` : '等待画像数据' }}</small></i></span>
      <span class="flow-step"><b>03</b><i><strong>校准六维</strong><small>{{ profile ? `${identifiedCount} / 6 已识别` : '等待分析' }}</small></i></span>
      <RouterLink class="flow-step flow-next" to="/workshop"><b>04</b><i><strong>驱动资源</strong><small>进入资源工坊</small></i><ArrowRight :size="15" /></RouterLink>
    </nav>

    <div v-if="error" class="os-alert profile-alert" role="alert" aria-live="assertive">
      <CircleAlert :size="18" aria-hidden="true" /><span><strong>当前操作未完成</strong><small>{{ error }}</small></span>
      <button class="os-button" type="button" :disabled="loading || refreshing || updating" @click="retryLastAction"><RotateCcw :size="14" />{{ failedDraft ? '重试本轮分析' : '重新加载' }}</button>
    </div>
    <div v-if="statusNotice" class="profile-notice" role="status" aria-live="polite"><Check :size="16" aria-hidden="true" />{{ statusNotice }}</div>

    <section v-if="loading && !profile" class="os-card os-loading" role="status" aria-live="polite">
      <div><span class="os-spinner"></span><p>正在读取画像快照与学习证据…</p></div>
    </section>

    <template v-else-if="profile">
      <section class="profile-console">
        <article class="profile-dialogue os-card" aria-labelledby="profile-interview-title">
          <header class="panel-heading">
              <div><span class="panel-index">01</span><span><small>证据输入</small><h2 id="profile-interview-title">补充画像证据</h2></span></div>
            <span class="cp-status"><span class="profile-live-dot"></span>{{ updating ? '分析中' : '智能体就绪' }}</span>
          </header>

          <p class="panel-intro">用自然语言描述学习变化，系统会将本轮输入写入可追踪画像。</p>
          <div class="dialogue-prompts" aria-label="画像补充提示">
            <button type="button" @click="usePrompt('我最近在哪些知识点上反复出错？请根据已有记录更新画像。')">根据错题分析</button>
            <button type="button" @click="usePrompt('我更适合图解、案例和分步讲解，请把这些偏好写入画像。')">补充学习偏好</button>
            <button type="button" @click="usePrompt('我的目标是完成一份真实项目成果，请据此调整学习节奏与动机类型。')">补充学习目标</button>
          </div>

          <form class="dialogue-composer" @submit.prevent="submitProfile">
            <label for="profile-evidence-input">本轮补充说明</label>
            <textarea id="profile-evidence-input" ref="inputRef" v-model="input" placeholder="描述课程、目标、薄弱点、偏好或最近的学习变化…" rows="4" @keydown="handleComposerKeydown"></textarea>
            <footer><span>Ctrl / ⌘ + Enter 快速分析</span><button class="os-button os-button-primary dialogue-send" type="submit" :disabled="!input.trim() || updating"><LoaderCircle v-if="updating" class="spin" :size="15" /><Send v-else :size="15" />{{ updating ? '正在分析' : '分析并更新' }}</button></footer>
          </form>

          <section class="dialogue-history" aria-label="画像分析对话">
            <header><span><MessageSquareText :size="14" />分析记录</span><small>{{ messages.length }} 条消息</small></header>
            <div class="dialogue-messages" aria-live="polite" aria-relevant="additions">
              <div v-for="(message, index) in messages" :key="`${message.time}-${index}`" class="dialogue-message" :class="`is-${message.role}`">
                <span class="message-role">{{ message.role === 'assistant' ? 'AI' : '我' }}</span><div><p>{{ message.content }}</p><time>{{ message.time }}</time></div>
              </div>
              <div v-if="updating" class="dialogue-message is-assistant is-thinking"><span class="message-role">AI</span><div><p><LoaderCircle :size="15" class="spin" />正在提取证据并形成分析结果…</p></div></div>
            </div>
          </section>
        </article>

        <div class="profile-results">
          <article class="learner-strip os-card" aria-label="当前学习者画像摘要">
            <div class="learner-label"><span class="panel-index">02</span><small>当前画像</small></div>
            <div class="profile-avatar"><span class="profile-avatar-photo" role="img" aria-label="用户头像"></span><i></i></div>
            <div class="profile-identity-copy"><h2>{{ profile.learner.display_name }}</h2><p>{{ profile.learner.major }} · {{ profile.learner.grade }}</p><small>{{ profile.learner.goals || '尚未补充学习目标' }}</small></div>
            <div class="profile-strip-metric"><span>画像完整度</span><strong>{{ percentValue(profile.completeness) }}<small>%</small></strong><div class="os-progress" role="progressbar" aria-label="画像完整度" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="percentValue(profile.completeness)"><span :style="{ width: `${percentValue(profile.completeness)}%` }"></span></div></div>
            <dl class="profile-meta"><div><dt>有效证据</dt><dd>{{ profile.evidence_count }} 条</dd></div><div><dt>当前版本</dt><dd>{{ profile.learner.profile_version }}</dd></div><div><dt>最近更新</dt><dd>{{ formatDate(profile.learner.updated_at) }}</dd></div></dl>
          </article>

          <article class="dimension-workbench os-card" aria-labelledby="dimension-title">
            <header class="panel-heading dimension-header">
              <div><span class="panel-index">03</span><span><small>六维画像</small><h2 id="dimension-title">六维画像校准</h2></span></div>
              <span class="dimension-summary">{{ identifiedCount }} / 6 已识别 · 点击维度查看依据</span>
            </header>

            <div v-if="profile.dimensions.length" class="dimension-console-body">
              <div class="dimension-rail" role="list" aria-label="画像维度">
                <button v-for="(dimension, index) in profile.dimensions" :key="dimension.key" type="button" class="dimension-row" :class="{ active: selectedDimension?.key === dimension.key }" :aria-pressed="selectedDimension?.key === dimension.key" @click="selectedKey = dimension.key">
                  <span class="dimension-index">0{{ index + 1 }}</span><span class="dimension-copy"><strong>{{ dimension.label }}</strong><small>{{ dimension.value }}</small></span><ChevronRight :size="15" aria-hidden="true" />
                </button>
              </div>

              <section v-if="selectedDimension" class="dimension-detail" aria-live="polite">
                <header><span class="detail-icon"><Brain :size="20" /></span><span><small>当前维度</small><strong>{{ selectedDimension.label }}</strong></span><span class="os-chip os-chip-active"><Check :size="12" />{{ selectedDimension.status === 'ready' ? '已识别' : '待补全' }}</span></header>
                <p class="dimension-value">{{ selectedDimension.value }}</p><p class="dimension-desc">{{ selectedDimension.description }}</p>
                <div class="detail-source"><Database :size="15" /><span><strong>{{ profile.evidence_count }} 条证据参与判断</strong><small>来自画像对话、练习与学习行为记录</small></span></div>
              </section>
            </div>
            <div v-else class="cp-empty-state compact-empty"><span><Brain :size="23" /></span><h3>尚未形成维度判断</h3><p>补充学习目标、薄弱点和偏好后，画像智能体会在这里呈现分析结果。</p></div>
          </article>

          <article class="profile-ledger os-card" aria-label="学习焦点与画像版本">
            <section class="evidence-focus-card">
              <header><span><span class="panel-index">04</span><i><small>学习焦点</small><strong>当前学习焦点</strong></i></span><em>{{ profile.focus.weak_points.length }} 个优先卡点</em></header>
              <h2>{{ profile.focus.headline }}</h2>
              <div v-if="profile.focus.weak_points.length" class="focus-evidence-list"><div v-for="(item, index) in profile.focus.weak_points" :key="item"><span>{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ item }}</strong><small>优先补齐</small></div></div>
              <div v-else class="profile-inline-empty">暂无明确薄弱点，完成一次练习诊断后将自动补充。</div>
              <div v-if="profile.focus.keywords.length" class="os-chip-list"><span v-for="item in profile.focus.keywords" :key="item" class="os-chip"># {{ item }}</span></div>
            </section>

            <section class="profile-history-card">
              <header><span><History :size="15" /><i><small>版本记录</small><strong>画像版本记录</strong></i></span><em>{{ profile.history.length }} 个快照</em></header>
              <div v-if="profile.history.length" class="history-list"><div v-for="(item, index) in profile.history" :key="item.id" class="history-row"><span class="history-dot" :class="{ current: index === 0 }"><Clock3 :size="13" /></span><span><strong>{{ item.version }} <em v-if="index === 0">当前</em></strong><small>{{ item.reason }}</small></span><time :datetime="item.created_at">{{ formatDate(item.created_at) }}</time></div></div>
              <div v-else class="profile-inline-empty">暂无历史快照；画像版本变化后会在这里保留原因与时间。</div>
            </section>
          </article>
        </div>
      </section>

      <section class="profile-next-step os-card-soft"><span class="next-step-icon"><Sparkles :size="19" /></span><span><strong>画像已接入资源生成链路</strong><small>资源类型、讲解方式与内容难度将根据当前薄弱点、目标和模态偏好组织。</small></span><RouterLink class="os-button os-button-primary" to="/workshop">进入资源工坊 <ArrowRight :size="15" /></RouterLink></section>
    </template>

    <section v-else class="os-card cp-empty-state"><span><UserRoundSearch :size="25" /></span><h3>暂时无法读取用户画像</h3><p>保留当前页面即可重试，已有输入不会因为重新加载而丢失。</p><button class="os-button os-button-primary" type="button" @click="loadProfile"><RefreshCw :size="15" />重新加载画像</button></section>
    </template>
  </div>
</template>

<style scoped>
.shot-dimensions button {
  grid-template-rows: 1fr;
  align-items: center;
}

.dimension-row {
  grid-template-columns: 28px minmax(0, 1fr) auto;
}
.profile-command-page { display: grid; gap: 12px; padding-top: 18px; }
.spin { animation: os-spin 700ms linear infinite; }
.profile-topbar { display: flex; align-items: center; justify-content: space-between; gap: 24px; min-height: 58px; padding-bottom: 13px; border-bottom: 1px solid var(--cp-line); }
.profile-heading { display: flex; align-items: center; gap: 22px; min-width: 0; }
.profile-heading > div { display: flex; align-items: baseline; gap: 14px; min-width: 0; }
.profile-heading h1 { margin: 0; color: var(--cp-text); font-size: clamp(24px,2.2vw,32px); line-height: 1.1; letter-spacing: -.045em; }
.profile-heading p { overflow: hidden; margin: 0; color: var(--cp-muted); font-size: 11px; white-space: nowrap; text-overflow: ellipsis; }
.profile-topbar .os-page-actions { display: flex; flex: 0 0 auto; gap: 8px; }
.profile-topbar .os-button { min-height: 38px; }

.profile-flowbar { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); overflow: hidden; border: 1px solid var(--cp-line); border-radius: 13px; background: rgba(255,255,255,.88); box-shadow: var(--cp-shadow-soft); }
.flow-step { position: relative; display: grid; grid-template-columns: 27px minmax(0,1fr) auto; align-items: center; gap: 9px; min-height: 54px; padding: 7px 14px; color: var(--cp-text); text-decoration: none; }
.flow-step:not(:last-child)::after { position: absolute; top: 12px; right: 0; width: 1px; height: 30px; background: var(--cp-line); content: ''; }
.flow-step > b { display: grid; place-items: center; width: 27px; height: 27px; color: var(--cp-muted); border-radius: 8px; background: #edf2f8; font-size: 9px; }
.flow-step > i { display: grid; gap: 2px; min-width: 0; font-style: normal; }.flow-step strong { font-size: 11px; }.flow-step small { overflow: hidden; color: var(--cp-muted); font-size: 9px; white-space: nowrap; text-overflow: ellipsis; }
.flow-step.is-current { color: #fff; background: linear-gradient(120deg,#1769ff,#168ee9); }.flow-step.is-current > b { color: var(--cp-blue); background: #fff; }.flow-step.is-current small { color: #d9ecff; }.flow-step.is-current::after { display: none; }
.flow-next { color: #f4f9ff; background: #102b4e; }.flow-next > b { color: #85cfff; background: rgba(255,255,255,.1); }.flow-next small { color: #9db5d0; }.flow-next:hover { background: #163b68; }

.profile-alert { display: grid; grid-template-columns: auto minmax(0,1fr) auto; align-items: center; }.profile-alert > span { display: grid; gap: 2px; }.profile-alert strong { font-size: 12px; }.profile-alert small { font-size: 10px; }.profile-alert .os-button { min-height: 34px; }
.profile-notice { display: flex; align-items: center; gap: 8px; padding: 9px 13px; color: var(--cp-blue-ink); border: 1px solid rgba(23,105,255,.2); border-radius: 10px; background: var(--cp-blue-soft); font-size: 11px; font-weight: 700; }
.profile-console { display: grid; grid-template-columns: minmax(330px,.68fr) minmax(0,1.65fr); align-items: start; gap: 12px; }
.profile-dialogue { position: sticky; top: 76px; display: grid; gap: 11px; padding: 16px; border-color: rgba(57,104,174,.23); background: linear-gradient(155deg,#fff,#f8fbff); }
.panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }.panel-heading > div,.learner-label { display: flex; align-items: center; gap: 9px; }.panel-heading > div > span:last-child { display: grid; gap: 2px; }.panel-heading small,.learner-label small { color: var(--cp-blue); font-size: 9px; font-weight: 800; letter-spacing: .12em; }.panel-heading h2 { margin: 0; font-size: 16px; letter-spacing: -.02em; }.panel-index { display: grid; place-items: center; width: 29px; height: 29px; color: var(--cp-blue); border: 1px solid rgba(23,105,255,.17); border-radius: 8px; background: var(--cp-blue-soft); font-size: 9px; font-weight: 850; }
.profile-live-dot { width: 6px; height: 6px; border-radius: 50%; background: #11a97b; box-shadow: 0 0 0 4px rgba(17,169,123,.1); }.panel-intro { margin: -3px 0 0; color: var(--cp-muted); font-size: 10px; line-height: 1.55; }
.dialogue-prompts { display: flex; flex-wrap: wrap; gap: 6px; }.dialogue-prompts button { min-height: 29px; padding: 0 9px; color: var(--cp-blue-ink); border: 1px solid rgba(23,105,255,.17); border-radius: 8px; background: #f4f8ff; font-size: 10px; font-weight: 700; cursor: pointer; }.dialogue-prompts button:hover { border-color: rgba(23,105,255,.4); background: var(--cp-blue-soft); }
.dialogue-composer { overflow: hidden; border: 1px solid rgba(23,105,255,.28); border-radius: 12px; background: #fff; box-shadow: 0 7px 18px rgba(31,91,174,.05); }.dialogue-composer:focus-within { border-color: var(--cp-blue); box-shadow: 0 0 0 3px rgba(23,105,255,.09); }.dialogue-composer > label { display: block; padding: 9px 11px 0; color: var(--cp-muted); font-size: 10px; font-weight: 750; }.dialogue-composer textarea { width: 100%; min-height: 96px; padding: 7px 11px; color: var(--cp-text); border: 0; outline: 0; resize: vertical; background: transparent; box-sizing: border-box; font-size: 11px; line-height: 1.6; }.dialogue-composer footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 7px 8px; border-top: 1px solid var(--cp-line); background: #f8fbff; }.dialogue-composer footer > span { color: var(--cp-muted); font-size: 9px; }.dialogue-send { min-height: 33px; }
.dialogue-history { display: grid; gap: 7px; min-height: 0; }.dialogue-history > header { display: flex; align-items: center; justify-content: space-between; color: var(--cp-text); font-size: 11px; font-weight: 800; }.dialogue-history > header > span { display: flex; align-items: center; gap: 6px; }.dialogue-history > header small { color: var(--cp-muted); font-size: 9px; font-weight: 600; }.dialogue-messages { display: flex; flex-direction: column; gap: 8px; max-height: 235px; overflow-y: auto; padding: 9px; border: 1px solid var(--cp-line); border-radius: 11px; background: #f5f8fd; scrollbar-width: thin; }.dialogue-message { display: grid; grid-template-columns: 27px minmax(0,1fr); align-items: start; gap: 7px; }.message-role { display: grid; place-items: center; width: 26px; height: 26px; color: var(--cp-blue); border: 1px solid rgba(23,105,255,.17); border-radius: 7px; background: #fff; font-size: 9px; font-weight: 850; }.dialogue-message > div { max-width: 96%; padding: 8px 9px; border: 1px solid rgba(70,112,170,.14); border-radius: 3px 10px 10px; background: #fff; }.dialogue-message.is-user > div { justify-self: end; border-color: rgba(23,105,255,.18); border-radius: 10px 3px 10px 10px; background: var(--cp-blue-soft); }.dialogue-message p { margin: 0; font-size: 10px; line-height: 1.55; }.dialogue-message time { display: block; margin-top: 3px; color: var(--cp-muted); font-size: 8px; }.is-thinking p { display: flex; align-items: center; gap: 6px; color: var(--cp-blue-ink); }

.profile-results { display: grid; gap: 12px; min-width: 0; }.learner-strip { display: grid; grid-template-columns: auto auto minmax(180px,1fr) minmax(145px,.48fr) minmax(280px,.9fr); align-items: center; gap: 13px; padding: 12px 15px; }.learner-label { display: grid; justify-items: center; gap: 3px; padding-right: 12px; border-right: 1px solid var(--cp-line); }.profile-avatar { position: relative; display: grid; place-items: center; width: 42px; height: 42px; overflow: visible; border-radius: 12px; background: #eaf3ff; }.profile-avatar-photo { display: block; width: 100%; height: 100%; border-radius: inherit; background: url('/assets/learner-avatar-v2.png') center / cover no-repeat; }.profile-avatar i { position: absolute; right: -2px; bottom: -2px; width: 8px; height: 8px; border: 3px solid #fff; border-radius: 50%; background: #14aa7c; }.profile-identity-copy { min-width: 0; }.profile-identity-copy h2 { margin: 0 0 2px; font-size: 15px; }.profile-identity-copy p,.profile-identity-copy > small { display: block; overflow: hidden; margin: 0; color: var(--cp-muted); font-size: 9px; white-space: nowrap; text-overflow: ellipsis; }.profile-identity-copy > small { margin-top: 2px; }.profile-strip-metric { display: grid; grid-template-columns: 1fr auto; align-items: baseline; gap: 4px 8px; padding-left: 13px; border-left: 1px solid var(--cp-line); }.profile-strip-metric > span { color: var(--cp-muted); font-size: 9px; font-weight: 700; }.profile-strip-metric strong { font-size: 21px; }.profile-strip-metric strong small { color: var(--cp-muted); font-size: 9px; }.profile-strip-metric .os-progress { grid-column: span 2; }.profile-meta { display: grid; grid-template-columns: .7fr .8fr 1.4fr; gap: 8px; margin: 0; padding: 9px 11px; border-radius: 10px; background: var(--cp-blue-soft); }.profile-meta div { min-width: 0; }.profile-meta dt { color: var(--cp-muted); font-size: 8px; }.profile-meta dd { overflow: hidden; margin: 2px 0 0; color: var(--cp-blue-ink); font-size: 9px; font-weight: 800; white-space: nowrap; text-overflow: ellipsis; }
.dimension-workbench { padding: 15px; }.dimension-header { padding-bottom: 11px; border-bottom: 1px solid var(--cp-line); }.dimension-summary { color: var(--cp-muted); font-size: 9px; }.dimension-console-body { display: grid; grid-template-columns: minmax(340px,1.1fr) minmax(280px,.9fr); gap: 12px; margin-top: 12px; }.dimension-rail { display: grid; align-content: start; }.dimension-row { display: grid; grid-template-columns: 28px minmax(0,1fr) 62px 35px auto; align-items: center; gap: 8px; width: 100%; min-height: 48px; padding: 6px 8px; color: var(--cp-text); border: 0; border-bottom: 1px solid var(--cp-line); background: transparent; text-align: left; cursor: pointer; }.dimension-row:first-child { border-top: 1px solid var(--cp-line); }.dimension-row:hover,.dimension-row.active { position: relative; z-index: 1; color: var(--cp-blue-ink); border-color: rgba(23,105,255,.25); background: var(--cp-blue-soft); box-shadow: inset 3px 0 0 var(--cp-blue); }.dimension-index { display: grid; place-items: center; width: 26px; height: 26px; color: var(--cp-blue); border-radius: 7px; background: #fff; font-size: 9px; font-weight: 850; }.dimension-copy { display: grid; gap: 2px; min-width: 0; }.dimension-copy strong { font-size: 10px; }.dimension-copy small { overflow: hidden; color: var(--cp-muted); font-size: 9px; white-space: nowrap; text-overflow: ellipsis; }.dimension-row > b { color: var(--cp-blue); font-size: 9px; }.mini-progress { height: 4px; overflow: hidden; border-radius: 99px; background: #dfe8f4; }.mini-progress i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg,var(--cp-blue),var(--cp-cyan)); }
.dimension-detail { display: grid; align-content: start; min-width: 0; padding: 15px; border: 1px solid rgba(23,105,255,.18); border-radius: 12px; background: linear-gradient(145deg,#f4f8ff,#eef6ff); }.dimension-detail > header { display: grid; grid-template-columns: auto minmax(0,1fr) auto; align-items: center; gap: 9px; }.detail-icon { display: grid; place-items: center; width: 37px; height: 37px; color: #fff; border-radius: 10px; background: linear-gradient(145deg,var(--cp-blue),var(--cp-cyan)); }.dimension-detail header > span:nth-child(2) { display: grid; gap: 2px; }.dimension-detail header small { color: var(--cp-muted); font-size: 8px; letter-spacing: .09em; }.dimension-detail header strong { font-size: 13px; }.dimension-value { margin: 18px 0 5px; font-size: 19px; font-weight: 820; line-height: 1.25; }.dimension-desc { margin: 0; color: var(--cp-muted); font-size: 10px; line-height: 1.65; }.confidence-score { display: grid; gap: 8px; margin-top: 18px; padding: 11px; border-radius: 10px; background: rgba(255,255,255,.78); }.confidence-score > span { display: flex; align-items: baseline; justify-content: space-between; }.confidence-score small { color: var(--cp-muted); font-size: 9px; }.confidence-score strong { color: var(--cp-blue); font-size: 18px; }.detail-source { display: flex; align-items: center; gap: 8px; margin-top: 12px; padding-top: 11px; color: var(--cp-blue); border-top: 1px solid rgba(23,105,255,.13); }.detail-source > span { display: grid; gap: 2px; }.detail-source strong { color: var(--cp-text); font-size: 9px; }.detail-source small { color: var(--cp-muted); font-size: 8px; }.compact-empty { min-height: 180px; }
.profile-ledger { display: grid; grid-template-columns: 1fr 1fr; overflow: hidden; }.profile-ledger > section { min-width: 0; padding: 14px 16px; }.profile-ledger > section + section { border-left: 1px solid var(--cp-line); }.profile-ledger section > header { display: flex; align-items: center; justify-content: space-between; gap: 9px; }.profile-ledger section > header > span { display: flex; align-items: center; gap: 8px; color: var(--cp-blue); }.profile-ledger section > header i { display: grid; gap: 2px; font-style: normal; }.profile-ledger section > header small { color: var(--cp-blue); font-size: 8px; font-weight: 800; letter-spacing: .1em; }.profile-ledger section > header strong { color: var(--cp-text); font-size: 11px; }.profile-ledger section > header > em { color: var(--cp-muted); font-size: 9px; font-style: normal; }.evidence-focus-card h2 { margin: 12px 0 7px; font-size: 15px; line-height: 1.35; }.focus-evidence-list { display: grid; }.focus-evidence-list > div { display: grid; grid-template-columns: 25px minmax(0,1fr) auto; align-items: center; gap: 7px; padding: 7px 0; border-top: 1px solid var(--cp-line); }.focus-evidence-list > div > span { color: var(--cp-blue); font-size: 9px; font-weight: 850; }.focus-evidence-list strong { overflow: hidden; font-size: 9px; white-space: nowrap; text-overflow: ellipsis; }.focus-evidence-list small { color: var(--cp-blue-ink); font-size: 8px; }.os-chip-list { margin-top: 8px; }.profile-history-card .history-list { display: grid; max-height: 188px; margin-top: 8px; overflow-y: auto; scrollbar-width: thin; }.history-row { display: grid; grid-template-columns: 27px minmax(0,1fr) auto; align-items: center; gap: 8px; padding: 7px 0; border-top: 1px solid var(--cp-line); }.history-dot { display: grid; place-items: center; width: 25px; height: 25px; color: var(--cp-muted); border-radius: 7px; background: #edf2f9; }.history-dot.current { color: #fff; background: var(--cp-blue); }.history-row > span:nth-child(2) { display: grid; gap: 1px; min-width: 0; }.history-row strong { font-size: 9px; }.history-row strong em { margin-left: 4px; color: var(--cp-blue); font-size: 8px; font-style: normal; }.history-row small,.history-row time { overflow: hidden; color: var(--cp-muted); font-size: 8px; white-space: nowrap; text-overflow: ellipsis; }.profile-inline-empty { margin-top: 10px; padding: 13px; color: var(--cp-muted); border: 1px dashed var(--cp-line-strong); border-radius: 9px; background: #f8fbff; font-size: 9px; line-height: 1.5; }
.profile-next-step { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 11px; padding: 11px 14px; }.next-step-icon { display: grid; place-items: center; width: 35px; height: 35px; color: var(--cp-blue); border-radius: 9px; background: var(--cp-blue-soft); }.profile-next-step > span:nth-child(2) { display: grid; gap: 2px; }.profile-next-step strong { font-size: 10px; }.profile-next-step small { color: var(--cp-muted); font-size: 9px; }.profile-next-step .os-button { min-height: 35px; }

@media (max-width: 1180px) { .profile-heading { align-items: flex-start; flex-direction: column; gap: 3px; }.profile-console { grid-template-columns: 1fr; }.profile-dialogue { position: static; grid-template-columns: minmax(320px,.85fr) minmax(0,1.15fr); }.profile-dialogue > .panel-heading,.profile-dialogue > .panel-intro,.profile-dialogue > .dialogue-prompts { grid-column: span 2; }.dialogue-messages { max-height: 210px; } }
@media (max-width: 900px) { .profile-topbar { align-items: flex-start; }.profile-heading > div { align-items: flex-start; flex-direction: column; gap: 3px; }.profile-flowbar { grid-template-columns: 1fr 1fr; }.flow-step:nth-child(2)::after { display: none; }.learner-strip { grid-template-columns: auto auto minmax(0,1fr) minmax(130px,.45fr); }.profile-meta { grid-column: span 4; }.dimension-console-body,.profile-ledger { grid-template-columns: 1fr; }.profile-ledger > section + section { border-top: 1px solid var(--cp-line); border-left: 0; } }
@media (max-width: 680px) { .profile-command-page { padding-top: 12px; }.profile-topbar { flex-direction: column; }.profile-topbar .os-page-actions { width: 100%; }.profile-topbar .os-page-actions .os-button { flex: 1; }.profile-flowbar { grid-template-columns: 1fr; }.flow-step::after { display: none; }.profile-dialogue { grid-template-columns: 1fr; }.profile-dialogue > .panel-heading,.profile-dialogue > .panel-intro,.profile-dialogue > .dialogue-prompts { grid-column: auto; }.learner-strip { grid-template-columns: auto minmax(0,1fr); }.learner-label { display: none; }.profile-strip-metric { grid-column: span 2; padding: 9px 0 0; border-top: 1px solid var(--cp-line); border-left: 0; }.profile-meta { grid-column: span 2; }.dimension-summary { display: none; }.dimension-row { grid-template-columns: 27px minmax(0,1fr) 35px auto; }.mini-progress { display: none; }.profile-alert { grid-template-columns: auto 1fr; }.profile-alert .os-button { grid-column: span 2; }.profile-next-step { grid-template-columns: auto 1fr; }.profile-next-step .os-button { grid-column: span 2; } }
@media (max-width: 430px) { .profile-heading > .os-eyebrow { display: none; }.dialogue-composer footer { align-items: stretch; flex-direction: column; }.dialogue-send { width: 100%; }.dimension-workbench,.profile-ledger > section,.profile-dialogue { padding: 12px; }.profile-meta { grid-template-columns: 1fr 1fr; }.profile-meta div:last-child { grid-column: span 2; }.history-row { grid-template-columns: 27px minmax(0,1fr); }.history-row time { grid-column: 2; } }
@media (max-width: 900px) {
  .profile-topbar { flex-direction: column; }
  .profile-topbar .os-page-actions { width: 100%; min-width: 0; }
}
</style>
