<script setup lang="ts">
import { computed } from 'vue'
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clock3,
  LoaderCircle,
} from 'lucide-vue-next'
import ExecutionTree from '@/components/chat/ExecutionTree.vue'
import type { RunExecutionState } from '@/composables/useRunExecutions'

const props = defineProps<{
  state: RunExecutionState
}>()

const emit = defineEmits<{
  toggle: [runId: string]
}>()

const latestNode = computed(() => {
  const active = [...props.state.nodes]
    .reverse()
    .find((node) => node.status === 'running' || node.status === 'waiting' || node.status === 'failed')
  return active || props.state.nodes.at(-1)
})

const statusLabel = computed(() => {
  const { status, mode, metrics } = props.state.run
  if (status === 'failed') return '本次执行未完成'
  if (status === 'waiting') return '等待你的输入'
  if (status === 'running' || status === 'pending') {
    if (mode === 'plan') {
      const completed = metrics.completed_steps ?? 0
      const total = metrics.step_count ?? 0
      return total ? `正在执行计划 · ${completed}/${total}` : '正在制定并执行计划'
    }
    return mode === 'react' ? '正在思考与执行' : '正在组织回答'
  }
  const duration = formatDuration(props.state.run.latency_ms)
  const prefix = props.state.run.mode === 'plan' ? '已完成计划与执行' : '已思考并执行'
  return duration ? `${prefix} ${duration}` : prefix
})

const detailSummary = computed(() => {
  const metrics = props.state.run.metrics
  const parts: string[] = []
  if (metrics.step_count) parts.push(`步骤 ${metrics.completed_steps ?? 0}/${metrics.step_count}`)
  if (metrics.tool_count) parts.push(`${metrics.tool_count} 个工具`)
  return parts.join(' · ')
})

function formatDuration(value?: number | null): string {
  if (value == null) return ''
  if (value < 1000) return `${value} ms`
  if (value < 60_000) return `${Math.max(1, Math.round(value / 1000))} 秒`
  return `${Math.floor(value / 60_000)} 分 ${Math.round((value % 60_000) / 1000)} 秒`
}
</script>

<template>
  <section class="run-process-block" :class="[`status-${state.run.status}`, { expanded: state.expanded }]">
    <button
      class="run-process-toggle"
      type="button"
      :aria-expanded="state.expanded"
      @click="emit('toggle', state.runId)"
    >
      <ChevronRight :size="15" class="run-process-chevron" />
      <LoaderCircle v-if="state.run.status === 'running' || state.run.status === 'pending'" :size="15" class="spin" />
      <Clock3 v-else-if="state.run.status === 'waiting'" :size="15" />
      <AlertCircle v-else-if="state.run.status === 'failed'" :size="15" />
      <CheckCircle2 v-else :size="15" />
      <span class="run-process-label">{{ statusLabel }}</span>
      <span v-if="detailSummary" class="run-process-summary">{{ detailSummary }}</span>
    </button>

    <div v-if="state.expanded" class="run-process-detail">
      <div v-if="latestNode" class="run-process-current">
        <span>{{ latestNode.summary || latestNode.title }}</span>
      </div>
      <ExecutionTree :nodes="state.nodes" />
      <div v-if="state.loading" class="run-process-loading">正在读取执行详情…</div>
      <div v-else-if="state.error" class="run-process-error">{{ state.error }}</div>
      <div v-if="!state.traceComplete" class="run-process-warning">执行记录暂不完整，可稍后刷新重试。</div>
    </div>
  </section>
</template>
