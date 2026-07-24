<script setup lang="ts">
import { ref } from 'vue'
import { Check, Copy, GitFork, LoaderCircle, Pencil, RefreshCw } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import type { BranchOperation } from '@/lib/api/types'

const props = withDefaults(defineProps<{
  content: string
  align?: 'left' | 'right'
  role?: 'user' | 'assistant'
  sourceEventId?: string
  branchDisabled?: boolean
  branchDisabledReason?: string
  branchBusy?: boolean
}>(), {
  align: 'left',
  role: 'assistant',
  sourceEventId: undefined,
  branchDisabled: false,
  branchDisabledReason: '',
  branchBusy: false,
})

const emit = defineEmits<{
  copied: []
  branch: [operation: BranchOperation]
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

function branch(operation: BranchOperation) {
  if (!props.sourceEventId || props.branchDisabled || props.branchBusy) return
  emit('branch', operation)
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
    <ElTooltip
      :content="branchDisabledReason || '从这里创建新对话分支'"
      placement="top"
    >
      <button
        class="message-action-button"
        type="button"
        :disabled="!sourceEventId || branchDisabled || branchBusy"
        aria-label="从这里分支"
        @click="branch('fork')"
      >
        <LoaderCircle v-if="branchBusy" :size="14" class="spin" />
        <GitFork v-else :size="14" />
      </button>
    </ElTooltip>
    <ElTooltip
      v-if="role === 'user'"
      :content="branchDisabledReason || '编辑并在新分支重新提交'"
      placement="top"
    >
      <button
        class="message-action-button"
        type="button"
        :disabled="!sourceEventId || branchDisabled || branchBusy"
        aria-label="编辑并重新提交"
        @click="branch('edit')"
      >
        <Pencil :size="14" />
      </button>
    </ElTooltip>
    <ElTooltip
      v-else
      :content="branchDisabledReason || '在新分支重新生成回复'"
      placement="top"
    >
      <button
        class="message-action-button"
        type="button"
        :disabled="!sourceEventId || branchDisabled || branchBusy"
        aria-label="重新生成回复"
        @click="branch('regenerate')"
      >
        <RefreshCw :size="14" />
      </button>
    </ElTooltip>
  </div>
</template>
