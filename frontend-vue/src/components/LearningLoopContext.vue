<script setup lang="ts">
import { ArrowRight, BadgeCheck, BrainCircuit, Database, Route } from 'lucide-vue-next'

withDefaults(defineProps<{
  stage: string
  stageLabel: string
  task: string
  input: string
  process: string
  output: string
  nextTo: string
  nextLabel: string
  status?: string
}>(), {
  status: '证据实时同步',
})
</script>

<template>
  <section class="module-context" aria-label="当前模块闭环上下文">
    <div class="module-context__stage">
      <span class="module-context__index">STEP {{ stage }}</span>
      <span class="module-context__task">
        <small>{{ stageLabel }} · 当前任务</small>
        <strong>{{ task }}</strong>
      </span>
    </div>

    <div class="module-context__flow" aria-label="输入、处理与产出流程">
      <article>
        <span class="module-context__icon"><Database :size="17" /></span>
        <span><small>输入证据</small><strong>{{ input }}</strong></span>
      </article>
      <ArrowRight class="module-context__arrow" :size="15" aria-hidden="true" />
      <article class="is-agent">
        <span class="module-context__icon"><BrainCircuit :size="17" /></span>
        <span><small>智能体处理</small><strong>{{ process }}</strong></span>
      </article>
      <ArrowRight class="module-context__arrow" :size="15" aria-hidden="true" />
      <article class="is-output">
        <span class="module-context__icon"><BadgeCheck :size="17" /></span>
        <span><small>当前产出</small><strong>{{ output }}</strong></span>
      </article>
    </div>

    <RouterLink class="module-context__next" :to="nextTo">
      <span><small>{{ status }}</small><strong>下一阶段 · {{ nextLabel }}</strong></span>
      <Route :size="17" />
    </RouterLink>
  </section>
</template>
