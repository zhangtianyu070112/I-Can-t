<script setup lang="ts">
import { ref } from 'vue'
import { Camera, Mic2, ShieldCheck, Sparkles, Video } from 'lucide-vue-next'
import TutorRealtimeCall from '@/components/TutorRealtimeCall.vue'
import MarkdownContent from '@/components/MarkdownContent.vue'
import { useStudent } from '@/composables/useStudent'
import { apiPost } from '@/utils/api'

type LocalAnswer = {
  answer: { markdown: string }
  references: Array<{ id: string; title: string; excerpt: string; score: number }>
}

const { studentId } = useStudent()
const question = ref('')
const answer = ref<LocalAnswer | null>(null)
const error = ref('')
const asking = ref(false)

async function askLocalKnowledge() {
  const text = question.value.trim()
  if (!text || asking.value) return
  asking.value = true
  error.value = ''
  answer.value = null
  try {
    const result = await apiPost<LocalAnswer>('/api/knowledge/ask', { student_id: studentId.value, question: text })
    if (!result.success || !result.data) throw new Error(result.error?.message || '本地资料检索失败')
    answer.value = result.data
  } catch (reason: any) {
    error.value = reason?.message || '本地资料检索失败'
  } finally {
    asking.value = false
  }
}

const capabilities = [
  { icon: Camera, title: '双向视频课堂', copy: '启用本地摄像头，与数字人辅导老师保持同屏交流。' },
  { icon: Mic2, title: '实时语音交互', copy: '支持连续对话、随时打断与麦克风静音控制。' },
  { icon: ShieldCheck, title: '学习过程留痕', copy: '通话结束后保存对话证据，用于更新画像与后续推荐。' },
]
</script>

<template>
  <div class="competition-page tutor-video-page">
    <header class="tutor-video-hero">
      <div>
        <div class="competition-eyebrow"><Video :size="15" /> REALTIME AI TUTOR</div>
        <h1>实时视频辅导</h1>
        <p>与数字人老师面对面交流。系统会结合当前学习画像与课程证据，进行实时讲解和追问。</p>
      </div>
    </header>

    <section class="tutor-video-shell">
      <TutorRealtimeCall />
    </section>

    <section class="tutor-local-panel" aria-labelledby="local-tutor-title">
      <div>
        <span class="competition-eyebrow">无需外部密钥</span>
        <h2 id="local-tutor-title">本地资料问答</h2>
        <p>检索当前学习者已保存的课程资料与资源，回答只展示检索到的依据。语音视频服务未配置时，可在现场继续演示这条真实链路。</p>
      </div>
      <form @submit.prevent="askLocalKnowledge">
        <label for="local-tutor-question">输入课程问题</label>
        <div class="tutor-local-composer">
          <input id="local-tutor-question" v-model="question" maxlength="300" placeholder="例如：需求访谈和用例图有什么关系？" />
          <button type="submit" :disabled="asking || !question.trim()">{{ asking ? '检索中…' : '检索本地资料' }}</button>
        </div>
      </form>
      <p v-if="error" class="tutor-local-error" role="alert">{{ error }}</p>
      <div v-if="answer" class="tutor-local-answer" aria-live="polite">
        <MarkdownContent :content="answer.answer.markdown" />
        <div v-if="answer.references.length" class="tutor-local-sources">
          <strong>检索依据</strong>
          <ul><li v-for="source in answer.references.slice(0, 3)" :key="source.id">{{ source.title }} <small>匹配度 {{ Math.round(source.score * 100) }}%</small></li></ul>
        </div>
      </div>
    </section>

    <section class="tutor-capability-strip" aria-label="实时辅导能力">
      <article v-for="item in capabilities" :key="item.title">
        <span class="tutor-capability-icon"><component :is="item.icon" :size="20" /></span>
        <div><strong>{{ item.title }}</strong><p>{{ item.copy }}</p></div>
      </article>
      <div class="tutor-capability-note"><Sparkles :size="17" /> 真实音视频与模型响应均由服务端配置驱动</div>
    </section>
  </div>
</template>

<style scoped>
.tutor-local-panel { display: grid; gap: 16px; margin: 24px 0; padding: 28px; border: 1px solid #dbe5f2; border-radius: 22px; background: #fff; box-shadow: 0 12px 36px rgba(29, 74, 132, .08); }
.tutor-local-panel h2 { margin: 8px 0; font-size: 24px; color: #102033; }
.tutor-local-panel p { margin: 0; color: #52657d; line-height: 1.7; }
.tutor-local-panel form { display: grid; gap: 8px; }
.tutor-local-panel label { font-weight: 700; color: #213b5b; }
.tutor-local-composer { display: flex; gap: 10px; }
.tutor-local-composer input { flex: 1; min-width: 0; padding: 12px 15px; border: 1px solid #cddbea; border-radius: 12px; background: #fff; }
.tutor-local-composer button { padding: 12px 18px; border: 0; border-radius: 12px; color: #fff; background: #246dff; font-weight: 700; cursor: pointer; }
.tutor-local-composer button:disabled { opacity: .55; cursor: not-allowed; }
.tutor-local-error { color: #b42318 !important; }
.tutor-local-answer { padding: 18px; border: 1px solid #dbe5f2; border-radius: 14px; background: #f7faff; }
.tutor-local-sources { margin-top: 14px; padding-top: 12px; border-top: 1px solid #dbe5f2; }
.tutor-local-sources ul { margin: 8px 0 0; padding-left: 20px; }
.tutor-local-sources li { margin: 5px 0; }
.tutor-local-sources small { margin-left: 8px; color: #66809d; }
@media (max-width: 640px) { .tutor-local-panel { padding: 18px; } .tutor-local-composer { flex-direction: column; } }
</style>
