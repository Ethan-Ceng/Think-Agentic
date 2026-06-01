<script setup lang="ts">
import { ref } from 'vue'
import { Check, Copy } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'

const props = withDefaults(defineProps<{
  content: string
  align?: 'left' | 'right'
}>(), {
  align: 'left',
})

const emit = defineEmits<{
  copied: []
}>()

const toast = useToast()
const copied = ref(false)

async function copyText() {
  const text = props.content.trim()
  if (!text) return

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'fixed'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }

    copied.value = true
    emit('copied')
    toast.success('已复制')
    window.setTimeout(() => {
      copied.value = false
    }, 1400)
  } catch {
    toast.error('复制失败')
  }
}
</script>

<template>
  <div class="message-actions" :class="`align-${align}`">
    <ElTooltip :content="copied ? '已复制' : '复制'" placement="top">
      <button
        class="message-action-button"
        type="button"
        :disabled="!content.trim()"
        :aria-label="copied ? '已复制' : '复制'"
        @click="copyText"
      >
        <Check v-if="copied" :size="14" />
        <Copy v-else :size="14" />
      </button>
    </ElTooltip>
  </div>
</template>
