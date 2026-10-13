<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { renderMarkdown } from '@/utils/markdownRenderer'

const props = withDefaults(defineProps<{
  content?: string
  streaming?: boolean
}>(), {
  content: '',
  streaming: false,
})

const html = ref('')
const root = ref<HTMLElement | null>(null)
let renderTimer: number | null = null

const source = computed(() => String(props.content || ''))

function updateHtml(immediate = false) {
  if (renderTimer !== null) {
    window.clearTimeout(renderTimer)
    renderTimer = null
  }

  const apply = () => {
    html.value = renderMarkdown(source.value, { streaming: props.streaming })
    renderTimer = null
  }

  if (immediate || !props.streaming) {
    apply()
    return
  }

  renderTimer = window.setTimeout(apply, 50)
}

function copyCode(event: Event) {
  const target = event.target as HTMLElement | null
  const button = target?.closest<HTMLButtonElement>('.markdown-code-copy')
  if (!button) return
  const pre = button.nextElementSibling
  const code = pre?.querySelector('code')?.textContent || ''
  if (!code) return
  void navigator.clipboard?.writeText(code)
  button.dataset.copied = 'true'
  window.setTimeout(() => {
    button.dataset.copied = 'false'
  }, 1200)
}

function enhanceCodeBlocks() {
  nextTick(() => {
    root.value?.querySelectorAll('pre').forEach((pre) => {
      const parent = pre.parentElement
      if (!parent || parent.classList.contains('markdown-code-frame')) return
      const wrapper = document.createElement('div')
      wrapper.className = 'markdown-code-frame'
      const button = document.createElement('button')
      button.className = 'markdown-code-copy'
      button.type = 'button'
      button.textContent = '复制'
      parent.insertBefore(wrapper, pre)
      wrapper.appendChild(button)
      wrapper.appendChild(pre)
    })
  })
}

watch([source, () => props.streaming], () => updateHtml(!props.streaming), { immediate: true })
watch(html, enhanceCodeBlocks)

onBeforeUnmount(() => {
  if (renderTimer !== null) window.clearTimeout(renderTimer)
})
</script>

<template>
  <div ref="root" class="markdown-body" @click="copyCode" v-html="html"></div>
</template>
