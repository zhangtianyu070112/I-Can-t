<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BrainCircuit,
  ChartNoAxesCombined,
  ClipboardCheck,
  Eye,
  EyeOff,
  GraduationCap,
  LayoutDashboard,
  LockKeyhole,
  Map,
  MessageCircleQuestion,
  Mic,
  Network,
  ShieldCheck,
  Smartphone,
  Settings,
  UserRound,
  X,
} from 'lucide-vue-next'
import { useStudent } from '@/composables/useStudent'

type NavItem = {
  to: string
  label: string
  desc: string
  icon: typeof LayoutDashboard
}

const route = useRoute()
const router = useRouter()
const authStorageKey = 'zx-resource-agent-authed'
const isAuthed = ref(typeof window !== 'undefined' && sessionStorage.getItem(authStorageKey) === '1')
const phone = ref('')
const password = ref('')
const captcha = ref('')
const showPassword = ref(false)
const loginError = ref('')
const captchaCode = '2VV3'
const settingsOpen = ref(false)
const { studentId, major, goals, createFreshLearner } = useStudent()

const nav: NavItem[] = [
  { to: '/', label: '总控首页', desc: '录屏演示主入口', icon: LayoutDashboard },
  { to: '/profile', label: '用户画像', desc: '对话式动态画像', icon: GraduationCap },
  { to: '/workshop', label: '资源工坊', desc: '多智能体协同生成', icon: BrainCircuit },
  { to: '/path', label: '路径推送', desc: '个性化步骤与资源推送', icon: Map },
  { to: '/exercise', label: '练习诊断', desc: '答题进度与错题诊断', icon: ClipboardCheck },
  { to: '/knowledge', label: '知识中枢', desc: '课程检索与知识图谱', icon: Network },
  { to: '/multimodal', label: '多模态实验室', desc: '视频、代码、语音资源', icon: Mic },
  { to: '/tutor', label: '智能辅导', desc: '多模态即时答疑', icon: MessageCircleQuestion },
  { to: '/evaluate', label: '评估进化', desc: '学习效果追踪与闭环优化', icon: ChartNoAxesCombined },
]

const current = computed(() => nav.find((n) => n.to === route.path) || nav[0])

function submitLogin() {
  loginError.value = ''
  if (!/^1\d{10}$/.test(phone.value.trim())) {
    loginError.value = '请输入 11 位手机号'
    return
  }
  if (password.value !== 'demo123') {
    loginError.value = '测试密码为 demo123'
    return
  }
  if (captcha.value.trim().toUpperCase() !== captchaCode) {
    loginError.value = '验证码不正确'
    return
  }
  if (studentId.value === 'demo') createFreshLearner()
  isAuthed.value = true
  sessionStorage.setItem(authStorageKey, '1')
}

function enterDemo() {
  studentId.value = 'demo'
  isAuthed.value = true
  sessionStorage.setItem(authStorageKey, '1')
  loginError.value = ''
  void router.replace('/')
}

function logout() {
  sessionStorage.removeItem(authStorageKey)
  isAuthed.value = false
  settingsOpen.value = false
  void router.replace('/')
}

onMounted(() => {
  if (!isAuthed.value && route.path !== '/') {
    void router.replace('/')
  }
})
</script>

<template>
  <div class="portal-shell" :class="{ 'portal-shell-locked': !isAuthed }">
    <header class="portal-header">
      <RouterLink class="portal-brand" to="/">
        <span class="portal-brand-mark">
          <img src="/assets/huisi-learning-logo.png" alt="慧思智学平台标志" />
        </span>
        <span class="portal-brand-copy">
          <strong>慧思智学平台</strong>
          <small>个性化智慧学习平台</small>
        </span>
      </RouterLink>

      <nav class="portal-nav" aria-label="主导航">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="portal-nav-link"
          :title="item.desc"
        >
          <component :is="item.icon" :size="17" stroke-width="2.35" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="portal-user-menu">
        <span v-if="studentId === 'demo' && isAuthed" class="portal-demo-label">预置演示数据</span>
        <button class="portal-user-trigger" type="button" :aria-expanded="settingsOpen" aria-label="打开用户设置" @click="settingsOpen = !settingsOpen">
          <UserRound :size="17" />
          <span>用户设置</span>
          <Settings :size="15" />
        </button>
        <section v-if="settingsOpen" class="portal-settings-panel" aria-label="用户设置面板">
          <header><strong>用户设置</strong><button type="button" aria-label="关闭用户设置" @click="settingsOpen = false"><X :size="17" /></button></header>
          <label><span>学习者 ID</span><input v-model="studentId" autocomplete="off" /></label>
          <label><span>专业方向</span><input v-model="major" placeholder="例如：软件工程" autocomplete="off" /></label>
          <label><span>学习目标</span><textarea v-model="goals" rows="3" placeholder="描述希望达成的能力或成果"></textarea></label>
          <footer><RouterLink to="/profile" @click="settingsOpen = false">完善用户画像</RouterLink><button type="button" @click="logout">退出登录</button></footer>
        </section>
      </div>
    </header>

    <main class="portal-main" :class="{ 'portal-main-home': route.path === '/' }">
      <slot />
    </main>

    <section v-if="!isAuthed" class="login-gate" aria-label="登录注册">
      <form class="login-card" @submit.prevent="submitLogin">
        <div class="login-title">
          <h1>登录 / 注册</h1>
          <p>AI个性化学习智能体</p>
        </div>

        <label class="login-field">
          <Smartphone :size="28" stroke-width="2.2" />
          <input v-model="phone" inputmode="numeric" maxlength="11" placeholder="手机号" autocomplete="tel" />
        </label>

        <label class="login-field login-field-active">
          <LockKeyhole :size="28" stroke-width="2.2" />
          <input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            placeholder="密码"
            autocomplete="current-password"
          />
          <button class="login-eye" type="button" @click="showPassword = !showPassword" :aria-label="showPassword ? '隐藏密码' : '显示密码'">
            <EyeOff v-if="showPassword" :size="26" stroke-width="2.2" />
            <Eye v-else :size="26" stroke-width="2.2" />
          </button>
        </label>

        <label class="login-field login-captcha-field">
          <ShieldCheck :size="30" stroke-width="2.15" />
          <input v-model="captcha" maxlength="4" placeholder="验证码" autocomplete="off" />
          <span class="captcha-box">{{ captchaCode }}</span>
        </label>

        <button class="login-submit" type="submit">登录并进入系统</button>
        <button class="login-demo-submit" type="button" @click="enterDemo">使用预置数据进入路演</button>

        <div class="login-tip">
          <span>现场演示可直接使用预置数据；测试登录使用任意 11 位手机号、密码 demo123</span>
          <strong v-if="loginError">{{ loginError }}</strong>
        </div>
      </form>
    </section>
  </div>
</template>
