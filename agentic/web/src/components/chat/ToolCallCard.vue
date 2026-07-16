<script setup lang="ts">
import {
  AlertCircle,
  Bot,
  Check,
  CheckCircle2,
  Copy,
  FileSearch,
  Globe,
  Loader2,
  Search,
  SquareChevronRight,
  Terminal,
  Wrench,
} from 'lucide-vue-next'
import { computed, ref, type Component } from 'vue'
import { useToast } from '@/composables/useToast'
import type { ToolEvent } from '@/lib/api/types'
import SkillDraftHandoffButton from '@/components/skills/SkillDraftHandoffButton.vue'
import {
  getFriendlyToolLabel,
  getToolKind,
  getToolResultText,
  isToolFailed,
  stringifyToolValue,
  type ToolKind,
} from '@/lib/tool-utils'

const props = withDefaults(defineProps<{
  data?: ToolEvent | null
  clickable?: boolean
  dense?: boolean
  timeLabel?: string
}>(), {
  data: null,
  clickable: false,
  dense: false,
  timeLabel: undefined,
})

const emit = defineEmits<{
  click: [tool: ToolEvent]
}>()

const toast = useToast()
const copiedTarget = ref<'args' | 'result' | null>(null)

const iconMap: Record<ToolKind, Component | undefined> = {
  message: undefined,
  bash: Terminal,
  file: FileSearch,
  search: Search,
  browser: Globe,
  mcp: Wrench,
  a2a: Bot,
  default: SquareChevronRight,
}

const kindLabelMap: Record<ToolKind, string> = {
  message: '消息',
  bash: '终端',
  file: '文件',
  search: '搜索',
  browser: '浏览器',
  mcp: 'MCP',
  a2a: 'Agent',
  default: '工具',
}

const kind = computed(() => getToolKind(props.data))
const icon = computed(() => iconMap[kind.value])
const label = computed(() => getFriendlyToolLabel(props.data))
const toolName = computed(() => props.data?.function || props.data?.name || 'tool')
const isRunning = computed(() => props.data?.status === 'calling')
const isFailed = computed(() => isToolFailed(props.data))
const statusLabel = computed(() => {
  if (isRunning.value) return '运行中'
  if (isFailed.value) return '失败'
  if (props.data?.status === 'called') return '已完成'
  return '已记录'
})
const tagType = computed(() => (isRunning.value ? 'warning' : isFailed.value ? 'danger' : 'success'))
const toolKindLabel = computed(() => kindLabelMap[kind.value])
const cardTitle = computed(() => `${toolKindLabel.value} · ${label.value}`)
const ariaLabel = computed(() => `查看${toolKindLabel.value}调用详情：${label.value}`)
const argsCopyText = computed(() => stringifyToolValue(props.data?.args || {}))
const resultCopyText = computed(() => getToolResultText(props.data))
const draftId = computed(() => {
  if (props.data?.function !== 'skill_draft_create') return ''
  const data = props.data.function_result?.data
  if (!data || typeof data !== 'object') return ''
  const value = (data as Record<string, unknown>).draft_id
  return typeof value === 'string' ? value : ''
})
const eventDomId = computed(() => {
  const eventId = (props.data as { event_id?: string } | null)?.event_id
  return eventId ? `event-${eventId}` : undefined
})

function handleClick() {
  if (props.clickable && props.data) {
    emit('click', props.data)
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  handleClick()
}

async function copyText(text: string, target: 'args' | 'result') {
  if (!text.trim()) return

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
    copiedTarget.value = target
    toast.success(target === 'args' ? '已复制参数' : '已复制结果')
    window.setTimeout(() => {
      if (copiedTarget.value === target) copiedTarget.value = null
    }, 1400)
  } catch {
    toast.error('复制失败')
  }
}
</script>

<template>
  <div
    :id="eventDomId"
    class="tool-call-card"
    :class="[`kind-${kind}`, { 'is-running': isRunning, 'is-failed': isFailed, passive: !clickable, dense }]"
    :title="cardTitle"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    :aria-label="clickable ? ariaLabel : undefined"
    @click="handleClick"
    @keydown="handleKeydown"
  >
    <span class="tool-call-icon">
      <Loader2 v-if="isRunning" :size="16" class="spin" />
      <AlertCircle v-else-if="isFailed" :size="16" />
      <component :is="icon" v-else-if="icon" :size="16" />
      <CheckCircle2 v-else :size="16" />
    </span>

    <span class="tool-call-main">
      <span class="tool-call-topline">
        <span class="tool-call-kind">{{ toolKindLabel }}</span>
        <span v-if="timeLabel" class="tool-call-time">{{ timeLabel }}</span>
      </span>
      <span class="tool-call-title" :title="label">{{ label }}</span>
      <span class="tool-call-meta" :title="toolName">{{ toolName }}</span>
    </span>

    <ElTag size="small" effect="light" round :type="tagType">
      {{ statusLabel }}
    </ElTag>

    <span class="tool-call-actions" @click.stop>
      <SkillDraftHandoffButton v-if="draftId" :draft-id="draftId" />
      <ElTooltip :content="copiedTarget === 'args' ? '已复制参数' : '复制参数'" placement="top">
        <button
          class="tool-copy-button"
          type="button"
          aria-label="复制工具参数"
          @click.stop="copyText(argsCopyText, 'args')"
        >
          <Check v-if="copiedTarget === 'args'" :size="13" />
          <Copy v-else :size="13" />
        </button>
      </ElTooltip>

      <ElTooltip :content="copiedTarget === 'result' ? '已复制结果' : '复制结果'" placement="top">
        <button
          class="tool-copy-button"
          type="button"
          :disabled="!resultCopyText.trim()"
          aria-label="复制工具结果"
          @click.stop="copyText(resultCopyText, 'result')"
        >
          <Check v-if="copiedTarget === 'result'" :size="13" />
          <Copy v-else :size="13" />
        </button>
      </ElTooltip>
    </span>
  </div>
</template>
