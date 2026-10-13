<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useStudent } from '@/composables/useStudent'
import MarkdownContent from '@/components/MarkdownContent.vue'

type RealtimeConfig = {
  enabled?: boolean
  model?: string
  transport?: string
  ws_path?: string
  timeout?: number
  config_error?: string | null
}

type ConversationMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

const INPUT_SAMPLE_RATE = 16000
const OUTPUT_SAMPLE_RATE = 24000
const XINGYUAN_SDK_URL = 'https://media.xingyun3d.com/xingyun3d/general/litesdk/xmovAvatar@latest.js'
const XINGYUAN_GATEWAY_SERVER = 'https://nebula-agent.xingyun3d.com/user/v1/ttsa/session'

const { studentId } = useStudent()
const localVideoRef = ref<HTMLVideoElement | null>(null)
const digitalHumanCanvasRef = ref<HTMLCanvasElement | null>(null)
const xingyuanSdkMountRef = ref<HTMLDivElement | null>(null)
const config = ref<RealtimeConfig>({})
const avatarConfig = ref<any>({})
const xingyuanSdkConfig = ref<any>({})
const avatarVideoUrl = ref('')
const avatarStatus = ref('')
const xingyuanSdkVisible = ref(false)
const avatarConfigLoaded = ref(false)
const connecting = ref(false)
const connected = ref(false)
const localStreamReady = ref(false)
const micMuted = ref(false)
const cameraOff = ref(false)
const aiSpeaking = ref(false)
const userSpeaking = ref(false)
const statusText = ref('正在读取 Realtime 配置...')
const statusKind = ref<'info' | 'error'>('info')
const conversation = ref<ConversationMessage[]>([])
const saveStatus = ref('')
const lastVisibleLog = ref('')

let ws: WebSocket | null = null
let localStream: MediaStream | null = null
let audioContext: AudioContext | null = null
let sourceNode: MediaStreamAudioSourceNode | null = null
let processorNode: ScriptProcessorNode | null = null
let upstreamReady = false
let playbackTime = 0
let pendingInterruptUntil = 0
let eventId = 0
let messageId = 0
let sessionStartedAt = ''
let sessionSaved = true
let pendingAssistantText = ''
let silenceTimer: number | null = null
let interruptCooldown = 0
let realtimeConnectSettled = false
let upstreamHadError = false
let realtimeClosedNormally = false
let digitalHumanImage: HTMLImageElement | null = null
let digitalHumanFrame = 0
let digitalHumanResizeObserver: ResizeObserver | null = null
let avatarSessionId = ''
let avatarSessionStarting = false
let xingyuanSdkInstance: any = null
let xingyuanSdkLoading: Promise<void> | null = null
let avatarRecognition: any = null
let avatarRecognitionShouldRun = false
let avatarRecognitionStarting = false
let avatarRecognitionRestartTimer: number | null = null
let avatarVoiceAskPending = false
let avatarInterruptSource: MediaStreamAudioSourceNode | null = null
let avatarInterruptAnalyser: AnalyserNode | null = null
let avatarInterruptFrame = 0
let avatarLastInterruptAt = 0
let avatarForceSilentUntil = 0
let avatarSpeechFinishResolve: (() => void) | null = null
let avatarSpeechFinishTimer: number | null = null
let avatarSpeechStartTimer: number | null = null
let avatarSpeechTurn = 0
let avatarSpeechStarted = false
const playbackSources = new Set<AudioBufferSourceNode>()

const hintText = computed(() => {
  if (avatarVoiceMode.value) return ''
  if (config.value.config_error) return '语音辅导服务还没有配置完成，请先检查密钥和连接地址。'
  if (!connected.value) return '点击开始通话后，浏览器会请求摄像头和麦克风权限。'
  if (aiSpeaking.value) return 'AI 正在回答；可以直接开口或点击“打断 AI”。'
  if (userSpeaking.value) return '正在听你说话。'
  return '通话中，可以自然提问、追问或让老师换一种讲法。'
})
const xingyuanSdkConfigured = computed(() => avatarConfigLoaded.value && xingyuanSdkConfig.value?.enabled === true)
const avatarVoiceMode = computed(() => Boolean(config.value.config_error) && xingyuanSdkConfigured.value)

function setStatus(text: string, kind: 'info' | 'error' = 'info') {
  statusText.value = text
  statusKind.value = kind
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms))
}

function logEvent(text: string) {
  if (!text || text === lastVisibleLog.value) return
  lastVisibleLog.value = text
  saveStatus.value = text
}

function appendConversation(role: 'user' | 'assistant', content: string) {
  const text = String(content || '').trim()
  if (!text) return
  const last = conversation.value[conversation.value.length - 1]
  if (last && last.role === role && last.content === text) return
  conversation.value.push({
    id: ++messageId,
    role,
    content: text,
    timestamp: new Date().toLocaleTimeString('zh-CN'),
  })
  conversation.value = conversation.value.slice(-30)
  sessionSaved = false
}

function appendAssistantDraft() {
  const id = ++messageId
  conversation.value.push({
    id,
    role: 'assistant',
    content: '',
    timestamp: new Date().toLocaleTimeString('zh-CN'),
  })
  conversation.value = conversation.value.slice(-30)
  sessionSaved = false
  return id
}

function updateConversationContent(id: number, content: string) {
  const item = conversation.value.find((message) => message.id === id)
  if (!item) return
  item.content = content
  conversation.value = [...conversation.value]
  sessionSaved = false
}

function findAvatarVideoUrl(payload: any): string {
  if (!payload || typeof payload !== 'object') return ''
  const direct = payload.stream_url || payload.video_url || payload.play_url || payload.url || payload.webrtc_url
  if (typeof direct === 'string') return direct
  for (const value of Object.values(payload)) {
    if (value && typeof value === 'object') {
      const nested = findAvatarVideoUrl(value)
      if (nested) return nested
    }
  }
  return ''
}

function findAvatarSessionId(payload: any): string {
  if (!payload || typeof payload !== 'object') return ''
  const direct = payload.session_id || payload.sessionId || payload.id
  if (typeof direct === 'string') return direct
  for (const value of Object.values(payload)) {
    if (value && typeof value === 'object') {
      const nested = findAvatarSessionId(value)
      if (nested) return nested
    }
  }
  return ''
}

async function loadAvatarConfig() {
  try {
    const [configResponse, sdkResponse] = await Promise.all([
      fetch('/api/avatar/config'),
      fetch('/api/avatar/sdk-config'),
    ])
    const data = await configResponse.json().catch(() => ({}))
    const sdkData = await sdkResponse.json().catch(() => ({}))
    avatarConfig.value = data
    xingyuanSdkConfig.value = sdkData
    avatarStatus.value = data.enabled ? '星元具身数字人已就绪' : (data.config_error || '数字人视频引擎未配置完整')
  } catch {
    avatarStatus.value = '数字人视频引擎配置读取失败'
  } finally {
    avatarConfigLoaded.value = true
  }
}

function getXingyuanSdkGlobal() {
  const root = window as any
  const names = [
    'XmovAvatar',
    'XMovAvatar',
    'XMOVAvatar',
    'xmovAvatar',
    'XmovAvatarLite',
    'XmovAvatarSDK',
    'XingyunAvatar',
    'Xingyun3DAvatar',
  ]
  for (const name of names) {
    if (root[name]) return root[name]
  }
  return null
}

async function loadXingyuanSdk() {
  if (xingyuanSdkLoading) return xingyuanSdkLoading
  xingyuanSdkLoading = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-xingyuan-avatar-sdk="true"]')
    if (existing?.dataset.loaded === 'true') {
      resolve()
      return
    }
    const script = existing || document.createElement('script')
    script.src = XINGYUAN_SDK_URL
    script.async = true
    script.dataset.xingyuanAvatarSdk = 'true'
    script.onload = () => {
      script.dataset.loaded = 'true'
      resolve()
    }
    script.onerror = () => reject(new Error('星元具身 SDK 加载失败'))
    if (!existing) document.head.appendChild(script)
  })
  return xingyuanSdkLoading
}

async function initXingyuanSdkRenderer() {
  const mount = xingyuanSdkMountRef.value
  if (!mount || xingyuanSdkInstance) return
  try {
    await loadXingyuanSdk()
    const sdk = getXingyuanSdkGlobal()
    if (!sdk) {
      avatarStatus.value = '星元 SDK 已加载，但未识别到全局对象，请补充官方调用示例'
      return
    }
    const options = {
      container: mount,
      el: mount,
      element: mount,
      gatewayServer: XINGYUAN_GATEWAY_SERVER,
      server: XINGYUAN_GATEWAY_SERVER,
      sessionUrl: XINGYUAN_GATEWAY_SERVER,
    }
    xingyuanSdkInstance = typeof sdk === 'function' ? new sdk(options) : sdk
    const initMethod = ['init', 'create', 'start', 'mount', 'render'].find((name) => typeof xingyuanSdkInstance?.[name] === 'function')
    if (initMethod) {
      await xingyuanSdkInstance[initMethod](options)
      avatarStatus.value = `星元 SDK 已初始化：${initMethod}`
    } else {
      avatarStatus.value = '星元 SDK 已加载，等待官方 init/speak 调用示例'
    }
  } catch (error: any) {
    avatarStatus.value = error?.message || '星元 SDK 初始化失败'
  }
}

async function speakWithXingyuanSdk(text: string) {
  const content = String(text || '').trim()
  if (!content) return false
  await initXingyuanSdkRenderer()
  const target = xingyuanSdkInstance || getXingyuanSdkGlobal()
  if (!target) return false
  const method = ['speak', 'say', 'sendText', 'send_text', 'pushText', 'playText', 'tts'].find((name) => typeof target?.[name] === 'function')
  if (!method) {
    avatarStatus.value = '星元 SDK 已加载，但未找到说话方法，请补充官方 speak 调用示例'
    return false
  }
  try {
    await target[method]({ text: content, sessionId: avatarSessionId, session_id: avatarSessionId })
    avatarStatus.value = `星元数字人正在说话：${method}`
    return true
  } catch {
    try {
      await target[method](content)
      avatarStatus.value = `星元数字人正在说话：${method}`
      return true
    } catch (error: any) {
      avatarStatus.value = error?.message || '星元 SDK 说话调用失败'
      return false
    }
  }
}

async function initXingyuanSdkRendererV2() {
  const mount = xingyuanSdkMountRef.value
  if (!mount || xingyuanSdkInstance) return
  try {
    if (!xingyuanSdkConfig.value?.appId) await loadAvatarConfig()
    await loadXingyuanSdk()
    const sdk = getXingyuanSdkGlobal()
    if (typeof sdk !== 'function') {
      avatarStatus.value = '星元 SDK 已加载，但未找到 XmovAvatar 构造函数'
      xingyuanSdkVisible.value = false
      return
    }
    const sdkConfig = xingyuanSdkConfig.value || {}
    if (!sdkConfig.appId || !sdkConfig.appSecret || !sdkConfig.gatewayServer) {
      avatarStatus.value = sdkConfig.config_error || '星元 SDK 参数不完整'
      xingyuanSdkVisible.value = false
      return
    }
    // Keep the local portrait visible while the remote model is downloading.
    // The SDK may need several seconds before it inserts a canvas/video node.
    xingyuanSdkVisible.value = false
    avatarVideoUrl.value = ''
    mount.replaceChildren()
    xingyuanSdkInstance = new sdk({
      containerId: '#xingyuan-avatar-sdk',
      appId: sdkConfig.appId,
      appSecret: sdkConfig.appSecret,
      gatewayServer: sdkConfig.gatewayServer,
      headers: sdkConfig.headers || {},
      hardwareAcceleration: sdkConfig.hardwareAcceleration || 'prefer-hardware',
      onWidgetEvent(data: any) {
        console.log('XmovAvatar widget event:', data)
      },
      proxyWidget: {
        widget_slideshow(data: any) {
          console.log('XmovAvatar slideshow:', data)
        },
        widget_video(data: any) {
          console.log('XmovAvatar video:', data)
        },
      },
      onNetworkInfo(networkInfo: any) {
        console.log('XmovAvatar network:', networkInfo)
      },
      onMessage(message: any) {
        console.log('XmovAvatar message:', message)
        if (message?.message) avatarStatus.value = String(message.message)
      },
      onStateChange(state: string) {
        avatarStatus.value = `星元数字人状态：${state}`
      },
      onStatusChange(status: any) {
        console.log('XmovAvatar status:', status)
      },
      onStateRenderChange(state: string, duration: number) {
        console.log('XmovAvatar render state:', state, duration)
      },
      onVoiceStateChange(status: string) {
        const voiceStatus = String(status || '').toLowerCase()
        if (isAvatarVoiceStartStatus(voiceStatus)) {
          avatarSpeechStarted = true
          avatarStatus.value = '星元数字人正在说话'
          aiSpeaking.value = true
          stopAvatarVoiceRecognition(false)
          return
        }
        if (isAvatarVoiceEndStatus(voiceStatus)) {
          if (Date.now() < avatarForceSilentUntil) {
            avatarStatus.value = '星元数字人已停止上一段语音'
            return
          }
          avatarStatus.value = '星元数字人语音播放结束'
          finishAvatarSpeech(true)
          return
        }
        avatarStatus.value = `星元数字人语音状态：${status}`
      },
      onStartSessionWarning(message: any) {
        console.log('XmovAvatar session warning:', message)
        avatarStatus.value = '星元数字人配置警告，请检查应用角色、音色或风格'
      },
      enableLogger: false,
    })
    if (typeof xingyuanSdkInstance.init !== 'function') {
      avatarStatus.value = '星元 SDK 实例缺少 init 方法'
      xingyuanSdkVisible.value = false
      return
    }
    await xingyuanSdkInstance.init({
      initModel: 'normal',
      onDownloadProgress(progress: number) {
        avatarStatus.value = `星元数字人资源加载 ${Math.round(Number(progress) || 0)}%`
      },
    })
    await nextTick()
    const renderedSurface = mount.querySelector('canvas, video, iframe, [data-xmov-renderer]')
    xingyuanSdkVisible.value = Boolean(renderedSurface || mount.childElementCount)
    avatarStatus.value = '星元 SDK 已初始化'
  } catch (error: any) {
    avatarStatus.value = error?.message || '星元 SDK 初始化失败'
    xingyuanSdkVisible.value = false
    xingyuanSdkInstance = null
  }
}

async function speakWithXingyuanSdkV2(text: string) {
  const content = String(text || '').trim()
  if (!content) return false
  await initXingyuanSdkRendererV2()
  if (!xingyuanSdkInstance || typeof xingyuanSdkInstance.speak !== 'function') {
    avatarStatus.value = '星元 SDK 实例未就绪或缺少 speak 方法'
    return false
  }
  try {
    const settleMs = avatarForceSilentUntil - Date.now()
    if (settleMs > 0) {
      avatarStatus.value = '星元数字人正在准备下一次回答'
      await sleep(Math.min(settleMs, 1800))
    }
    const speechTurn = beginAvatarSpeechWatch(content)
    xingyuanSdkInstance.speak(content, true, true)
    avatarStatus.value = '星元数字人正在说话'
    await waitAvatarSpeechFinish(content, speechTurn)
    return true
  } catch (error: any) {
    finishAvatarSpeech(false)
    avatarStatus.value = error?.message || '星元 SDK 说话调用失败'
    return false
  }
}

function isAvatarVoiceStartStatus(status: string) {
  return /^(start|started|begin|speaking|speak|play|playing)$/i.test(status)
}

function isAvatarVoiceEndStatus(status: string) {
  return /^(end|ended|finish|finished|stop|stopped|complete|completed|idle)$/i.test(status)
}

function beginAvatarSpeechWatch(text: string) {
  finishAvatarSpeech(false)
  const speechTurn = ++avatarSpeechTurn
  if (avatarSpeechFinishTimer) window.clearTimeout(avatarSpeechFinishTimer)
  if (avatarSpeechStartTimer) window.clearTimeout(avatarSpeechStartTimer)
  avatarSpeechFinishTimer = null
  avatarSpeechStartTimer = null
  avatarSpeechFinishResolve = null
  avatarSpeechStarted = false
  aiSpeaking.value = true
  stopAvatarVoiceRecognition(false)
  const estimatedMs = Math.min(18000, Math.max(2600, String(text || '').length * 180))
  avatarSpeechStartTimer = window.setTimeout(() => {
    if (speechTurn !== avatarSpeechTurn || avatarSpeechStarted || !aiSpeaking.value) return
    avatarStatus.value = '星元数字人正在合成语音'
  }, 1800)
  avatarSpeechFinishTimer = window.setTimeout(() => finishAvatarSpeech(true, speechTurn), estimatedMs)
  return speechTurn
}

function finishAvatarSpeech(shouldResumeListening: boolean, speechTurn = avatarSpeechTurn) {
  if (speechTurn !== avatarSpeechTurn) return
  if (!aiSpeaking.value && !avatarSpeechFinishResolve) return
  if (avatarSpeechFinishTimer) window.clearTimeout(avatarSpeechFinishTimer)
  if (avatarSpeechStartTimer) window.clearTimeout(avatarSpeechStartTimer)
  avatarSpeechFinishTimer = null
  avatarSpeechStartTimer = null
  aiSpeaking.value = false
  avatarSpeechStarted = false
  const resolve = avatarSpeechFinishResolve
  avatarSpeechFinishResolve = null
  if (resolve) resolve()
  if (shouldResumeListening && avatarVoiceMode.value && connected.value && !micMuted.value) {
    scheduleAvatarVoiceRecognitionRestart(500)
  }
}

function waitAvatarSpeechFinish(text: string, speechTurn: number) {
  const maxMs = Math.min(20000, Math.max(3200, String(text || '').length * 210))
  return new Promise<void>((resolve) => {
    avatarSpeechFinishResolve = resolve
    window.setTimeout(() => finishAvatarSpeech(true, speechTurn), maxMs)
  })
}

async function startAvatarSession() {
  if (!avatarConfig.value?.enabled || avatarSessionId || avatarSessionStarting) return
  avatarSessionStarting = true
  try {
    const response = await fetch('/api/avatar/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_id: studentId.value,
        meta: { source: 'realtime_tutor' },
      }),
    })
    const data = await response.json().catch(() => ({}))
    avatarSessionId = findAvatarSessionId(data)
    const videoUrl = findAvatarVideoUrl(data)
    if (videoUrl) avatarVideoUrl.value = videoUrl
    avatarStatus.value = data.success === false ? (data.error || '数字人会话创建失败') : '数字人会话已建立'
  } catch (error: any) {
    avatarStatus.value = error?.message || '数字人会话创建失败'
  } finally {
    avatarSessionStarting = false
  }
}

function sanitizeAvatarSpeech(text: string) {
  return String(text || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/[*_~>|-]/g, ' ')
    .replace(/[<>{}[\]\\^]/g, ' ')
    .replace(/&/g, '和')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 520)
}

async function sendAvatarSpeak(text: string) {
  const content = sanitizeAvatarSpeech(text)
  if (!content || !xingyuanSdkConfigured.value) return false
  const spoken = await speakWithXingyuanSdkV2(content)
  if (!spoken) {
    setStatus(avatarStatus.value || '数字人老师语音调用失败', 'error')
  }
  return spoken
}

function getSpeechRecognitionCtor() {
  const root = window as any
  return root.SpeechRecognition || root.webkitSpeechRecognition
}

function scheduleAvatarVoiceRecognitionRestart(delay = 450) {
  if (avatarRecognitionRestartTimer) window.clearTimeout(avatarRecognitionRestartTimer)
  avatarRecognitionRestartTimer = window.setTimeout(() => {
    avatarRecognitionRestartTimer = null
    if (!avatarRecognitionShouldRun || !connected.value || !avatarVoiceMode.value || micMuted.value) return
    if (aiSpeaking.value) {
      scheduleAvatarVoiceRecognitionRestart(800)
      return
    }
    startAvatarVoiceRecognition()
  }, delay)
}

function stopAvatarVoiceRecognition(permanent = true) {
  if (permanent) avatarRecognitionShouldRun = false
  if (avatarRecognitionRestartTimer) {
    window.clearTimeout(avatarRecognitionRestartTimer)
    avatarRecognitionRestartTimer = null
  }
  avatarRecognitionStarting = false
  if (!avatarRecognition) return
  try { avatarRecognition.stop() } catch {}
}

function startAvatarInterruptMonitor() {
  if (!audioContext || !localStream || avatarInterruptAnalyser) return
  try {
    avatarInterruptSource = audioContext.createMediaStreamSource(localStream)
    avatarInterruptAnalyser = audioContext.createAnalyser()
    avatarInterruptAnalyser.fftSize = 1024
    avatarInterruptSource.connect(avatarInterruptAnalyser)
    const samples = new Uint8Array(avatarInterruptAnalyser.fftSize)
    const tick = () => {
      if (!avatarInterruptAnalyser) return
      avatarInterruptAnalyser.getByteTimeDomainData(samples)
      let sum = 0
      for (let i = 0; i < samples.length; i += 1) {
        const centered = (samples[i] - 128) / 128
        sum += centered * centered
      }
      const level = Math.sqrt(sum / samples.length)
      if (
        avatarVoiceMode.value
        && connected.value
        && aiSpeaking.value
        && !micMuted.value
        && Date.now() > avatarForceSilentUntil
        && level > 0.09
        && Date.now() - avatarLastInterruptAt > 1200
      ) {
        avatarLastInterruptAt = Date.now()
        void interruptAi()
      }
      avatarInterruptFrame = window.requestAnimationFrame(tick)
    }
    avatarInterruptFrame = window.requestAnimationFrame(tick)
  } catch {
    avatarInterruptAnalyser = null
    avatarInterruptSource = null
  }
}

function stopAvatarInterruptMonitor() {
  if (avatarInterruptFrame) window.cancelAnimationFrame(avatarInterruptFrame)
  avatarInterruptFrame = 0
  if (avatarInterruptSource) {
    try { avatarInterruptSource.disconnect() } catch {}
    avatarInterruptSource = null
  }
  if (avatarInterruptAnalyser) {
    try { avatarInterruptAnalyser.disconnect() } catch {}
    avatarInterruptAnalyser = null
  }
}

function startAvatarVoiceRecognition() {
  if (!avatarVoiceMode.value || !connected.value || micMuted.value || aiSpeaking.value || avatarRecognitionStarting) return
  const RecognitionCtor = getSpeechRecognitionCtor()
  if (!RecognitionCtor) {
    setStatus('当前浏览器不支持语音识别，请使用新版 Chrome 或 Edge。', 'error')
    return
  }
  avatarRecognitionShouldRun = true
  avatarRecognitionStarting = true
  if (!avatarRecognition) {
    avatarRecognition = new RecognitionCtor()
    avatarRecognition.lang = 'zh-CN'
    avatarRecognition.continuous = true
    avatarRecognition.interimResults = true
    avatarRecognition.maxAlternatives = 1
    avatarRecognition.onaudiostart = () => {
      userSpeaking.value = true
      setStatus('数字人老师语音通话中，正在听你说话')
    }
    avatarRecognition.onspeechend = () => {
      userSpeaking.value = false
    }
    avatarRecognition.onerror = (event: any) => {
      avatarRecognitionStarting = false
      userSpeaking.value = false
      const error = String(event?.error || '')
      if (error === 'no-speech' || error === 'aborted') {
        scheduleAvatarVoiceRecognitionRestart(800)
        return
      }
      setStatus(`数字人老师语音识别失败：${error || '未知错误'}`, 'error')
    }
    avatarRecognition.onend = () => {
      avatarRecognitionStarting = false
      userSpeaking.value = false
      if (avatarRecognitionShouldRun && connected.value && avatarVoiceMode.value && !micMuted.value && !aiSpeaking.value) {
        scheduleAvatarVoiceRecognitionRestart()
      }
    }
    avatarRecognition.onresult = (event: any) => {
      let finalText = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        const text = String(result?.[0]?.transcript || '').trim()
        if (result?.isFinal && text) finalText += text
      }
      if (finalText) void handleAvatarVoiceQuestion(finalText)
    }
  }
  try {
    avatarRecognition.start()
    setStatus('数字人老师语音通话中，正在听你说话')
  } catch {
    avatarRecognitionStarting = false
  }
}

function extractTutorAnswer(payload: any): string {
  const data = payload?.data ?? payload
  const answer = data?.answer ?? data?.result?.answer ?? data?.result ?? data
  if (typeof answer === 'string') return answer
  if (answer && typeof answer === 'object') {
    for (const key of ['answer', 'text', 'summary', 'content', 'explanation']) {
      if (typeof answer[key] === 'string' && answer[key].trim()) return answer[key]
    }
  }
  return ''
}

async function streamTutorAnswer(question: string, onChunk: (chunk: string) => void) {
  const response = await fetch('/api/tutor/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      student_id: studentId.value,
      question,
      context: {
        source: 'xingyuan_avatar_voice',
        answer_style: 'short_voice_reply',
        instruction: '只回答当前问题，简短自然。可以回答高等数学等通用知识问题。不要主动提学习画像或学习记录，不要说知识库不支持，不要把话题转回软件工程或需求分析。',
        recent_messages: conversation.value.slice(-8).map((item) => ({ role: item.role, content: item.content })),
      },
    }),
  })
  if (!response.ok || !response.body) {
    throw new Error(`智能辅导回答生成失败：HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let finalAnswer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''
    for (const rawEvent of events) {
      const dataLine = rawEvent.split('\n').find((line) => line.startsWith('data:'))
      if (!dataLine) continue
      const payload = JSON.parse(dataLine.slice(5).trim())
      if (payload.event === 'chunk') {
        const chunk = String(payload.data?.text || '')
        if (chunk) {
          finalAnswer += chunk
          onChunk(chunk)
        }
      } else if (payload.event === 'final') {
        const finalText = extractTutorAnswer(payload.data?.result)
        if (finalText) finalAnswer = finalText
      } else if (payload.event === 'error') {
        throw new Error(payload.data?.message || '智能辅导回答生成失败')
      }
    }
  }

  return finalAnswer.trim()
}

async function handleAvatarVoiceQuestion(text: string) {
  const question = String(text || '').trim()
  if (!question || avatarVoiceAskPending) return
  avatarVoiceAskPending = true
  stopAvatarVoiceRecognition(false)
  appendConversation('user', question)
  const assistantId = appendAssistantDraft()
  let streamedAnswer = ''
  setStatus('已收到你的问题，正在生成回答...')
  try {
    const answer = await streamTutorAnswer(question, (chunk) => {
      streamedAnswer += chunk
      updateConversationContent(assistantId, streamedAnswer)
    }) || streamedAnswer || '我先记下这个问题，我们换一种说法继续讲。'
    updateConversationContent(assistantId, answer)
    setStatus('数字人老师正在回答')
    aiSpeaking.value = true
    const spoken = await sendAvatarSpeak(answer)
    if (spoken) scheduleAvatarVoiceRecognitionRestart(1600)
  } catch (error: any) {
    setStatus(error?.message || '语音问题处理失败', 'error')
    scheduleAvatarVoiceRecognitionRestart(1200)
  } finally {
    avatarVoiceAskPending = false
  }
}

async function interruptAvatar() {
  const sdkMethod = ['interrupt', 'stopSpeak', 'stop_speak', 'cancelSpeak', 'cancel_speak'].find((name) => typeof xingyuanSdkInstance?.[name] === 'function')
  if (sdkMethod) {
    try {
      await xingyuanSdkInstance[sdkMethod]()
      avatarStatus.value = '星元数字人已停止当前语音'
      return
    } catch {
    }
  }
  if (!avatarConfig.value?.enabled || !avatarSessionId) return
  try {
    await fetch('/api/avatar/interrupt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: avatarSessionId }),
    })
  } catch {
  }
}

async function stopAvatarSession() {
  if (xingyuanSdkInstance && typeof xingyuanSdkInstance.destroy === 'function') {
    try {
      xingyuanSdkInstance.destroy()
    } catch {
    }
  }
  xingyuanSdkInstance = null
  xingyuanSdkVisible.value = false
  if (!avatarSessionId) return
  const sessionId = avatarSessionId
  avatarSessionId = ''
  try {
    await fetch('/api/avatar/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    })
  } catch {
  }
}

function collectConversationEvent(event: any) {
  const type = String(event?.type || '')
  const transcript = extractTranscript(event)
  if (transcript) {
    if (type.includes('input_audio') || type.includes('input_audio_transcription') || type.includes('conversation.item.input')) {
      appendConversation('user', transcript)
    } else {
      pendingAssistantText += transcript
    }
  }

  const textDelta = event.text || event.delta?.text || event.delta?.content
  if (typeof textDelta === 'string' && (type.includes('response.text.delta') || type.includes('response.output_text.delta'))) {
    pendingAssistantText += textDelta
  }

  if (type.includes('response.text.done') || type.includes('response.output_text.done') || type.includes('response.done')) {
    const finalText = event.text || event.transcript || pendingAssistantText
    if (finalText) {
      appendConversation('assistant', finalText)
      void sendAvatarSpeak(finalText)
    }
    pendingAssistantText = ''
  }
}

function extractTranscript(event: any): string {
  const candidates = [
    event.transcript,
    event.text,
    event.item?.content?.[0]?.transcript,
    event.content?.[0]?.transcript,
    event.response?.output?.[0]?.content?.[0]?.transcript,
  ]
  const value = candidates.find((item) => typeof item === 'string' && item.trim())
  return value ? String(value).trim() : ''
}

async function saveConversationSession() {
  if (sessionSaved || conversation.value.length === 0) return
  sessionSaved = true
  saveStatus.value = '正在保存本次辅导对话...'
  try {
    const payload = {
      student_id: studentId.value,
      started_at: sessionStartedAt,
      ended_at: new Date().toISOString(),
      messages: conversation.value.map((item) => ({
        role: item.role,
        content: item.content,
        timestamp: item.timestamp,
      })),
      meta: { source: 'realtime_voice_call' },
    }
    const response = await fetch('/api/tutor/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await response.json().catch(() => ({}))
    if (data.success) {
      const weakPoints = data.data?.analysis?.weak_points || []
      saveStatus.value = weakPoints.length
        ? `已保存对话，并提取薄弱点：${weakPoints.slice(0, 3).join('、')}`
        : '已保存对话，等待更多证据用于画像迭代。'
    } else {
      sessionSaved = false
      saveStatus.value = data.error?.message || '对话保存失败'
    }
  } catch (error: any) {
    sessionSaved = false
    saveStatus.value = error?.message || '对话保存失败'
  }
}

async function loadConfig() {
  try {
    const response = await fetch('/api/voice/realtime/config')
    const data = await response.json().catch(() => ({}))
    config.value = data
    if (data.config_error) {
      if (xingyuanSdkConfigured.value) {
        setStatus('已切换为数字人老师语音，可以开始通话。')
      } else {
        setStatus(`语音辅导配置错误：${data.config_error}`, 'error')
      }
    } else if (data.transport !== 'websocket') {
      setStatus('当前语音辅导连接不是 WebSocket 地址，请配置 wss:// 地址。', 'error')
    } else {
      setStatus('配置已就绪，可以开始通话。')
    }
  } catch (error: any) {
    setStatus(`读取配置失败：${error?.message || '网络错误'}`, 'error')
  }
}

async function startCall() {
  if (connecting.value || connected.value) return
  connecting.value = true
  conversation.value = []
  saveStatus.value = ''
  pendingAssistantText = ''
  sessionStartedAt = new Date().toISOString()
  sessionSaved = true
  setStatus('正在请求摄像头和麦克风...')
  try {
    localStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        facingMode: 'user',
      },
    })
    localStreamReady.value = true
    micMuted.value = false
    cameraOff.value = false
    if (localVideoRef.value) {
      localVideoRef.value.srcObject = localStream
      await localVideoRef.value.play().catch(() => {})
    }

    const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext
    audioContext = new AudioContextCtor()
    if (audioContext.state === 'suspended') await audioContext.resume().catch(() => {})
    playbackTime = audioContext.currentTime

    if (avatarVoiceMode.value) {
      await initXingyuanSdkRendererV2()
      connected.value = true
      avatarRecognitionShouldRun = true
      setStatus('数字人老师语音通话中')
      logEvent('已启用数字人老师语音')
      const greeted = await sendAvatarSpeak('你好，我是数字人老师。你可以直接说出问题，我会听你说完后回答。')
      if (!greeted) {
        setStatus(avatarStatus.value || '数字人老师语音未成功播放', 'error')
        return
      }
      startAvatarInterruptMonitor()
      scheduleAvatarVoiceRecognitionRestart(1200)
      return
    }

    await openRealtimeSocket()
    void initXingyuanSdkRendererV2()
  } catch (error: any) {
    setStatus(error?.message || '无法建立通话', 'error')
    logEvent(`连接失败：${error?.message || '未知错误'}`)
    endCall()
  } finally {
    connecting.value = false
  }
}

function openRealtimeSocket() {
  return new Promise<void>((resolve, reject) => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}${config.value.ws_path || '/api/voice/realtime/ws'}`
    ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'
    realtimeConnectSettled = false
    upstreamHadError = false
    realtimeClosedNormally = false

    const timeout = window.setTimeout(() => {
      if (!realtimeConnectSettled) {
        realtimeConnectSettled = true
        reject(new Error('语音辅导连接超时'))
      }
    }, 12000)

    ws.onopen = () => {
      window.clearTimeout(timeout)
      realtimeConnectSettled = true
      connected.value = true
      setStatus('正在连接语音辅导服务...')
      logEvent('已连接语音辅导服务，等待课堂就绪')
      resolve()
    }
    ws.onmessage = (event) => handleRealtimeMessage(event.data)
    ws.onerror = () => {
      window.clearTimeout(timeout)
      if (!realtimeConnectSettled) {
        realtimeConnectSettled = true
        reject(new Error('浏览器无法连接语音辅导服务'))
      }
    }
    ws.onclose = () => {
      window.clearTimeout(timeout)
      connected.value = false
      upstreamReady = false
      aiSpeaking.value = false
      userSpeaking.value = false
      if (!realtimeConnectSettled) {
        realtimeConnectSettled = true
        reject(new Error('语音辅导连接在建立前已关闭'))
        return
      }
      if (!realtimeClosedNormally && statusKind.value !== 'error') setStatus('通话已断开')
      if (!realtimeClosedNormally && !upstreamHadError) logEvent('通话连接已关闭')
      void saveConversationSession()
    }
  })
}

function sendSessionUpdate() {
  sendRealtimeEvent({
    type: 'session.update',
    session: {
      model: config.value.model,
      voice: 'tongtong',
      chat_mode: 'audio',
      modalities: ['audio', 'text'],
      instructions: '你是通用智能辅导老师。请用自然中文短句交流，直接回答用户当前问题；学生随时可能插话打断，一旦被打断，立刻停止当前回答并回应学生最新内容。',
      input_audio_format: 'pcm16',
      output_audio_format: 'pcm',
      turn_detection: {
        type: 'server_vad',
        interrupt_response: true,
        create_response: true,
      },
      beta_fields: {
        chat_mode: 'audio',
        tts_source: 'e2e',
      },
    },
  })
}

function startMicrophoneStreaming() {
  if (!audioContext || !localStream || processorNode) return
  sourceNode = audioContext.createMediaStreamSource(localStream)
  processorNode = audioContext.createScriptProcessor(4096, 1, 1)
  processorNode.onaudioprocess = (event) => {
    if (!connected.value || micMuted.value || !audioContext) return
    const mono = mixInputBufferToMono(event.inputBuffer)
    const level = rms(mono)
    if (level > 0.025) {
      markUserSpeaking()
      if (aiSpeaking.value && Date.now() > interruptCooldown) {
        interruptCooldown = Date.now() + 1200
        interruptAi()
      }
    }
    const pcm16 = floatToPcm16(resample(mono, audioContext.sampleRate, INPUT_SAMPLE_RATE))
    sendRealtimeEvent({
      type: 'input_audio_buffer.append',
      audio: arrayBufferToBase64(pcm16.buffer),
    })
  }
  sourceNode.connect(processorNode)
  processorNode.connect(audioContext.destination)
}

function handleRealtimeMessage(raw: string | ArrayBuffer) {
  if (raw instanceof ArrayBuffer) {
    playPcm16(raw, OUTPUT_SAMPLE_RATE)
    return
  }

  let event: any
  try {
    event = JSON.parse(raw)
  } catch {
    logEvent(String(raw).slice(0, 160))
    return
  }

  if (event.type === 'proxy.connected') {
    upstreamReady = true
    setStatus('通话中')
    logEvent('AI 辅导老师已进入课堂')
    sendSessionUpdate()
    startMicrophoneStreaming()
    return
  }

  if (event.type === 'proxy.closed') {
    upstreamReady = false
    const message = event.error || event.reason || '语音辅导连接已关闭'
    if (isNormalRealtimeClose(message)) {
      realtimeClosedNormally = true
      return
    }
    if (isExpectedCancelError(message)) {
      setStatus('已打断 AI，正在等待你继续说话')
      logEvent('AI 已停止上一段回答')
    } else {
      upstreamHadError = true
      setStatus(message, 'error')
      logEvent(message)
    }
    return
  }

  if (event.type?.includes('error') || event.error) {
    const message = event.error?.message || event.error || event.message || event.type
    if (isNormalRealtimeClose(message)) {
      realtimeClosedNormally = true
      return
    }
    if (isExpectedCancelError(message)) {
      setStatus('已打断 AI，正在等待你继续说话')
      logEvent('AI 已停止上一段回答')
      return
    }
    upstreamHadError = true
    setStatus(`语音辅导错误：${message}`, 'error')
    logEvent(`错误：${message}`)
    return
  }

  const audioDelta = event.delta || event.audio || event.data
  if (typeof audioDelta === 'string' && event.type?.includes('audio')) {
    playPcm16(base64ToArrayBuffer(audioDelta), OUTPUT_SAMPLE_RATE)
  }
  if (event.type?.includes('response.audio') || event.type?.includes('audio.delta')) markAiSpeaking()
  if (event.type?.includes('response.done') || event.type?.includes('audio.done')) aiSpeaking.value = false
  if (event.type?.includes('speech_started')) markUserSpeaking()
  collectConversationEvent(event)
}

function sendRealtimeEvent(payload: Record<string, any>) {
  if (!ws || ws.readyState !== WebSocket.OPEN || !upstreamReady) return false
  ws.send(JSON.stringify({
    event_id: payload.event_id || `event_${Date.now()}_${++eventId}`,
    client_timestamp: Date.now(),
    ...payload,
  }))
  return true
}

function interruptAi() {
  stopQueuedPlayback()
  if (avatarVoiceMode.value) {
    avatarForceSilentUntil = Date.now() + 2200
    finishAvatarSpeech(false)
    aiSpeaking.value = false
    setStatus('已打断数字人老师，等待继续互动')
    void interruptAvatar()
    scheduleAvatarVoiceRecognitionRestart(250)
    return
  }
  pendingInterruptUntil = Date.now() + 8000
  const sent = sendRealtimeEvent({ type: 'response.cancel' })
  if (sent) {
    logEvent('已发送打断指令')
    setStatus('已打断 AI，正在听你说话')
    aiSpeaking.value = false
    void interruptAvatar()
  }
}

function isExpectedCancelError(message: string) {
  if (Date.now() > pendingInterruptUntil) return false
  return /context canceled|cancelled|canceled|response\.cancel/i.test(String(message || ''))
}

function isNormalRealtimeClose(message: string) {
  return /1000\s*\(OK\)|ConnectionClosedOK|proxy\.closed|normal/i.test(String(message || ''))
}

function markAiSpeaking() {
  aiSpeaking.value = true
}

function markUserSpeaking() {
  userSpeaking.value = true
  if (silenceTimer) window.clearTimeout(silenceTimer)
  silenceTimer = window.setTimeout(() => {
    userSpeaking.value = false
  }, 650)
}

function startDigitalHumanRenderer() {
  const canvas = digitalHumanCanvasRef.value
  if (!canvas || digitalHumanFrame) return

  const image = new Image()
  image.src = '/assets/digital-human-tutor.jpg'
  digitalHumanImage = image

  const resize = () => resizeDigitalHumanCanvas()
  digitalHumanResizeObserver = new ResizeObserver(resize)
  digitalHumanResizeObserver.observe(canvas)
  image.onload = () => {
    resize()
    digitalHumanFrame = window.requestAnimationFrame(drawDigitalHumanFrame)
  }
}

function stopDigitalHumanRenderer() {
  if (digitalHumanFrame) window.cancelAnimationFrame(digitalHumanFrame)
  digitalHumanFrame = 0
  digitalHumanResizeObserver?.disconnect()
  digitalHumanResizeObserver = null
}

function resizeDigitalHumanCanvas() {
  const canvas = digitalHumanCanvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const width = Math.max(1, Math.round(rect.width * dpr))
  const height = Math.max(1, Math.round(rect.height * dpr))
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width
    canvas.height = height
  }
}

function drawDigitalHumanFrame(time: number) {
  const canvas = digitalHumanCanvasRef.value
  const image = digitalHumanImage
  const ctx = canvas?.getContext('2d')
  if (!canvas || !image || !ctx || !image.complete) {
    digitalHumanFrame = window.requestAnimationFrame(drawDigitalHumanFrame)
    return
  }

  const dpr = canvas.width / Math.max(1, canvas.clientWidth)
  const width = canvas.width / dpr
  const height = canvas.height / dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'

  const scale = width / image.width
  const sourceHeight = Math.min(image.height, height / scale)
  const rows = 120
  const speaking = aiSpeaking.value ? 1 : 0
  const listening = userSpeaking.value ? 1 : 0
  const phase = time / 1000
  const headTurn = Math.sin(phase * 0.9) * (5.2 + speaking * 1.4)
  const headNod = Math.sin(phase * 1.35 + 0.4) * (3.2 + speaking * 1.8)
  const breath = Math.sin(phase * 1.5) * (1.7 + speaking * 0.8)
  const attention = listening ? Math.sin(phase * 2.1) * 2.2 : 0
  const mouthOpen = speaking ? 0.45 + Math.abs(Math.sin(phase * 15.5)) * 0.55 : 0

  for (let i = 0; i < rows; i += 1) {
    const y = (height * i) / rows
    const nextY = (height * (i + 1)) / rows
    const rowHeight = nextY - y + 1.4
    const v = y / height
    const sourceY = y / scale
    const sourceRowHeight = rowHeight / scale
    if (sourceY >= sourceHeight) continue

    const headWeight = Math.max(0, 1 - Math.abs(v - 0.2) / 0.22)
    const shoulderWeight = Math.max(0, 1 - Math.abs(v - 0.47) / 0.32)
    const jawWeight = Math.max(0, 1 - Math.abs(v - 0.262) / 0.045)
    const lowerBodyWeight = Math.max(0, 1 - Math.abs(v - 0.68) / 0.35)
    const horizontalCurve = Math.sin((v - 0.08) * Math.PI) * 1.4
    const dx = headTurn * headWeight + attention * headWeight * 0.45 + horizontalCurve * lowerBodyWeight
    const dy = -headNod * headWeight + breath * shoulderWeight + mouthOpen * jawWeight * 3.2
    const scaleX = 1 + shoulderWeight * Math.sin(phase * 1.5) * 0.003 + jawWeight * mouthOpen * 0.006

    ctx.drawImage(
      image,
      0,
      sourceY,
      image.width,
      Math.min(sourceRowHeight + 2 / scale, sourceHeight - sourceY),
      dx - ((scaleX - 1) * width) / 2,
      y + dy,
      width * scaleX,
      rowHeight,
    )
  }

  const glow = ctx.createRadialGradient(width * 0.5, height * 0.22, 2, width * 0.5, height * 0.22, width * 0.24)
  glow.addColorStop(0, `rgba(255,255,255,${0.08 + speaking * 0.06})`)
  glow.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, width, height)

  if (mouthOpen > 0.02) {
    const mouthX = width * 0.5 + headTurn * 0.42
    const mouthY = height * 0.237 - headNod * 0.2
    ctx.save()
    ctx.globalCompositeOperation = 'multiply'
    ctx.globalAlpha = 0.24 + mouthOpen * 0.32
    ctx.fillStyle = '#8d263a'
    ctx.beginPath()
    ctx.ellipse(mouthX, mouthY + mouthOpen * 2.2, 11 + mouthOpen * 2.5, 2.5 + mouthOpen * 4.5, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
  }

  digitalHumanFrame = window.requestAnimationFrame(drawDigitalHumanFrame)
}

function mixInputBufferToMono(inputBuffer: AudioBuffer) {
  const channelCount = Math.max(1, inputBuffer.numberOfChannels || 1)
  const length = inputBuffer.length
  const mono = new Float32Array(length)
  for (let channel = 0; channel < channelCount; channel += 1) {
    const data = inputBuffer.getChannelData(channel)
    for (let i = 0; i < length; i += 1) mono[i] += data[i] / channelCount
  }
  return mono
}

function rms(samples: Float32Array) {
  let sum = 0
  for (let i = 0; i < samples.length; i += 1) sum += samples[i] * samples[i]
  return Math.sqrt(sum / samples.length)
}

function resample(samples: Float32Array, sourceRate: number, targetRate: number) {
  if (sourceRate === targetRate) return samples
  const ratio = sourceRate / targetRate
  const length = Math.max(1, Math.round(samples.length / ratio))
  const result = new Float32Array(length)
  for (let i = 0; i < length; i += 1) {
    const sourceIndex = i * ratio
    const left = Math.floor(sourceIndex)
    const right = Math.min(left + 1, samples.length - 1)
    const weight = sourceIndex - left
    result[i] = samples[left] * (1 - weight) + samples[right] * weight
  }
  return result
}

function floatToPcm16(samples: Float32Array) {
  const pcm = new Int16Array(samples.length)
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }
  return pcm
}

function playPcm16(buffer: ArrayBuffer, sampleRate: number) {
  if (!audioContext || !buffer.byteLength) return
  const pcm = new Int16Array(buffer)
  const audioBuffer = audioContext.createBuffer(1, pcm.length, sampleRate)
  const channel = audioBuffer.getChannelData(0)
  for (let i = 0; i < pcm.length; i += 1) channel[i] = pcm[i] / 0x8000

  const source = audioContext.createBufferSource()
  source.buffer = audioBuffer
  source.connect(audioContext.destination)
  const startAt = Math.max(audioContext.currentTime + 0.02, playbackTime)
  playbackSources.add(source)
  source.start(startAt)
  playbackTime = startAt + audioBuffer.duration
  markAiSpeaking()
  source.onended = () => {
    playbackSources.delete(source)
    if (audioContext && playbackTime <= audioContext.currentTime + 0.05) aiSpeaking.value = false
  }
}

function stopQueuedPlayback() {
  for (const source of playbackSources) {
    try { source.stop() } catch {}
    try { source.disconnect() } catch {}
  }
  playbackSources.clear()
  if (audioContext) playbackTime = audioContext.currentTime
  aiSpeaking.value = false
}

function arrayBufferToBase64(buffer: ArrayBufferLike) {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i])
  return btoa(binary)
}

function base64ToArrayBuffer(base64: string) {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes.buffer
}

function toggleMic() {
  const tracks = localStream?.getAudioTracks() || []
  micMuted.value = !micMuted.value
  for (const track of tracks) track.enabled = !micMuted.value
  if (avatarVoiceMode.value && connected.value) {
    if (micMuted.value) {
      stopAvatarVoiceRecognition(false)
    } else {
      startAvatarInterruptMonitor()
      startAvatarVoiceRecognition()
    }
  }
}

function toggleCamera() {
  const tracks = localStream?.getVideoTracks() || []
  cameraOff.value = !cameraOff.value
  for (const track of tracks) track.enabled = !cameraOff.value
}

async function endCall() {
  if (silenceTimer) window.clearTimeout(silenceTimer)
  silenceTimer = null
  stopAvatarVoiceRecognition()
  stopAvatarInterruptMonitor()
  if (processorNode) {
    try { processorNode.disconnect() } catch {}
    processorNode.onaudioprocess = null
    processorNode = null
  }
  if (sourceNode) {
    try { sourceNode.disconnect() } catch {}
    sourceNode = null
  }
  if (ws) {
    try { ws.close() } catch {}
    ws = null
  }
  upstreamReady = false
  if (localStream) {
    localStream.getTracks().forEach((track) => track.stop())
    localStream = null
  }
  stopQueuedPlayback()
  if (audioContext) {
    try { audioContext.close() } catch {}
    audioContext = null
  }
  if (localVideoRef.value) localVideoRef.value.srcObject = null
  connected.value = false
  connecting.value = false
  localStreamReady.value = false
  micMuted.value = false
  cameraOff.value = false
  aiSpeaking.value = false
  userSpeaking.value = false
  if (statusKind.value !== 'error') setStatus('通话已结束')
  await stopAvatarSession()
  await saveConversationSession()
}

onMounted(async () => {
  await loadAvatarConfig()
  await loadConfig()
  await nextTick()
  // The remote renderer is started on explicit user action. This keeps page
  // loading deterministic when the vendor CDN is slow or temporarily down.
})
onBeforeUnmount(() => {
  void endCall()
})
</script>

<template>
  <section class="studio-panel realtime-tutor-panel">
    <div class="studio-panel-header">
      <div>
        <div class="studio-title"><span class="studio-title-dot green"></span>实时视频辅导</div>
        <p>面向比赛录屏的沉浸式辅导场景，支持摄像头、麦克风、语音打断和对话留痕分析。</p>
      </div>
      <div class="realtime-status-chip" :class="{ error: statusKind === 'error', live: connected }">
        {{ connected ? '通话中' : statusKind === 'error' ? '需配置' : '待开始' }}
      </div>
    </div>

    <div class="studio-panel-body realtime-tutor-body">
      <div class="realtime-call-grid">
        <main class="realtime-ai-room" :class="{ connected, 'sdk-ready': xingyuanSdkConfigured }">
          <div class="realtime-room-head">
            <div>
              <strong>AI 辅导老师</strong>
              <span>实时课堂助手</span>
            </div>
            <small>{{ statusText }}</small>
          </div>

          <div class="realtime-ai-stage">
            <div class="realtime-avatar digital-human" aria-label="AI 数字人辅导老师">
              <span class="digital-human-space back"></span>
              <span class="digital-human-space mid"></span>
              <span class="digital-human-space front"></span>
              <span class="digital-human-depth-panel left"></span>
              <span class="digital-human-depth-panel right"></span>
              <span class="digital-human-glow"></span>
              <span class="digital-human-floor"></span>
              <div class="digital-human-portrait" :class="{ 'sdk-visible': xingyuanSdkVisible && connected }">
                <div class="digital-human-rig" role="img" aria-label="数字人静态预览图"></div>
                <div
                  id="xingyuan-avatar-sdk"
                  ref="xingyuanSdkMountRef"
                  class="digital-human-sdk-mount xingyuan-center-lock"
                  :class="{ 'sdk-visible': xingyuanSdkVisible && connected }"
                ></div>
                <video
                  v-if="false"
                  class="digital-human-video"
                  :src="avatarVideoUrl"
                  autoplay
                  playsinline
                  muted
                  loop
                ></video>
                <canvas v-show="false" ref="digitalHumanCanvasRef" class="digital-human-canvas" aria-label="AI 数字人辅导老师"></canvas>
                <span class="digital-human-eye-shine left"></span>
                <span class="digital-human-eye-shine right"></span>
                <span class="digital-human-light-sweep"></span>
              </div>
              <div class="digital-human-speech" aria-hidden="true">
                <i v-for="n in 7" :key="n" :style="{ animationDelay: `${n * 0.06}s` }"></i>
              </div>
            </div>
            <div
              v-if="avatarVoiceMode"
              class="realtime-wave realtime-avatar-wave"
              :class="{ speaking: aiSpeaking, listening: userSpeaking, idle: !aiSpeaking && !userSpeaking }"
              aria-label="数字人老师语音声波"
            >
              <i v-for="n in 18" :key="n" :style="{ animationDelay: `${n * 0.04}s` }"></i>
            </div>
            <div v-else-if="connected || connecting" class="realtime-wave">
              <i v-for="n in 18" :key="n" :style="{ animationDelay: `${n * 0.04}s` }"></i>
            </div>
            <p v-if="!avatarVoiceMode">{{ hintText }}</p>
            <p v-if="avatarStatus" class="digital-human-provider-status">{{ avatarStatus }}</p>
          </div>
        </main>

        <aside class="realtime-self-room">
          <div class="realtime-room-head">
            <div>
              <strong>我的画面</strong>
              <span>{{ micMuted ? '麦克风已静音' : cameraOff ? '摄像头已关闭' : '摄像头与麦克风状态' }}</span>
            </div>
          </div>
          <video ref="localVideoRef" autoplay muted playsinline v-show="localStreamReady && !cameraOff"></video>
          <div v-if="!localStreamReady || cameraOff" class="realtime-placeholder">
            <span>ME</span>
            <p>{{ localStreamReady ? '摄像头已关闭' : '等待开始通话' }}</p>
          </div>
        </aside>

        <aside class="realtime-chat-room">
          <div class="realtime-room-head">
            <div>
              <strong>历史聊天记录</strong>
              <span>{{ conversation.length ? `${conversation.length} 条对话` : '等待开始记录' }}</span>
            </div>
          </div>
          <div class="realtime-event-log">
            <p v-if="!conversation.length">与 AI 辅导老师的对话会记录在这里，通话结束后自动保存并进入画像迭代。</p>
            <p v-for="item in conversation" :key="item.id" class="realtime-dialogue-line" :class="item.role">
              <strong>{{ item.role === 'user' ? '学生' : 'AI 辅导老师' }}</strong>
              <MarkdownContent :content="item.content" />
              <small>{{ item.timestamp }}</small>
            </p>
          </div>
        </aside>
      </div>

      <div class="realtime-control-row">
        <button class="studio-btn" type="button" :disabled="connecting || connected || Boolean(config.config_error && !avatarVoiceMode)" @click="startCall">
          {{ connecting ? '连接中' : '开始通话' }}
        </button>
        <button class="studio-btn secondary" type="button" :disabled="!connected" @click="interruptAi">打断 AI</button>
        <button class="studio-btn secondary" type="button" :disabled="!localStreamReady" @click="toggleMic">
          {{ micMuted ? '打开麦克风' : '静音' }}
        </button>
        <button class="studio-btn secondary" type="button" :disabled="!localStreamReady" @click="toggleCamera">
          {{ cameraOff ? '开启摄像头' : '关闭摄像头' }}
        </button>
        <button class="studio-btn danger" type="button" :disabled="!connecting && !connected" @click="endCall">挂断</button>
      </div>

      <div class="realtime-info-row">
        <div class="realtime-status-text" :class="{ error: statusKind === 'error' }">
          {{ avatarVoiceMode ? statusText : config.config_error ? `语音辅导配置错误：${config.config_error}` : statusText }}
          <span v-if="saveStatus"> · {{ saveStatus }}</span>
        </div>
      </div>
    </div>
  </section>
</template>
