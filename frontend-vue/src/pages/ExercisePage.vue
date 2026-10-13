<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { apiGet, apiPost } from '@/utils/api'
import { useStudent } from '@/composables/useStudent'

type ExerciseQuestion = {
  id: string
  source: string
  type: string
  stem: string
  options: string[]
  tags: string[]
  answered: boolean
  last_answer?: string | null
  last_correct?: boolean | null
  last_correct_answer?: string | null
  last_analysis?: string | null
}

type NormalizedOption = {
  key: string
  text: string
  raw: string
}

type QuestionStemPart = {
  type: 'text' | 'code'
  content: string
  language?: string
}

const { studentId } = useStudent()
const props = defineProps<{
  questionBankIds?: string[]
  questionLimit?: number
  difficulty?: string
  courseName?: string
  knowledgePoint?: string
  questionTypeCount?: number
  resetSeed?: number
  active?: boolean
}>()
const emit = defineEmits<{
  answered: [payload: any]
  navigate: [target: 'builder' | 'wrongBook' | 'tagGalaxy' | 'diagnosis']
}>()
const loading = ref(false)
const answering = ref(false)
const mode = ref<'training' | 'exam'>('training')
const source = ref('')
const questions = ref<ExerciseQuestion[]>([])
const stats = ref<any | null>(null)
const currentIndex = ref(0)
const selectedAnswer = ref('')
const answerSheet = ref<Record<string, string>>({})
const markedQuestionIds = ref<string[]>([])
const lastResult = ref<any | null>(null)
const error = ref('')
const examFinished = ref(false)
const practicePaused = ref(false)
const practiceElapsedSeconds = ref(0)
const examDurationSeconds = ref(15 * 60)
const remainingSeconds = ref(examDurationSeconds.value)
const showExamStartDialog = ref(false)
const examCountdown = ref(0)
const refreshNonce = ref(0)
let examTimer: number | null = null
let practiceTimer: number | null = null
let countdownTimer: number | null = null
let sessionLoadSequence = 0
const activeQuestionBankKey = computed(() => (props.questionBankIds || []).join(',') || 'default')
const configuredBankCount = computed(() => (props.questionBankIds || []).filter(Boolean).length)
const configuredCourseName = computed(() => String(props.courseName || '').trim() || '待选择课程')
const configuredKnowledgePoint = computed(() => String(props.knowledgePoint || '').trim() || '待设置具体知识点')
const configuredQuestionTypeCount = computed(() => Math.max(0, Number(props.questionTypeCount) || 0))
const activeQuestionLimit = computed(() => Math.max(1, Math.min(50, Number(props.questionLimit) || 12)))
const activeDifficulty = computed(() => String(props.difficulty || 'mixed').toLowerCase())
const storageKey = computed(() => `exercise_session_state:${studentId.value}:${activeQuestionBankKey.value}:${activeQuestionLimit.value}:${activeDifficulty.value}:${props.resetSeed || 0}`)

const current = computed(() => questions.value[currentIndex.value] || null)
const hasQuestions = computed(() => questions.value.length > 0)
const progressText = computed(() => (questions.value.length ? `${currentIndex.value + 1} / ${questions.value.length}` : '0 / 0'))
const currentOptions = computed(() => normalizeDisplayOptions(current.value?.options || []))
const currentStemParts = computed(() => parseQuestionStem(current.value?.stem || ''))
const currentIsMultiple = computed(() => isMultipleQuestion(current.value))
const answeredCount = computed(() => questions.value.filter((q) => q.answered).length)
const examAnsweredCount = computed(() => Object.values(answerSheet.value).filter(Boolean).length)
const completedCount = computed(() => mode.value === 'exam' ? examAnsweredCount.value : answeredCount.value)
const unansweredCount = computed(() => Math.max(0, questions.value.length - completedCount.value))
const markedCount = computed(() => markedQuestionIds.value.length)
const sessionCompleted = computed(() => Boolean(questions.value.length) && questions.value.every((q) => q.answered))
const showStats = computed(() => mode.value === 'exam' ? examFinished.value : sessionCompleted.value)
const showImmediateResult = computed(() => mode.value === 'training' || examFinished.value)
const examInProgress = computed(() => mode.value === 'exam' && questions.value.length > 0 && !examFinished.value)
const sessionPaused = computed(() => mode.value === 'training' && practicePaused.value)
const isCurrentMarked = computed(() => Boolean(current.value && markedQuestionIds.value.includes(current.value.id)))
const responseLocked = computed(() => loading.value || answering.value || sessionPaused.value || examFinished.value || Boolean(current.value?.answered))
const navigationLocked = computed(() => loading.value || answering.value || sessionPaused.value)
const sessionStats = computed(() => {
  const total = questions.value.length
  const correct = questions.value.filter((q) => q.last_correct === true).length
  const wrong = mode.value === 'exam' && examFinished.value
    ? total - correct
    : questions.value.filter((q) => q.last_correct === false).length
  const tagMap: Record<string, { total: number; wrong: number }> = {}
  for (const question of questions.value) {
    const shouldCount = mode.value === 'exam' && examFinished.value ? true : question.answered
    if (!shouldCount) continue
    const isWrong = mode.value === 'exam' && examFinished.value ? question.last_correct !== true : question.last_correct === false
    const primaryTag = question.tags?.[0] || '未分类'
    for (const tag of [primaryTag]) {
      const item = tagMap[tag] || { total: 0, wrong: 0 }
      item.total += 1
      if (isWrong) item.wrong += 1
      tagMap[tag] = item
    }
  }
  const tagStats = Object.entries(tagMap)
    .map(([tag, item]) => ({
      tag,
      total: item.total,
      wrong: item.wrong,
      wrong_rate: item.total ? Math.round((item.wrong * 1000) / item.total) / 10 : 0,
      status: item.wrong > 0 ? 'weak' : 'stable',
    }))
    .sort((a, b) => b.wrong_rate - a.wrong_rate || b.wrong - a.wrong || b.total - a.total)
  return {
    total,
    correct,
    wrong,
    accuracy: total ? Math.round((correct * 1000) / total) / 10 : 0,
    tag_stats: tagStats,
    weak_tags: tagStats.filter((tag) => tag.wrong > 0),
  }
})
function formatTimer(totalSeconds: number) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds || 0))
  const hours = Math.floor(safeSeconds / 3600).toString().padStart(2, '0')
  const minutes = Math.floor((safeSeconds % 3600) / 60).toString().padStart(2, '0')
  const seconds = (safeSeconds % 60).toString().padStart(2, '0')
  return `${hours}:${minutes}:${seconds}`
}

const timerText = computed(() => formatTimer(remainingSeconds.value))
const practiceTimerText = computed(() => formatTimer(practiceElapsedSeconds.value))
const timerPercent = computed(() => {
  if (!examDurationSeconds.value) return 0
  return Math.max(0, Math.min(100, (remainingSeconds.value * 100) / examDurationSeconds.value))
})
const progressPercent = computed(() => {
  if (!questions.value.length) return 0
  return Math.round((completedCount.value * 1000) / questions.value.length) / 10
})
const difficultyLabel = computed(() => {
  const labels: Record<string, string> = {
    mixed: '中等难度',
    easy: '简单难度',
    medium: '中等难度',
    hard: '较高难度',
  }
  return labels[activeDifficulty.value] || props.difficulty || '中等难度'
})
const emptyQuestionTitle = computed(() => configuredBankCount.value ? '题库暂未载入' : '暂无题库')
const emptyQuestionHint = computed(() => configuredBankCount.value ? '点击刷新题目载入已生成题库' : '生成题库后显示题量与难度')
const practiceStatusText = computed(() => {
  if (!hasQuestions.value) return '等待题库'
  if (mode.value === 'exam' && examFinished.value) return '已交卷'
  if (sessionPaused.value) return '已暂停'
  if (mode.value === 'exam') return '进行中'
  return sessionCompleted.value ? '已完成' : '进行中'
})
const modeLabel = computed(() => (mode.value === 'exam' ? '考试诊断' : '即时训练'))
const sourceLabel = computed(() => {
  if (source.value === 'generated_question_bank') return '个性化题库'
  if (source.value === 'no_generated_question_bank') return '尚未生成题库'
  return source.value || '待载入题库'
})
const currentTypeLabel = computed(() => {
  const type = String(current.value?.type || '')
  const labels: Record<string, string> = {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    blank: '填空题',
    short_answer: '简答题',
    case_analysis: '案例分析',
    calculation: '计算题',
    matching: '匹配题',
    ordering: '排序题',
  }
  return labels[type] || type || '题目'
})
const currentPrimaryTag = computed(() => current.value?.tags?.[0] || '综合能力')
const questionStatusText = computed(() => {
  if (!current.value) return '等待载入'
  if (mode.value === 'exam' && !examFinished.value) {
    return answerSheet.value[current.value.id] ? '已暂存' : '待作答'
  }
  if (!current.value.answered) return '待提交'
  return current.value.last_correct ? '已掌握' : '需复盘'
})
const diagnosisInsight = computed(() => {
  if (!questions.value.length) return '刷新题目后开始本轮诊断。'
  if (showStats.value && sessionStats.value.weak_tags.length) {
    return `优先复盘：${sessionStats.value.weak_tags.slice(0, 2).map((tag: any) => tag.tag).join('、')}`
  }
  if (showStats.value) return '本轮表现稳定，可以进入错题本或路径推送。'
  if (mode.value === 'exam') return examFinished.value ? '交卷完成，查看每题解析。' : '考试中仅记录答案，交卷后统一诊断。'
  return '训练模式会即时判题，错误会沉淀到错题本。'
})

function normalizeOptions(options: string[]): NormalizedOption[] {
  const expanded = options.flatMap((option) => splitOptionLine(option))
  const seen = new Set<string>()
  return expanded
    .map((option) => {
      const text = option.trim()
      const match = text.match(/^([A-Ha-h])(?:[.、．)）:：]\s*|\s+)(.*)$/)
      const content = (match?.[2] || text).trim()
      return {
        text: content || text,
        raw: text,
      }
    })
    .filter((option) => option.text)
    .filter((option) => {
      const fingerprint = option.text.replace(/\s+/g, '').toLowerCase()
      if (seen.has(fingerprint)) return false
      seen.add(fingerprint)
      return true
    })
    .map((option, index) => ({
      ...option,
      key: String.fromCharCode(65 + index),
    }))
}

function splitOptionLine(option: string): string[] {
  const text = option.trim()
  if (!text) return []

  const matches = [...text.matchAll(/(?<![A-Za-z])([A-Ha-h])(?:[.、．)）:：]\s*|\s+(?=\S))/g)]
  if (matches.length <= 1) return [text]

  return matches
    .map((match, index) => {
      const start = match.index || 0
      const end = matches[index + 1]?.index ?? text.length
      return text.slice(start, end).trim()
    })
    .filter(Boolean)
}

function normalizeDisplayOptions(options: string[]): NormalizedOption[] {
  const expanded = options.flatMap((option) => splitDisplayOptionLine(option))
  const seen = new Set<string>()
  return expanded
    .map((option) => {
      const raw = option.trim()
      return { raw, text: cleanDisplayOptionText(raw) }
    })
    .filter((option) => option.text)
    .filter((option) => {
      const fingerprint = cleanDisplayOptionText(option.text).replace(/\s+/g, '').toLowerCase()
      if (!fingerprint || seen.has(fingerprint)) return false
      seen.add(fingerprint)
      return true
    })
    .map((option, index) => ({
      ...option,
      key: String.fromCharCode(65 + index),
    }))
}

function cleanDisplayOptionText(value: string) {
  let text = String(value || '')
    .replace(/\u00a0/g, ' ')
    .replace(/^\s*[\[\{"']+|[\]\}"',]+\s*$/g, '')
    .replace(/\*\*/g, '')
    .replace(/`+/g, '')
    .replace(/^[\s\-*]+/, '')
    .trim()

  for (let i = 0; i < 4; i += 1) {
    const next = text
      .replace(/^\(?[A-Ha-h]\)?\s*[.\u3001\uFF0E\uFF0C,)\uFF09:：]\s*(?=\S)/, '')
      .replace(/^[A-Ha-h]\s+(?=\S{2,})/, '')
      .trim()
    if (next === text) break
    text = next
  }

  return text.replace(/\s+/g, ' ').trim()
}

function splitDisplayOptionLine(option: string): string[] {
  const text = String(option || '').trim()
  if (!text) return []
  const markerPattern = /(?<![A-Za-z])([A-Ha-h])(?:[.\u3001\uFF0E\uFF0C,)\uFF09:：]\s*|\s+(?=\S))/g
  const matches = [...text.matchAll(markerPattern)]
  if (matches.length <= 1) return [text]

  return matches
    .map((match, index) => {
      const start = match.index || 0
      const end = matches[index + 1]?.index ?? text.length
      return text.slice(start, end).trim()
    })
    .filter((item) => cleanDisplayOptionText(item))
}

function parseQuestionStem(value: string): QuestionStemPart[] {
  const source = String(value || '').replace(/\\n/g, '\n').trim()
  if (!source) return []
  const parts: QuestionStemPart[] = []
  const fence = /```([A-Za-z0-9_+#.-]*)\s*([\s\S]*?)```/g
  let cursor = 0
  let match: RegExpExecArray | null
  while ((match = fence.exec(source))) {
    const prose = source.slice(cursor, match.index).trim()
    if (prose) parts.push({ type: 'text', content: prose })
    const code = formatQuestionCode(match[2] || '')
    if (code) parts.push({ type: 'code', content: code, language: match[1] || '代码' })
    cursor = match.index + match[0].length
  }
  const tail = source.slice(cursor).trim()
  if (tail) parts.push({ type: 'text', content: tail })
  return parts.length ? parts : [{ type: 'text', content: source }]
}

function formatQuestionCode(value: string) {
  const code = String(value || '').trim()
  if (!code || code.includes('\n')) return code
  return code
    .replace(/\s*\/\/\s*/g, ' // ')
    .replace(/\s*\{\s*/g, ' {\n  ')
    .replace(/;\s*/g, ';\n  ')
    .replace(/\s*\}\s*/g, '\n}\n')
    .replace(/\n\s*\n+/g, '\n')
    .split('\n')
    .map((line) => line.trimEnd())
    .join('\n')
    .trim()
}

function getQuestionSeconds(question: ExerciseQuestion) {
  const type = String(question.type || '').toLowerCase()
  if (type.includes('case')) return 300
  if (type.includes('calculation')) return 240
  if (type.includes('short')) return 180
  if (type.includes('multiple')) return 120
  if (type.includes('matching') || type.includes('ordering')) return 105
  if (type.includes('blank') || type.includes('fill')) return 90
  if (type.includes('true_false') || type.includes('judge')) return 50
  if (type.includes('single') || type.includes('choice')) return 75
  return 90
}

function getDifficultyMultiplier() {
  if (activeDifficulty.value === 'hard') return 1.35
  if (activeDifficulty.value === 'medium') return 1.1
  if (activeDifficulty.value === 'easy') return 0.85
  return 1.18
}

function calculateExamDuration(list = questions.value) {
  const count = Math.max(1, list.length || activeQuestionLimit.value)
  const rawSeconds = list.length
    ? list.reduce((sum, question) => sum + getQuestionSeconds(question), 0)
    : count * 90
  const scaledSeconds = rawSeconds * getDifficultyMultiplier()
  const minimumSeconds = Math.max(90, Math.min(8 * 60, count * 45))
  const roundedSeconds = Math.ceil(Math.max(minimumSeconds, scaledSeconds) / 30) * 30
  return Math.max(90, Math.min(120 * 60, roundedSeconds))
}

function resetExamTimerForCurrentQuestions() {
  examDurationSeconds.value = calculateExamDuration()
  remainingSeconds.value = examDurationSeconds.value
}

function syncSelectedFromCurrent() {
  selectedAnswer.value = mode.value === 'exam'
    ? answerSheet.value[current.value?.id || ''] || ''
    : current.value?.last_answer || ''
  lastResult.value = null
}

async function loadSession(forceRefresh = false, allowExamSetup = false) {
  if (examInProgress.value && !allowExamSetup) {
    error.value = '考试进行中不能刷新题目，请先交卷。'
    return false
  }
  const resetExamToTraining = forceRefresh && mode.value === 'exam'
  if (forceRefresh) refreshNonce.value += 1
  const requestSequence = ++sessionLoadSequence
  loading.value = true
  error.value = ''
  try {
    const resourceParam = (props.questionBankIds || []).length
      ? `&resource_ids=${encodeURIComponent((props.questionBankIds || []).join(','))}`
      : ''
    const resp = await apiGet<any>(`/api/exercise/session?student_id=${encodeURIComponent(studentId.value)}&limit=${activeQuestionLimit.value}${resourceParam}&refresh=${refreshNonce.value}`)
    if (requestSequence !== sessionLoadSequence) return false
    if (resp.success) {
      if (resetExamToTraining) {
        stopExamTimer()
        mode.value = 'training'
      }
      source.value = resp.data.source
      const loadedQuestions = resp.data.questions || []
      questions.value = loadedQuestions.map((q: ExerciseQuestion) => ({
        ...q,
        answered: false,
        last_answer: null,
        last_correct: null,
        last_correct_answer: null,
        last_analysis: null,
      }))
      stats.value = resp.data.stats
      answerSheet.value = {}
      markedQuestionIds.value = []
      lastResult.value = null
      examFinished.value = false
      practicePaused.value = false
      practiceElapsedSeconds.value = 0
      resetExamTimerForCurrentQuestions()
      currentIndex.value = 0
      syncSelectedFromCurrent()
      saveSessionState()
      if (mode.value === 'exam') {
        stopPracticeTimer()
        startExamTimer()
      } else {
        stopExamTimer()
        startPracticeTimer()
      }
      return true
    } else {
      error.value = resp.error?.message || '练习加载失败'
    }
  } catch (e: any) {
    if (requestSequence !== sessionLoadSequence) return false
    error.value = e?.message || '练习服务连接失败'
  } finally {
    if (requestSequence === sessionLoadSequence) loading.value = false
  }
  return false
}

function refreshQuestions() {
  void resetForNewPaper()
}

function isMultipleQuestion(question: ExerciseQuestion | null) {
  const type = String(question?.type || '').toLowerCase()
  return type === 'multiple_choice' || type.includes('multiple') || type.includes('多选')
}

function answerKeys(value = selectedAnswer.value) {
  return String(value || '').split(/[,，、\s]+/).map((item) => item.trim().toUpperCase()).filter(Boolean)
}

function isOptionSelected(key: string) {
  return currentIsMultiple.value ? answerKeys().includes(key) : selectedAnswer.value === key
}

function isQuestionMarked(question: ExerciseQuestion) {
  return markedQuestionIds.value.includes(question.id)
}

function toggleMarkCurrent() {
  if (!current.value || navigationLocked.value) return
  const id = current.value.id
  markedQuestionIds.value = markedQuestionIds.value.includes(id)
    ? markedQuestionIds.value.filter((item) => item !== id)
    : [...markedQuestionIds.value, id]
  saveSessionState()
}

function onOptionChange(key: string, event: Event) {
  if (responseLocked.value) return
  if (currentIsMultiple.value) {
    const checked = Boolean((event.target as HTMLInputElement | null)?.checked)
    const keys = new Set(answerKeys())
    if (checked) keys.add(key)
    else keys.delete(key)
    selectedAnswer.value = Array.from(keys).sort().join(',')
    if (mode.value === 'exam') saveExamDraft()
    return
  }
  selectedAnswer.value = key
  if (mode.value === 'exam') completeExamAnswer()
}

async function submitAnswer() {
  if (!current.value || !selectedAnswer.value || answering.value || mode.value === 'exam') return
  answering.value = true
  error.value = ''
  try {
    const resp = await apiPost<any>('/api/exercise/answer', {
      student_id: studentId.value,
      question_id: current.value.id,
      answer: selectedAnswer.value,
    })
    if (resp.success) {
      lastResult.value = resp.data
      emit('answered', { ...resp.data, question: current.value, mode: mode.value })
      stats.value = resp.data.stats
      questions.value[currentIndex.value] = {
        ...current.value,
        answered: true,
        last_answer: selectedAnswer.value,
        last_correct: resp.data.correct,
        last_correct_answer: resp.data.correct_answer,
        last_analysis: resp.data.analysis,
      }
      if (sessionCompleted.value) stopPracticeTimer()
      saveSessionState()
    } else {
      error.value = resp.error?.message || '判题失败'
    }
  } catch (e: any) {
    error.value = e?.message || '判题服务连接失败'
  } finally {
    answering.value = false
  }
}

function saveExamDraft() {
  if (!current.value || mode.value !== 'exam' || examFinished.value) return
  answerSheet.value = {
    ...answerSheet.value,
    [current.value.id]: selectedAnswer.value,
  }
  saveSessionState()
}

function completeExamAnswer() {
  saveExamDraft()
}

async function finishExam() {
  if (mode.value !== 'exam' || examFinished.value || answering.value) return false
  saveExamDraft()
  const resumeTimerOnFailure = remainingSeconds.value > 0
  answering.value = true
  error.value = ''
  stopExamTimer()
  try {
    for (const question of questions.value) {
      if (question.answered) continue
      const answer = answerSheet.value[question.id] || ''
      const resp = await apiPost<any>('/api/exercise/answer', {
        student_id: studentId.value,
        question_id: question.id,
        answer,
      })
      if (!resp.success) throw new Error(resp.error?.message || `第 ${questions.value.indexOf(question) + 1} 题提交失败`)
      emit('answered', { ...resp.data, question, mode: mode.value })
      questions.value = questions.value.map((q) => q.id === question.id
        ? {
            ...q,
            answered: true,
            last_answer: answer,
            last_correct: resp.data.correct,
            last_correct_answer: resp.data.correct_answer,
            last_analysis: resp.data.analysis,
          }
        : q)
      stats.value = resp.data.stats
    }
    questions.value = questions.value.map((q) => q.answered
      ? q
      : { ...q, answered: true, last_answer: '', last_correct: false, last_correct_answer: q.last_correct_answer || null, last_analysis: q.last_analysis || null })
    examFinished.value = true
    lastResult.value = null
    saveSessionState()
    return true
  } catch (e: any) {
    error.value = e?.message || '考试提交失败'
  } finally {
    answering.value = false
    if (!examFinished.value && resumeTimerOnFailure) startExamTimer()
  }
  return false
}

function nextQuestion() {
  if (!questions.value.length || navigationLocked.value) return
  saveExamDraft()
  currentIndex.value = Math.min(currentIndex.value + 1, questions.value.length - 1)
  syncSelectedFromCurrent()
}

function previousQuestion() {
  if (!questions.value.length || navigationLocked.value) return
  saveExamDraft()
  currentIndex.value = Math.max(currentIndex.value - 1, 0)
  syncSelectedFromCurrent()
}

function selectQuestion(index: number) {
  if (!questions.value.length || navigationLocked.value) return
  saveExamDraft()
  currentIndex.value = Math.max(0, Math.min(index, questions.value.length - 1))
  syncSelectedFromCurrent()
}

function selectMode(nextMode: 'training' | 'exam') {
  if (loading.value || answering.value) return
  if (nextMode === mode.value && (nextMode === 'training' || !examFinished.value)) return
  if (examInProgress.value) {
    error.value = '考试已经开始，交卷后才能切换模式。'
    return
  }
  if (nextMode === 'exam') {
    stopPracticeTimer()
    showExamStartDialog.value = true
    error.value = ''
    return
  }
  switchModeImmediately(nextMode)
}

async function switchModeImmediately(nextMode: 'training' | 'exam') {
  if (loading.value || answering.value) return
  const previousMode = mode.value
  const resumePreviousTimer = previousMode === 'exam' && !examFinished.value
  const resumePreviousPracticeTimer = previousMode === 'training' && !practicePaused.value && !sessionCompleted.value
  stopExamTimer()
  stopPracticeTimer()
  mode.value = nextMode
  const loaded = await loadSession(false, true)
  if (loaded) return
  mode.value = previousMode
  if (resumePreviousTimer) startExamTimer()
  if (resumePreviousPracticeTimer) startPracticeTimer()
}

function confirmStartExam() {
  if (examCountdown.value > 0) return
  examCountdown.value = 3
  countdownTimer = window.setInterval(() => {
    examCountdown.value -= 1
    if (examCountdown.value <= 0) {
      stopCountdown()
      showExamStartDialog.value = false
      void switchModeImmediately('exam')
    }
  }, 1000)
}

function cancelStartExam() {
  stopCountdown()
  showExamStartDialog.value = false
  examCountdown.value = 0
  if (mode.value === 'training' && !practicePaused.value && !sessionCompleted.value) startPracticeTimer()
}

function startPracticeTimer() {
  stopPracticeTimer()
  if (props.active === false || mode.value !== 'training' || !questions.value.length || practicePaused.value || sessionCompleted.value) return
  let lastTickAt = Date.now()
  practiceTimer = window.setInterval(() => {
    const now = Date.now()
    const elapsed = Math.max(1, Math.floor((now - lastTickAt) / 1000))
    lastTickAt += elapsed * 1000
    practiceElapsedSeconds.value += elapsed
  }, 1000)
}

function stopPracticeTimer() {
  if (practiceTimer !== null) {
    window.clearInterval(practiceTimer)
    practiceTimer = null
  }
}

function startExamTimer() {
  stopExamTimer()
  if (mode.value !== 'exam' || examFinished.value) return
  if (!examDurationSeconds.value) examDurationSeconds.value = calculateExamDuration()
  if (remainingSeconds.value <= 0) remainingSeconds.value = examDurationSeconds.value
  let lastTickAt = Date.now()
  examTimer = window.setInterval(() => {
    const now = Date.now()
    const elapsed = Math.max(1, Math.floor((now - lastTickAt) / 1000))
    lastTickAt += elapsed * 1000
    remainingSeconds.value = Math.max(0, remainingSeconds.value - elapsed)
    if (remainingSeconds.value <= 0) {
      remainingSeconds.value = 0
      void finishExam()
    }
  }, 1000)
}

function stopExamTimer() {
  if (examTimer !== null) {
    window.clearInterval(examTimer)
    examTimer = null
  }
}

function toggleSessionPause() {
  if (!questions.value.length || loading.value || answering.value) return
  if (mode.value === 'exam') return
  if (sessionCompleted.value) return
  practicePaused.value = !practicePaused.value
  if (practicePaused.value) stopPracticeTimer()
  else startPracticeTimer()
  saveSessionState()
}

function stopCountdown() {
  if (countdownTimer !== null) {
    window.clearInterval(countdownTimer)
    countdownTimer = null
  }
}

function saveSessionState() {
  const payload = {
    version: 1,
    saved_at: Date.now(),
    mode: mode.value,
    source: source.value,
    questions: questions.value,
    stats: stats.value,
    currentIndex: currentIndex.value,
    selectedAnswer: selectedAnswer.value,
    answerSheet: answerSheet.value,
    markedQuestionIds: markedQuestionIds.value,
    lastResult: lastResult.value,
    examFinished: examFinished.value,
    practicePaused: practicePaused.value,
    practiceElapsedSeconds: practiceElapsedSeconds.value,
    examDurationSeconds: examDurationSeconds.value,
    remainingSeconds: remainingSeconds.value,
    showExamStartDialog: false,
    examCountdown: 0,
  }
  try {
    window.localStorage.setItem(storageKey.value, JSON.stringify(payload))
  } catch {
    // localStorage 不可用时不影响作答流程。
  }
}

function restoreSessionState() {
  try {
    const raw = window.localStorage.getItem(storageKey.value)
    if (!raw) return false
    const payload = JSON.parse(raw)
    if (!payload || payload.version !== 1 || !Array.isArray(payload.questions) || !payload.questions.length) return false

    mode.value = payload.mode === 'exam' ? 'exam' : 'training'
    source.value = payload.source || ''
    questions.value = payload.questions
    stats.value = payload.stats || null
    currentIndex.value = Math.max(0, Math.min(Number(payload.currentIndex) || 0, questions.value.length - 1))
    answerSheet.value = payload.answerSheet || {}
    markedQuestionIds.value = Array.isArray(payload.markedQuestionIds) ? payload.markedQuestionIds : []
    lastResult.value = payload.lastResult || null
    examFinished.value = Boolean(payload.examFinished)
    practicePaused.value = Boolean(payload.practicePaused)
    practiceElapsedSeconds.value = Math.max(0, Number(payload.practiceElapsedSeconds) || 0)
    const calculatedDuration = calculateExamDuration()
    examDurationSeconds.value = Number(payload.examDurationSeconds) || calculatedDuration
    const savedRemainingSeconds = Number(payload.remainingSeconds)
    remainingSeconds.value = Number.isFinite(savedRemainingSeconds)
      ? Math.min(savedRemainingSeconds, examDurationSeconds.value)
      : examDurationSeconds.value
    const elapsed = Math.max(0, Math.floor((Date.now() - (Number(payload.saved_at) || Date.now())) / 1000))
    if (mode.value === 'exam' && !examFinished.value) {
      remainingSeconds.value = Math.max(0, remainingSeconds.value - Math.max(0, elapsed))
    } else if (mode.value === 'training' && !practicePaused.value && !sessionCompleted.value) {
      practiceElapsedSeconds.value += elapsed
    }
    selectedAnswer.value = mode.value === 'exam'
      ? answerSheet.value[current.value?.id || ''] || payload.selectedAnswer || ''
      : payload.selectedAnswer || current.value?.last_answer || ''
    if (mode.value === 'exam' && !examFinished.value) {
      if (remainingSeconds.value <= 0) window.setTimeout(() => void finishExam(), 0)
      else startExamTimer()
    } else if (mode.value === 'training' && !practicePaused.value && !sessionCompleted.value) {
      startPracticeTimer()
    }
    return true
  } catch {
    return false
  }
}

function hasActiveExam() {
  return examInProgress.value
}

async function resetForNewPaper() {
  const previousState = {
    mode: mode.value,
    examFinished: examFinished.value,
    practicePaused: practicePaused.value,
    practiceElapsedSeconds: practiceElapsedSeconds.value,
    examDurationSeconds: examDurationSeconds.value,
    remainingSeconds: remainingSeconds.value,
  }
  const resumeExamTimer = previousState.mode === 'exam' && !previousState.examFinished
  const resumePracticeTimer = previousState.mode === 'training' && !previousState.practicePaused && !sessionCompleted.value

  stopExamTimer()
  stopPracticeTimer()
  stopCountdown()
  showExamStartDialog.value = false
  examCountdown.value = 0
  mode.value = 'training'
  examFinished.value = false
  practicePaused.value = false
  practiceElapsedSeconds.value = 0
  resetExamTimerForCurrentQuestions()

  const expectedLoadSequence = sessionLoadSequence + 1
  const loaded = await loadSession(true, true)
  if (loaded || sessionLoadSequence !== expectedLoadSequence) return loaded

  mode.value = previousState.mode
  examFinished.value = previousState.examFinished
  practicePaused.value = previousState.practicePaused
  practiceElapsedSeconds.value = previousState.practiceElapsedSeconds
  examDurationSeconds.value = previousState.examDurationSeconds
  remainingSeconds.value = previousState.remainingSeconds
  if (resumeExamTimer) startExamTimer()
  if (resumePracticeTimer) startPracticeTimer()
  return false
}

defineExpose({
  loadSession,
  resetForNewPaper,
  finishExam,
  hasActiveExam,
})

onMounted(() => {
  if (!configuredBankCount.value || !restoreSessionState()) void loadSession()
})

onBeforeUnmount(() => {
  sessionLoadSequence += 1
  stopExamTimer()
  stopPracticeTimer()
  stopCountdown()
  saveSessionState()
})

watch(
  [mode, source, questions, currentIndex, selectedAnswer, answerSheet, markedQuestionIds, lastResult, examFinished, practicePaused, practiceElapsedSeconds, remainingSeconds],
  saveSessionState,
  { deep: true },
)

watch([activeQuestionBankKey, activeQuestionLimit, activeDifficulty, () => props.resetSeed], ([key, limit, difficulty, seed], [oldKey, oldLimit, oldDifficulty, oldSeed]) => {
  if (key === oldKey && limit === oldLimit && difficulty === oldDifficulty && seed === oldSeed) return
  if (examInProgress.value) return
  void resetForNewPaper()
})

watch(() => props.active, (active) => {
  if (mode.value !== 'training') return
  if (active === false) stopPracticeTimer()
  else if (!practicePaused.value && !sessionCompleted.value) startPracticeTimer()
})
</script>

<template>
  <div class="exercise-practice-center">
    <aside class="practice-sidebar exercise-card">
      <div class="practice-sidebar-head">
        <span>Practice Center</span>
        <strong>练习诊断中心</strong>
        <p>智能练习 · 精准诊断 · 个性提升</p>
      </div>
      <nav class="practice-menu" aria-label="练习诊断菜单">
        <button type="button" @click="emit('navigate', 'builder')">
          <span>▤</span>
          <strong>题库定制</strong>
        </button>
        <button type="button" class="active" @click="emit('navigate', 'diagnosis')">
          <span>▣</span>
          <strong>智能做题</strong>
        </button>
        <button type="button" @click="emit('navigate', 'tagGalaxy')">
          <span>◎</span>
          <strong>知识点诊断</strong>
        </button>
        <button type="button" @click="emit('navigate', 'wrongBook')">
          <span>◉</span>
          <strong>能力雷达</strong>
        </button>
        <button type="button" @click="emit('navigate', 'wrongBook')">
          <span>▤</span>
          <strong>错题本</strong>
        </button>
        <button type="button" @click="emit('navigate', 'wrongBook')">
          <span>☆</span>
          <strong>我的收藏</strong>
        </button>
        <button type="button" @click="emit('navigate', 'tagGalaxy')">
          <span>↺</span>
          <strong>历史记录</strong>
        </button>
      </nav>
      <div class="practice-learning-card">
        <span>正在学习</span>
        <strong>{{ currentPrimaryTag }}</strong>
        <p>{{ sourceLabel }}</p>
        <div class="practice-mini-progress"><i :style="{ width: `${progressPercent}%` }"></i></div>
        <button type="button" @click="emit('navigate', 'builder')">调整阶段题库</button>
      </div>
    </aside>

    <section class="exercise-card exercise-main-card practice-main-panel">
      <header class="exercise-card-head exercise-hero">
        <div class="practice-main-title">
          <strong>智能做题</strong>
        </div>
        <div class="exercise-head-actions">
          <div class="practice-question-count" :class="{ 'is-empty': !hasQuestions }">
            <template v-if="hasQuestions">
              <strong>第 {{ currentIndex + 1 }} / {{ questions.length }} 题</strong>
              <span>{{ currentTypeLabel }} · {{ difficultyLabel }}</span>
            </template>
            <template v-else>
              <strong>{{ emptyQuestionTitle }}</strong>
              <span>{{ emptyQuestionHint }}</span>
            </template>
          </div>
          <div class="practice-time-chip">
            <span>◷</span>
            <strong>{{ hasQuestions ? (mode === 'exam' ? timerText : practiceTimerText) : '--:--:--' }}</strong>
          </div>
          <button
            v-if="mode === 'training'"
            type="button"
            class="practice-icon-btn"
            :disabled="!questions.length || loading || answering || sessionCompleted"
            @click="toggleSessionPause"
          >
            {{ sessionPaused ? '继续' : '暂停' }}
          </button>
          <div class="exercise-mode-switch">
            <button :class="{ active: hasQuestions && mode === 'training' }" :disabled="!hasQuestions || loading || answering || examInProgress" @click="selectMode('training')">训练模式</button>
            <button :class="{ active: hasQuestions && mode === 'exam' }" :disabled="!hasQuestions || loading || answering || examInProgress" @click="selectMode('exam')">考试模式</button>
          </div>
          <button class="exercise-primary-btn" :disabled="loading || answering || examInProgress" @click="refreshQuestions">
            {{ loading ? '刷新中' : '刷新题目' }}
          </button>
        </div>
      </header>

      <div class="practice-progress-line" aria-label="答题进度">
        <i :style="{ width: `${progressPercent}%` }"></i>
      </div>

      <div class="exercise-overview">
        <article>
          <span>当前模式</span>
          <strong>{{ modeLabel }}</strong>
          <em>{{ sourceLabel }}</em>
        </article>
        <article>
          <span>{{ mode === 'exam' ? '已答进度' : '提交进度' }}</span>
          <strong>{{ progressPercent }}%</strong>
          <div class="exercise-mini-track"><i :style="{ width: `${progressPercent}%` }"></i></div>
        </article>
        <article>
          <span>诊断提示</span>
          <strong>{{ diagnosisInsight }}</strong>
        </article>
      </div>

      <div v-if="!current" class="exercise-empty">
        <i class="exercise-empty-mark">+</i>
        <strong>还没有可用的定制练习</strong>
        <span>练习诊断只读取路径推送当前节点生成的题库，不会混入其它课程或章节。</span>
        <div class="exercise-empty-config" aria-label="当前题库状态">
          <article><span>题库状态</span><strong>{{ configuredBankCount ? '等待载入' : '尚未生成' }}</strong></article>
          <article><span>当前课程</span><strong>{{ configuredCourseName }}</strong></article>
          <article><span>诊断范围</span><strong>{{ configuredKnowledgePoint }}</strong></article>
        </div>
        <div class="exercise-empty-steps">
          <button type="button" @click="emit('navigate', 'builder')"><b>01</b><span><strong>确认路径节点</strong><small>题目范围由当前学习阶段锁定</small></span></button>
          <button type="button" @click="emit('navigate', 'builder')"><b>02</b><span><strong>设置题量题型</strong><small>按需要配置难度、数量与形式</small></span></button>
          <button type="button" @click="refreshQuestions"><b>03</b><span><strong>载入已生成题库</strong><small>有可用题库时立即开始练习</small></span></button>
        </div>
        <div class="exercise-empty-outcomes" aria-label="完成作答后的真实数据去向">
          <span>完成作答后</span>
          <div>
            <article><strong>错题自动归档</strong><small>保留用户答案、正确答案和错因解析</small></article>
            <article><strong>能力雷达更新</strong><small>依据真实正误和重做结果计算</small></article>
            <article><strong>诊断证据沉淀</strong><small>作为学习路径与画像迭代的输入</small></article>
          </div>
        </div>
        <button class="exercise-empty-primary" type="button" @click="emit('navigate', 'builder')">前往定制题库</button>
      </div>

      <div v-else class="exercise-workbench">
        <div v-if="mode === 'exam'" class="exercise-exam-timer" :class="{ urgent: remainingSeconds <= 180 && !examFinished }">
          <div>
            <span>{{ examFinished ? '考试已交卷' : '考试倒计时' }}</span>
            <strong>{{ timerText }}</strong>
          </div>
          <div class="exercise-timer-track">
            <i :style="{ width: `${timerPercent}%` }"></i>
          </div>
        </div>
        <div v-if="sessionPaused" class="practice-paused-banner" role="status">
          <strong>训练已暂停</strong>
          <span>继续后才能修改答案或切换题目。</span>
        </div>

        <div class="exercise-toolbar">
          <div class="exercise-badges exercise-question-meta">
            <span>{{ currentTypeLabel }}</span>
            <span>{{ currentPrimaryTag }}</span>
            <span>第 {{ progressText }} 题</span>
            <span>{{ questionStatusText }}</span>
            <span v-if="mode === 'exam'">{{ examAnsweredCount }} / {{ questions.length }} 已答</span>
            <span v-else>{{ answeredCount }} / {{ questions.length }} 已提交</span>
          </div>
          <div class="exercise-switch">
            <button :disabled="navigationLocked || currentIndex === 0" @click="previousQuestion">上一题</button>
            <button :disabled="navigationLocked || currentIndex === questions.length - 1" @click="nextQuestion">下一题</button>
          </div>
        </div>

        <article class="exercise-question exercise-question-focus">
          <div class="exercise-question-kicker">
            <span>当前题目</span>
            <em>{{ questionStatusText }}</em>
          </div>
          <div class="exercise-stem-content">
            <template v-for="(part, index) in currentStemParts" :key="`${part.type}-${index}`">
              <p v-if="part.type === 'text'">{{ part.content }}</p>
              <figure v-else class="exercise-code-block">
                <figcaption>{{ part.language || '代码' }}</figcaption>
                <pre><code>{{ part.content }}</code></pre>
              </figure>
            </template>
          </div>
          <div v-if="current.tags?.length && (mode === 'training' || examFinished)" class="exercise-tags">
            <span v-for="tag in current.tags" :key="tag">{{ tag }}</span>
          </div>
        </article>

        <div v-if="currentOptions.length" class="exercise-options">
          <label v-for="option in currentOptions" :key="option.key" :class="{ selected: isOptionSelected(option.key), disabled: responseLocked }">
            <input
              :type="currentIsMultiple ? 'checkbox' : 'radio'"
              :name="current.id"
              :value="option.key"
              :checked="isOptionSelected(option.key)"
              :disabled="responseLocked"
              @change="onOptionChange(option.key, $event)"
            />
            <span class="exercise-option-control"></span>
            <span class="exercise-option-key">{{ option.key }}</span>
            <span class="exercise-option-text">{{ option.text }}</span>
          </label>
        </div>

        <input v-else v-model="selectedAnswer" class="exercise-answer-input" :disabled="responseLocked" placeholder="输入答案" @change="mode === 'exam' ? completeExamAnswer() : undefined" />

        <div class="exercise-actions">
          <button class="exercise-secondary-btn practice-prev-btn" :disabled="navigationLocked || currentIndex === 0" @click="previousQuestion">
            ← 上一题
          </button>
          <button class="exercise-secondary-btn practice-mark-btn" :class="{ active: isCurrentMarked }" :disabled="navigationLocked" @click="toggleMarkCurrent">
            ⚑ {{ isCurrentMarked ? '已标记' : '标记本题' }}
          </button>
          <button v-if="mode === 'training'" class="exercise-primary-btn" :disabled="responseLocked || !selectedAnswer" @click="submitAnswer">
            {{ answering ? '判题中' : '提交答案' }}
          </button>
          <button v-else class="exercise-primary-btn" :disabled="answering || examFinished" @click="finishExam">
            {{ answering ? '交卷中' : '交卷并查看诊断' }}
          </button>
          <button class="exercise-primary-btn practice-next-btn" :disabled="navigationLocked || currentIndex === questions.length - 1" @click="nextQuestion">
            下一题 →
          </button>
          <span v-if="current.answered && showImmediateResult" :class="current.last_correct ? 'exercise-ok' : 'exercise-wrong'">
            本题已作答：{{ current.last_correct ? '正确' : '错误' }}
          </span>
          <span v-if="mode === 'exam' && !examFinished" class="exercise-ok">考试中不显示答案和解析</span>
        </div>

        <div v-if="lastResult && showImmediateResult" class="exercise-result" :class="lastResult.correct ? 'is-correct' : 'is-wrong'">
          <strong>{{ lastResult.correct ? '回答正确' : '回答错误' }}</strong>
          <span>正确答案：{{ lastResult.correct_answer || '待核验' }}</span>
          <p v-if="lastResult.analysis">{{ lastResult.analysis }}</p>
        </div>

        <div v-if="mode === 'exam' && examFinished" class="exercise-result" :class="current.last_correct ? 'is-correct' : 'is-wrong'">
          <strong>{{ current.last_correct ? '本题正确' : '本题错误' }}</strong>
          <span>你的答案：{{ current.last_answer || '未作答' }}</span>
          <span>正确答案：{{ current.last_correct_answer || '待核验' }}</span>
          <p v-if="current.last_analysis">{{ current.last_analysis }}</p>
          <p v-else>考试已结束，可查看统计和标签表现。</p>
        </div>

        <div v-if="error" class="exercise-error">{{ error }}</div>
      </div>
    </section>

    <aside class="exercise-side">
      <section class="exercise-card exercise-stats-card">
        <div class="exercise-side-head">
          <div class="exercise-title">
            <span class="green"></span>
            <strong>诊断结果</strong>
          </div>
          <div class="exercise-score-ring" :style="{ '--score': `${showStats ? sessionStats.accuracy : progressPercent}%` }">
            <strong>{{ showStats ? `${sessionStats.accuracy}%` : `${progressPercent}%` }}</strong>
            <span>{{ showStats ? '正确率' : '完成度' }}</span>
          </div>
        </div>
        <div v-if="!showStats" class="exercise-compact-empty">完成本轮全部题目后显示统计</div>
        <div v-else class="exercise-stats">
          <div>
            <strong>{{ sessionStats.total }}</strong>
            <span>总题数</span>
          </div>
          <div>
            <strong>{{ sessionStats.correct }}</strong>
            <span>正确</span>
          </div>
          <div>
            <strong>{{ sessionStats.accuracy }}%</strong>
            <span>正确率</span>
          </div>
        </div>

        <div v-if="showStats" class="exercise-weak-tags">
          <strong>标签统计</strong>
          <div v-if="sessionStats.tag_stats.length" class="exercise-weak-list">
            <p v-for="tag in sessionStats.tag_stats" :key="tag.tag" :class="tag.status === 'weak' ? 'is-weak' : 'is-stable'">
              <span>{{ tag.tag }}</span>
              <em>{{ tag.wrong ? `错 ${tag.wrong} / ${tag.total}` : `稳 ${tag.total} / ${tag.total}` }}</em>
            </p>
          </div>
          <div v-else class="exercise-compact-empty">暂无标签统计</div>
        </div>
      </section>

      <section class="exercise-card exercise-nav-card">
        <div class="exercise-side-head compact">
          <div class="exercise-title">
            <span></span>
            <strong>答题进度</strong>
          </div>
          <em>{{ progressText }}</em>
        </div>
        <div class="practice-progress-summary">
          <p>{{ hasQuestions ? `已答 ${completedCount} / ${questions.length}` : '尚未载入题目' }}</p>
          <div class="practice-mini-progress"><i :style="{ width: `${progressPercent}%` }"></i></div>
          <dl>
            <div>
              <dt>未答</dt>
              <dd>{{ unansweredCount }}</dd>
            </div>
            <div>
              <dt>已标记</dt>
              <dd>{{ markedCount }}</dd>
            </div>
            <div>
              <dt>考试状态</dt>
              <dd>{{ practiceStatusText }}</dd>
            </div>
          </dl>
          <div v-if="!questions.length" class="practice-empty-side-guide">
            <section>
              <span>当前设置</span>
              <strong>{{ configuredCourseName }}</strong>
              <p>{{ configuredKnowledgePoint }}</p>
              <small>{{ configuredBankCount ? '题库等待载入，刷新后显示实际题量与难度' : '尚未生成题库' }}</small>
            </section>
            <section>
              <span>开始前准备</span>
              <p><b :class="{ ready: configuredQuestionTypeCount > 0 }"></b>题量和题型配置</p>
              <p><b :class="{ ready: Boolean(configuredKnowledgePoint) }"></b>诊断知识点范围</p>
              <p><b :class="{ ready: configuredBankCount > 0 }"></b>练习专用题库</p>
            </section>
            <section>
              <span>载入后将展示</span>
              <p><b></b>当前题号与完成进度</p>
              <p><b></b>未答、已标记和暂存状态</p>
              <p><b></b>训练即时判题或考试统一交卷</p>
              <p><b></b>错题与知识点诊断结果</p>
            </section>
            <div>
              <button type="button" @click="emit('navigate', 'builder')">检查定制设置</button>
              <button type="button" class="primary" @click="refreshQuestions">重新载入题库</button>
            </div>
          </div>
        </div>
        <div v-if="!questions.length" class="exercise-compact-empty">载入后显示题号</div>
        <div v-else class="exercise-question-nav">
          <button
            v-for="(q, idx) in questions"
            :key="q.id"
            :class="[
              idx === currentIndex ? 'active' : '',
              q.answered && showImmediateResult && q.last_correct ? 'correct' : '',
              q.answered && showImmediateResult && q.last_correct === false ? 'wrong' : '',
              mode === 'exam' && answerSheet[q.id] && !examFinished ? 'saved' : '',
              isQuestionMarked(q) ? 'marked' : '',
            ]"
            :disabled="navigationLocked"
            @click="selectQuestion(idx)"
          >
            {{ idx + 1 }}
          </button>
        </div>
        <p class="practice-progress-hint">交卷后生成知识点诊断与错题解析。</p>
      </section>
    </aside>

    <div v-if="showExamStartDialog" class="exercise-modal-backdrop">
      <section class="exercise-modal exercise-card">
        <div v-if="examCountdown > 0" class="exercise-countdown">
          <span>{{ examCountdown }}</span>
          <strong>准备进入考试模式</strong>
        </div>
        <template v-else>
          <div class="exercise-title">
            <span></span>
            <strong>进入考试模式</strong>
          </div>
          <p>进入考试模式后将开始计时，考试过程中不能切换模式或其它功能；如需离开，需要先交卷。</p>
          <div class="exercise-modal-actions">
            <button class="exercise-secondary-btn" @click="cancelStartExam">取消</button>
            <button class="exercise-primary-btn" @click="confirmStartExam">确定进入</button>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>
