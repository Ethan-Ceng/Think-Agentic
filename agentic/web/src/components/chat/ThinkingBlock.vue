<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Circle,
  Loader2,
  Sparkles,
} from 'lucide-vue-next'
import ToolCallCard from '@/components/chat/ToolCallCard.vue'
import type { StepEvent, ToolEvent } from '@/lib/api/types'
import { getToolTimeLabel } from '@/lib/session-events'
import { getFriendlyToolLabel, getToolKind, type ToolKind } from '@/lib/tool-utils'

const props = defineProps<{
  step: StepEvent
  tools: ToolEvent[]
}>()

const emit = defineEmits<{
  toolClick: [tool: ToolEvent]
}>()

const toolKindLabelMap: Record<ToolKind, string> = {
  message: '消息',
  bash: '终端',
  file: '文件',
  search: '搜索',
  browser: '浏览器',
  mcp: 'MCP',
  a2a: 'Agent',
  default: '工具',
}

const expanded = ref(props.step.status !== 'completed')
const userToggled = ref(false)

const statusMeta = computed(() => {
  switch (props.step.status) {
    case 'completed':
      return { label: '已完成', title: '思考完成', icon: CheckCircle2 }
    case 'running':
      return { label: '进行中', title: '正在思考', icon: Loader2 }
    case 'failed':
      return { label: '失败', title: '需要关注', icon: AlertCircle }
    default:
      return { label: '等待中', title: '等待执行', icon: Circle }
  }
})

const visibleTools = computed(() => props.tools.filter((tool) => getToolKind(tool) !== 'message'))
const messageTools = computed(() => props.tools.filter((tool) => getToolKind(tool) === 'message'))
const stepError = computed(() => (typeof props.step.error === 'string' ? props.step.error : ''))
const groupedVisibleTools = computed(() => {
  const groups = new Map<ToolKind, ToolEvent[]>()

  for (const tool of visibleTools.value) {
    const kind = getToolKind(tool)
    groups.set(kind, [...(groups.get(kind) || []), tool])
  }

  return Array.from(groups.entries()).map(([kind, tools]) => ({
    kind,
    label: toolKindLabelMap[kind],
    tools,
  }))
})
const toolSummary = computed(() => {
  const parts = [`${visibleTools.value.length} 个工具`, `${messageTools.value.length} 条进度`]
  if (groupedVisibleTools.value.length > 1) parts.push(`${groupedVisibleTools.value.length} 类`)
  return parts.join(' · ')
})

watch(
  () => props.step.status,
  (status) => {
    if (userToggled.value) return
    expanded.value = status === 'running' || status === 'failed'
  },
)

function toggleExpanded() {
  userToggled.value = true
  expanded.value = !expanded.value
}

function handleToolClick(tool: ToolEvent) {
  if (getToolKind(tool) === 'message') return
  emit('toolClick', tool)
}
</script>

<template>
  <section class="thinking-block" :class="`status-${step.status}`">
    <button
      class="thinking-header"
      type="button"
      :aria-expanded="expanded"
      :title="step.description || statusMeta.title"
      @click="toggleExpanded"
    >
      <span class="thinking-status-icon">
        <component
          :is="statusMeta.icon"
          :size="16"
          :class="{ spin: step.status === 'running' }"
        />
      </span>

      <span class="thinking-copy">
        <span class="thinking-eyebrow">
          <Sparkles :size="13" />
          思考过程
        </span>
        <strong>{{ statusMeta.title }}</strong>
        <span :title="step.description || '正在规划下一步行动'">
          {{ step.description || '正在规划下一步行动' }}
        </span>
      </span>

      <span class="thinking-summary">
        <ElTag size="small" round effect="light" :type="step.status === 'failed' ? 'danger' : 'info'">
          {{ statusMeta.label }}
        </ElTag>
        <small>{{ toolSummary }}</small>
        <ChevronDown :size="16" :class="{ rotated: expanded }" />
      </span>
    </button>

    <div v-if="expanded" class="thinking-body">
      <div v-if="stepError" class="thinking-error">
        <AlertCircle :size="14" />
        <span>{{ stepError }}</span>
      </div>

      <div v-if="messageTools.length > 0" class="thinking-notes">
        <p v-for="(tool, index) in messageTools" :key="`${step.id}-note-${index}`">
          {{ getFriendlyToolLabel(tool) }}
        </p>
      </div>

      <div v-if="visibleTools.length > 0" class="thinking-tool-list">
        <section
          v-for="group in groupedVisibleTools"
          :key="`${step.id}-tool-group-${group.kind}`"
          class="thinking-tool-group"
        >
          <header class="thinking-tool-group-header">
            <span>{{ group.label }}</span>
            <small>{{ group.tools.length }} 次</small>
          </header>
          <ToolCallCard
            v-for="(tool, index) in group.tools"
            :key="`${step.id}-tool-${group.kind}-${index}`"
            :data="tool"
            :time-label="getToolTimeLabel(tool) || '刚刚'"
            dense
            clickable
            @click="handleToolClick"
          />
        </section>
      </div>

      <div v-else class="thinking-empty">
        还没有工具调用
      </div>
    </div>
  </section>
</template>
