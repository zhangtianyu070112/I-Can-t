<script setup lang="ts">
import type { Component } from 'vue'
import { RouterLink } from 'vue-router'
import {
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  ClipboardCheck,
  Code2,
  FileText,
  GraduationCap,
  Layers3,
  Map,
  Network,
  PenTool,
  Route,
  Sparkles,
  Video,
} from 'lucide-vue-next'

type Capability = {
  eyebrow: string
  title: string
  desc: string
  to: string
  action: string
  icon: Component
  preview: string[]
}

type PathNode = {
  label: string
  desc: string
  status: 'done' | 'active' | 'next'
}

type ResourceType = {
  label: string
  icon: Component
  desc: string
}

const capabilities: Capability[] = [
  {
    eyebrow: 'Profile',
    title: '一句话，形成动态学习画像。',
    desc: '学生只需要描述专业、课程章节、目标和薄弱点，系统即可抽取知识基础、认知风格、易错模式、模态偏好等关键维度。',
    to: '/profile',
    action: '进入用户画像',
    icon: GraduationCap,
    preview: ['软件工程', '需求分析与建模', '图解偏好', '用例图 / 需求访谈'],
  },
  {
    eyebrow: 'Agent Workshop',
    title: '多智能体协同，不止生成一份资料。',
    desc: '讲解、题库、导图、拓展阅读、实操案例和视频脚本由不同角色智能体协同产出，并沉淀为可复用学习资源。',
    to: '/workshop',
    action: '进入资源工坊',
    icon: BrainCircuit,
    preview: ['讲解文档', '思维导图', '练习题库', '实操案例'],
  },
  {
    eyebrow: 'Learning Path',
    title: '把资源变成真正可执行的学习路径。',
    desc: '结合画像、练习诊断和知识图谱，系统动态安排学习顺序，并精准推送文档、视频、题库和实操任务。',
    to: '/path',
    action: '查看路径推送',
    icon: Route,
    preview: ['概念补强', '例题训练', '项目实操', '阶段测评'],
  },
]

const pathNodes: PathNode[] = [
  { label: '基础诊断', desc: '识别知识起点', status: 'done' },
  { label: '概念补强', desc: '聚焦薄弱章节', status: 'active' },
  { label: '例题训练', desc: '对比易错概念', status: 'next' },
  { label: '项目实操', desc: '迁移到真实任务', status: 'next' },
  { label: '阶段测评', desc: '形成学习证据', status: 'next' },
  { label: '动态调整', desc: '更新画像与推荐', status: 'next' },
]

const resourceTypes: ResourceType[] = [
  { label: '讲解文档', icon: FileText, desc: '课程重点结构化讲解' },
  { label: '思维导图', icon: Network, desc: '知识点关系可视化' },
  { label: '练习题库', icon: ClipboardCheck, desc: '按薄弱点生成训练题' },
  { label: '拓展阅读', icon: BookOpenCheck, desc: '补充背景与案例材料' },
  { label: '实操案例', icon: Code2, desc: '面向任务的实践步骤' },
  { label: '视频 / 动画', icon: Video, desc: '短视频脚本与讲解设计' },
]
</script>

<template>
  <div class="apple-home">
    <section class="apple-hero">
      <div class="apple-hero-copy">
        <div class="apple-kicker">
          <Sparkles :size="18" />
          <span>AI Learning Agent</span>
        </div>
        <h1>为每一位学生，生成专属学习路径。</h1>
        <p>
          基于学习画像、多智能体协同与多模态资源生成，帮助学生从知识短板到能力提升，
          获得更精准、更高效的学习体验。
        </p>
        <div class="apple-hero-actions">
          <RouterLink class="apple-primary-btn" to="/profile">
            开始构建学习画像
            <ArrowRight :size="18" />
          </RouterLink>
          <RouterLink class="apple-text-btn" to="/path">
            查看学习路径示例
          </RouterLink>
        </div>
      </div>

      <div class="product-preview-shell" aria-label="系统产品预览">
        <div class="preview-glow"></div>
        <div class="preview-device">
          <div class="preview-toolbar">
            <span></span>
            <span></span>
            <span></span>
            <strong>慧思智学平台</strong>
          </div>
          <div class="preview-screen">
            <div class="preview-left">
              <small>Learning Profile</small>
              <h2>需求分析与建模</h2>
              <p>已识别：图解偏好、案例驱动、用例图与需求访谈混淆</p>
              <div class="preview-tags">
                <span>画像生成中</span>
                <span>资源沉淀</span>
                <span>路径更新</span>
              </div>
            </div>
            <div class="preview-flow">
              <div class="flow-line"></div>
              <div class="flow-item active">
                <GraduationCap :size="19" />
                <span>学习画像</span>
              </div>
              <div class="flow-item">
                <BrainCircuit :size="19" />
                <span>Agent 协作</span>
              </div>
              <div class="flow-item">
                <Map :size="19" />
                <span>路径推送</span>
              </div>
            </div>
          </div>
          <div class="preview-bottom">
            <div>
              <strong>6</strong>
              <span>画像维度</span>
            </div>
            <div>
              <strong>5+</strong>
              <span>资源类型</span>
            </div>
            <div>
              <strong>API</strong>
              <span>真实接口</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="apple-section apple-intro">
      <span class="section-label">核心能力</span>
      <h2>从“我哪里不会”，到“下一步该学什么”。</h2>
      <p>
        首页展示完整学习闭环：画像采集、资源生成、练习诊断、路径推送与效果评估，
        但表达方式保持克制，让比赛演示更像成熟产品发布。
      </p>
    </section>

    <section class="capability-story">
      <article v-for="item in capabilities" :key="item.title" class="story-panel">
        <div class="story-copy">
          <div class="story-icon">
            <component :is="item.icon" :size="23" />
          </div>
          <span>{{ item.eyebrow }}</span>
          <h3>{{ item.title }}</h3>
          <p>{{ item.desc }}</p>
          <RouterLink :to="item.to">
            {{ item.action }}
            <ArrowRight :size="17" />
          </RouterLink>
        </div>
        <div class="story-visual">
          <div class="story-screen">
            <div class="screen-line strong"></div>
            <div class="screen-line"></div>
            <div class="screen-line short"></div>
            <div class="story-chip-grid">
              <span v-for="tag in item.preview" :key="tag">{{ tag }}</span>
            </div>
          </div>
        </div>
      </article>
    </section>

    <section class="path-showcase">
      <div class="path-copy">
        <span class="section-label">路径推送</span>
        <h2>让学习顺序被看见。</h2>
        <p>
          系统根据画像、知识掌握情况和资源覆盖度动态规划学习步骤。
          每个节点都对应清晰目标和下一步资源，不再让学生在资料堆里迷路。
        </p>
      </div>
      <div class="path-rail">
        <article v-for="(node, index) in pathNodes" :key="node.label" class="path-node" :class="node.status">
          <span class="path-index">{{ String(index + 1).padStart(2, '0') }}</span>
          <div>
            <strong>{{ node.label }}</strong>
            <p>{{ node.desc }}</p>
          </div>
          <em>{{ node.status === 'done' ? '已完成' : node.status === 'active' ? '进行中' : '推荐下一步' }}</em>
        </article>
      </div>
    </section>

    <section class="resource-showcase">
      <div class="resource-stage">
        <div class="resource-main-window">
          <div class="resource-window-head">
            <Layers3 :size="20" />
            <span>多模态资源生成</span>
          </div>
          <h2>同一个薄弱点，可以获得多种学习表达。</h2>
          <p>针对“用例图 / 需求访谈混淆”，系统会同步组织讲解、导图、练习和实操任务。</p>
          <div class="resource-progress">
            <span style="width: 72%"></span>
          </div>
        </div>

        <div class="resource-orbit">
          <article v-for="item in resourceTypes" :key="item.label" class="resource-pill">
            <component :is="item.icon" :size="20" />
            <div>
              <strong>{{ item.label }}</strong>
              <span>{{ item.desc }}</span>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section class="apple-final-cta">
      <div>
        <PenTool :size="28" />
        <h2>从今天开始，让学习路径真正属于你。</h2>
        <p>先构建画像，再生成资源，最后让系统持续根据学习证据更新推荐。</p>
      </div>
      <RouterLink class="apple-primary-btn" to="/profile">
        进入智能体系统
        <ArrowRight :size="18" />
      </RouterLink>
    </section>

    <footer class="apple-home-footer">
      <CheckCircle2 :size="16" />
      <span>慧思智学平台 · 多智能体个性化学习资源生成系统</span>
    </footer>
  </div>
</template>
