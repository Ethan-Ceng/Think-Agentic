<script setup lang="ts">
import { computed, ref, type PropType } from 'vue'
import type { ChatRuntimeEvent, ChatRuntimeStep } from '@/models/app'

const props = defineProps({
  loading: { type: Boolean, default: false, required: false },
  mode: { type: String as PropType<'debug' | 'public'>, default: 'debug', required: false },
  runtime_events: {
    type: Array as PropType<ChatRuntimeEvent[]>,
    default: () => [],
    required: true,
  },
})

const visible = ref(true)

const latestPlan = computed(() => {
  const plans = props.runtime_events.filter((item) => item.type === 'plan')
  return plans[plans.length - 1]
})

const timelineEvents = computed(() => {
  const events = props.runtime_events.filter((item) => !['plan', 'message', 'title'].includes(String(item.type)))
  if (props.mode !== 'public') return events.slice(-24)

  const hasUserLevelEvents = events.some((item) => ['step', 'wait', 'error', 'done'].includes(String(item.type)))
  return events
    .filter((item) => String(item.type) !== 'tool' || !hasUserLevelEvents)
    .slice(-12)
})

const waitEvents = computed(() => timelineEvents.value.filter((item) => item.type === 'wait'))

const panelTitle = computed(() => {
  if (latestPlan.value) return latestPlan.value.title || '执行计划'
  if (props.loading) return '正在运行'
  return '运行事件'
})

const planSteps = computed(() => latestPlan.value?.steps ?? [])

const statusLabel = (status: string) => {
  const labels: Record<string, string> = {
    created: '已创建',
    updated: '已更新',
    pending: '待执行',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    waiting: '等待中',
    cancelled: '已停止',
  }
  return labels[status] ?? status
}

const statusClass = (status: string) => {
  const classes: Record<string, string> = {
    created: 'bg-blue-50 text-blue-700 border-blue-100',
    updated: 'bg-indigo-50 text-indigo-700 border-indigo-100',
    pending: 'bg-gray-50 text-gray-600 border-gray-200',
    running: 'bg-blue-50 text-blue-700 border-blue-100',
    completed: 'bg-emerald-50 text-emerald-700 border-emerald-100',
    failed: 'bg-red-50 text-red-700 border-red-100',
    waiting: 'bg-amber-50 text-amber-700 border-amber-100',
    cancelled: 'bg-gray-100 text-gray-600 border-gray-200',
  }
  return classes[status] ?? 'bg-gray-50 text-gray-600 border-gray-200'
}

const dotClass = (status: string) => {
  const classes: Record<string, string> = {
    created: 'bg-blue-500',
    updated: 'bg-indigo-500',
    pending: 'bg-gray-300',
    running: 'bg-blue-500',
    completed: 'bg-emerald-500',
    failed: 'bg-red-500',
    waiting: 'bg-amber-500',
    cancelled: 'bg-gray-400',
  }
  return classes[status] ?? 'bg-gray-300'
}

const eventLabel = (event: ChatRuntimeEvent) => {
  if (props.mode === 'public') {
    const publicLabels: Record<string, string> = {
      step: '步骤',
      tool: '执行',
      wait: '等待',
      error: '异常',
      done: '完成',
    }
    return publicLabels[String(event.type)] ?? '事件'
  }
  const labels: Record<string, string> = {
    step: 'Step',
    tool: 'Tool',
    wait: 'Wait',
    error: 'Error',
    done: 'Done',
  }
  return labels[String(event.type)] ?? String(event.type)
}

const stepTitle = (step: ChatRuntimeStep) => {
  return step.key || step.id || 'Step'
}

const stepDescription = (step: ChatRuntimeStep) => {
  return step.description || step.result || step.error || ''
}

const missingInfo = (event: ChatRuntimeEvent) => {
  const raw = event.payload?.missing_info ?? event.payload?.missing_fields ?? []
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => {
      if (typeof item === 'string') return item
      if (item && typeof item === 'object') {
        return item.label || item.name || item.field || item.description || JSON.stringify(item)
      }
      return String(item || '')
    })
    .filter((item) => item.trim() !== '')
}

const eventSummary = (event: ChatRuntimeEvent) => {
  return (
    event.summary ||
    event.payload?.output_summary ||
    event.payload?.input_summary ||
    event.payload?.reason ||
    ''
  )
}

const eventTitle = (event: ChatRuntimeEvent) => {
  if (props.mode === 'public' && event.type === 'tool') {
    if (event.status === 'running') return '正在处理'
    if (event.status === 'failed') return '处理失败'
    return '处理完成'
  }
  return event.title || eventLabel(event)
}
</script>

<template>
  <div
    v-if="props.runtime_events.length > 0"
    class="w-full max-w-[720px] overflow-hidden rounded-lg border border-gray-200 bg-white"
  >
    <button
      type="button"
      class="flex h-10 w-full items-center justify-between gap-3 bg-gray-50 px-3 text-left text-gray-700"
      @click="visible = !visible"
    >
      <div class="flex min-w-0 items-center gap-2">
        <icon-list class="shrink-0 text-gray-500" />
        <span class="truncate text-sm font-medium">{{ panelTitle }}</span>
        <span
          v-if="latestPlan"
          :class="`shrink-0 rounded-full border px-2 py-0.5 text-[11px] ${statusClass(latestPlan.status)}`"
        >
          {{ statusLabel(latestPlan.status) }}
        </span>
      </div>
      <div class="shrink-0 text-gray-500">
        <icon-loading v-if="props.loading" />
        <icon-up v-else-if="visible" />
        <icon-down v-else />
      </div>
    </button>

    <div v-if="visible" class="space-y-3 p-3">
      <div v-if="latestPlan" class="space-y-2">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="truncate text-sm font-semibold text-gray-800">
              {{ latestPlan.title || '执行计划' }}
            </div>
            <div v-if="latestPlan.goal" class="mt-1 line-clamp-2 text-xs leading-5 text-gray-500">
              {{ latestPlan.goal }}
            </div>
          </div>
          <div class="shrink-0 text-xs text-gray-400">{{ planSteps.length }} Steps</div>
        </div>

        <div v-if="planSteps.length > 0" class="space-y-2">
          <div
            v-for="step in planSteps"
            :key="step.id || step.key"
            class="grid grid-cols-[16px_minmax(0,1fr)] gap-2 rounded-lg border border-gray-100 bg-gray-50 p-2"
          >
            <div :class="`mt-1 h-2.5 w-2.5 rounded-full ${dotClass(step.status)}`"></div>
            <div class="min-w-0 space-y-1">
              <div class="flex min-w-0 items-center gap-2">
                <span class="truncate text-xs font-medium text-gray-800">{{ stepTitle(step) }}</span>
                <span
                  :class="`shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] ${statusClass(step.status)}`"
                >
                  {{ statusLabel(step.status) }}
                </span>
                <span
                  v-if="step.worker_name"
                  class="min-w-0 truncate rounded-full border border-gray-200 bg-white px-1.5 py-0.5 text-[10px] text-gray-500"
                >
                  {{ step.worker_name }}
                </span>
              </div>
              <div v-if="stepDescription(step)" class="line-clamp-2 text-xs leading-5 text-gray-500">
                {{ stepDescription(step) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="waitEvents.length > 0" class="space-y-2">
        <div
          v-for="event in waitEvents"
          :key="`${event.id}:wait-card`"
          class="rounded-lg border border-amber-200 bg-amber-50 p-3"
        >
          <div class="flex items-center gap-2 text-sm font-medium text-amber-800">
            <icon-exclamation-circle />
            {{ event.title || '等待用户补充信息' }}
          </div>
          <div v-if="eventSummary(event)" class="mt-1 line-clamp-3 text-xs leading-5 text-amber-700">
            {{ eventSummary(event) }}
          </div>
          <div v-if="missingInfo(event).length > 0" class="mt-2 flex flex-wrap gap-1">
            <span
              v-for="item in missingInfo(event)"
              :key="item"
              class="rounded-md border border-amber-200 bg-white px-2 py-0.5 text-[11px] text-amber-700"
            >
              {{ item }}
            </span>
          </div>
          <div v-if="event.payload?.resume_operation" class="mt-2 text-[11px] text-amber-700">
            {{ event.payload.resume_operation }}
          </div>
        </div>
      </div>

      <div v-if="timelineEvents.length > 0" class="space-y-2">
        <div
          v-for="event in timelineEvents"
          :key="event.id"
          class="grid grid-cols-[18px_minmax(0,1fr)] gap-2"
        >
          <div :class="`mt-1.5 h-2 w-2 rounded-full ${dotClass(event.status)}`"></div>
          <div class="min-w-0 border-b border-gray-100 pb-2 last:border-b-0 last:pb-0">
            <div class="flex min-w-0 items-center gap-2">
              <span class="shrink-0 text-[11px] font-medium text-gray-400">{{ eventLabel(event) }}</span>
              <span class="truncate text-xs font-medium text-gray-700">{{ eventTitle(event) }}</span>
              <span
                :class="`shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] ${statusClass(event.status)}`"
              >
                {{ statusLabel(event.status) }}
              </span>
            </div>
            <div v-if="eventSummary(event)" class="mt-1 line-clamp-2 text-xs leading-5 text-gray-500">
              {{ eventSummary(event) }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
