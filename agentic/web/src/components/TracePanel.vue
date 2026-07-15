<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Activity,
  AlertCircle,
  Bot,
  Braces,
  CheckCircle2,
  RefreshCw,
  Route,
  Timer,
  Wrench,
  X,
} from 'lucide-vue-next'
import { runsApi } from '@/lib/api/runs'
import UiState from '@/components/ui/UiState.vue'
import type {
  AgentRun,
  ModelCallRecord,
  RunDetailData,
  RunStatus,
  RunStepRecord,
  RunTraceStatus,
  ToolCallRecord,
  TraceEventRecord,
} from '@/lib/api/types'

type TraceTab = 'timeline' | 'steps' | 'tools' | 'models'
type TagType = 'success' | 'warning' | 'info' | 'danger'

const props = defineProps<{
  sessionId: string
}>()

const emit = defineEmits<{
  close: []
}>()

const runs = ref<AgentRun[]>([])
const selectedRunId = ref<string | null>(null)
const detail = ref<RunDetailData | null>(null)
const loadingRuns = ref(false)
const loadingDetail = ref(false)
const error = ref<string | null>(null)
const activeTab = ref<TraceTab>('timeline')
const lastLoadedAt = ref<number | null>(null)
let requestSeq = 0

const selectedRun = computed(() => detail.value?.run || runs.value.find((run) => run.id === selectedRunId.value) || null)

const orderedEvents = computed(() => {
  return [...(detail.value?.events || [])].sort((a, b) => toTime(a.created_at) - toTime(b.created_at))
})

const orderedSteps = computed(() => {
  return [...(detail.value?.steps || [])].sort((a, b) => toTime(a.created_at) - toTime(b.created_at))
})

const orderedToolCalls = computed(() => {
  return [...(detail.value?.tool_calls || [])].sort((a, b) => toTime(a.created_at) - toTime(b.created_at))
})

const orderedModelCalls = computed(() => {
  return [...(detail.value?.model_calls || [])].sort((a, b) => toTime(a.created_at) - toTime(b.created_at))
})

const totalTokens = computed(() =>
  orderedModelCalls.value.reduce((sum, call) => sum + Number(call.total_tokens || 0), 0),
)

const summaryStats = computed(() => [
  { label: '事件', value: String(orderedEvents.value.length), icon: Activity },
  { label: '步骤', value: String(orderedSteps.value.length), icon: Route },
  { label: '工具', value: String(orderedToolCalls.value.length), icon: Wrench },
  { label: '模型', value: String(orderedModelCalls.value.length), icon: Bot },
  { label: 'Token', value: totalTokens.value > 0 ? formatNumber(totalTokens.value) : '-', icon: Braces },
  { label: '耗时', value: selectedRun.value ? formatRunDuration(selectedRun.value) : '-', icon: Timer },
])

const lastLoadedLabel = computed(() => {
  if (!lastLoadedAt.value) return ''
  return formatShortTime(new Date(lastLoadedAt.value).toISOString())
})

const tabs = computed(() => [
  { key: 'timeline' as const, label: '时间线', count: orderedEvents.value.length, icon: Activity },
  { key: 'steps' as const, label: '步骤', count: orderedSteps.value.length, icon: Route },
  { key: 'tools' as const, label: '工具', count: orderedToolCalls.value.length, icon: Wrench },
  { key: 'models' as const, label: '模型', count: orderedModelCalls.value.length, icon: Bot },
])

watch(
  () => props.sessionId,
  () => {
    void loadRuns(false)
  },
  { immediate: true },
)

async function loadRuns(keepSelection = true) {
  const seq = ++requestSeq
  loadingRuns.value = true
  error.value = null

  try {
    const data = await runsApi.listRuns({ session_id: props.sessionId, limit: 30 })
    if (seq !== requestSeq) return

    runs.value = data.runs || []
    const currentId = keepSelection && selectedRunId.value
      ? runs.value.find((run) => run.id === selectedRunId.value)?.id
      : null
    const nextId = currentId || runs.value[0]?.id || null
    selectedRunId.value = nextId
    lastLoadedAt.value = Date.now()

    if (nextId) {
      await loadRunDetail(nextId, seq)
    } else {
      detail.value = null
    }
  } catch (err) {
    if (seq !== requestSeq) return
    error.value = err instanceof Error ? err.message : '加载运行记录失败'
    detail.value = null
  } finally {
    if (seq === requestSeq) {
      loadingRuns.value = false
    }
  }
}

async function loadRunDetail(runId: string, seq = requestSeq) {
  loadingDetail.value = true
  error.value = null
  if (detail.value?.run.id !== runId) {
    detail.value = null
  }

  try {
    const data = await runsApi.getRun(runId)
    if (seq !== requestSeq) return
    detail.value = data
  } catch (err) {
    if (seq !== requestSeq) return
    error.value = err instanceof Error ? err.message : '加载 Trace 详情失败'
    detail.value = null
  } finally {
    if (seq === requestSeq) {
      loadingDetail.value = false
    }
  }
}

function selectRun(run: AgentRun) {
  if (run.id === selectedRunId.value) return
  const seq = ++requestSeq
  selectedRunId.value = run.id
  void loadRunDetail(run.id, seq)
}

function refreshTrace() {
  void loadRuns(true)
}

function toTime(value?: string | null): number {
  if (!value) return 0
  const time = new Date(value).getTime()
  return Number.isFinite(time) ? time : 0
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value)
}

function formatDateTime(value?: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

function formatShortTime(value?: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

function formatElapsed(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return '-'
  const ms = Number(value)
  if (ms < 1000) return `${ms} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`
  const minutes = Math.floor(ms / 60_000)
  const seconds = Math.round((ms % 60_000) / 1000)
  return `${minutes}m ${seconds}s`
}

function formatRunDuration(run: AgentRun): string {
  return formatDurationRange(run.started_at || run.created_at, run.finished_at, run.status)
}

function formatStepDuration(step: RunStepRecord): string {
  return formatDurationRange(step.started_at || step.created_at, step.finished_at, step.status)
}

function formatDurationRange(startValue?: string | null, endValue?: string | null, status?: string | null): string {
  const start = toTime(startValue)
  const active = status === 'running' || status === 'started' || status === 'calling'
  const end = endValue ? toTime(endValue) : active ? Date.now() : 0
  if (!start || !end || end < start) return '-'
  return formatElapsed(end - start)
}

function runTitle(run: AgentRun): string {
  const text = (run.input_summary || run.final_summary || run.trace_id || run.id).replace(/\s+/g, ' ').trim()
  return text || run.id
}

function clipText(value: string, max = 160): string {
  if (value.length <= max) return value
  return `${value.slice(0, max)}...`
}

function statusLabel(status?: RunStatus | RunTraceStatus | string | null): string {
  switch (status) {
    case 'pending':
      return '待运行'
    case 'running':
    case 'started':
      return '运行中'
    case 'waiting':
      return '等待'
    case 'completed':
    case 'succeeded':
    case 'called':
      return '完成'
    case 'calling':
      return '调用中'
    case 'blocked':
      return '阻断'
    case 'failed':
      return '失败'
    default:
      return status || '-'
  }
}

function statusTagType(status?: RunStatus | RunTraceStatus | string | null): TagType {
  if (status === 'completed' || status === 'succeeded' || status === 'called') return 'success'
  if (status === 'running' || status === 'started' || status === 'calling') return 'warning'
  if (status === 'failed' || status === 'blocked') return 'danger'
  return 'info'
}

function riskTagType(risk?: string | null): TagType {
  if (risk === 'high') return 'danger'
  if (risk === 'medium') return 'warning'
  return 'info'
}

function eventGroup(eventType: string): 'model' | 'tool' | 'step' | 'error' | 'run' | 'event' {
  if (eventType.startsWith('model.')) return 'model'
  if (eventType.startsWith('tool.')) return 'tool'
  if (eventType.startsWith('step.') || eventType.startsWith('plan.')) return 'step'
  if (eventType.startsWith('error.')) return 'error'
  if (eventType.startsWith('run.') || eventType.startsWith('done.')) return 'run'
  return 'event'
}

function eventIcon(eventType: string) {
  const group = eventGroup(eventType)
  if (group === 'model') return Bot
  if (group === 'tool') return Wrench
  if (group === 'step') return Route
  if (group === 'error') return AlertCircle
  if (group === 'run') return CheckCircle2
  return Activity
}

function eventTypeLabel(eventType: string): string {
  return eventType.replace(/\./g, ' / ')
}

function formatJson(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function previewValue(value: unknown, fallback = '暂无数据'): string {
  const text = formatJson(value).trim()
  return text || fallback
}

function eventPreview(event: TraceEventRecord): string {
  return previewValue(event.payload, '无 payload')
}

function toolResultPreview(call: ToolCallRecord): string {
  if (call.error) return call.error
  return call.result_preview || previewValue(call.result, '等待结果')
}

function modelRequestPreview(call: ModelCallRecord): string {
  return previewValue(call.request_preview, '无请求摘要')
}

function modelResponsePreview(call: ModelCallRecord): string {
  if (call.error) return call.error
  return previewValue(call.response_preview, '等待响应')
}

function stepResultPreview(step: RunStepRecord): string {
  if (step.error) return step.error
  return step.result_summary || '暂无结果'
}
</script>

<template>
  <aside class="preview-panel trace-panel" role="dialog" aria-modal="true" aria-label="运行 Trace">
    <header class="trace-header">
      <div class="trace-title">
        <span class="trace-title-icon">
          <Activity :size="18" />
        </span>
        <div>
          <p>运行 Trace</p>
          <span>{{ selectedRun?.trace_id || '无运行记录' }}</span>
        </div>
      </div>

      <div class="trace-actions">
        <button
          class="icon-button subtle"
          type="button"
          title="刷新 Trace"
          :disabled="loadingRuns || loadingDetail"
          @click="refreshTrace"
        >
          <RefreshCw :size="16" :class="{ spinning: loadingRuns || loadingDetail }" />
        </button>
        <button class="icon-button subtle" type="button" aria-label="关闭 Trace" title="关闭" @click="emit('close')">
          <X :size="16" />
        </button>
      </div>
    </header>

    <div class="trace-body">
      <div v-if="error" class="trace-error">
        <AlertCircle :size="16" />
        <span>{{ error }}</span>
      </div>

      <div class="run-strip">
        <button
          v-for="run in runs"
          :key="run.id"
          class="run-item"
          :class="{ active: run.id === selectedRunId }"
          type="button"
          @click="selectRun(run)"
        >
          <span class="run-item-main">
            <ElTag size="small" round effect="light" :type="statusTagType(run.status)">
              {{ statusLabel(run.status) }}
            </ElTag>
            <strong :title="runTitle(run)">{{ clipText(runTitle(run), 42) }}</strong>
          </span>
          <span class="run-item-meta">
            {{ formatDateTime(run.created_at) }} · {{ formatRunDuration(run) }}
          </span>
        </button>

        <UiState v-if="loadingRuns && runs.length === 0" kind="loading" compact title="正在加载运行记录" />
        <UiState v-else-if="!loadingRuns && runs.length === 0" compact title="暂无运行记录" />
      </div>

      <template v-if="detail && selectedRun">
        <section class="run-summary">
          <div class="run-heading">
            <div>
              <p>{{ clipText(runTitle(selectedRun), 88) }}</p>
              <span>{{ formatDateTime(selectedRun.started_at || selectedRun.created_at) }}</span>
            </div>
            <ElTag size="small" round effect="light" :type="statusTagType(selectedRun.status)">
              {{ statusLabel(selectedRun.status) }}
            </ElTag>
          </div>

          <div class="summary-grid">
            <div v-for="item in summaryStats" :key="item.label" class="summary-cell">
              <component :is="item.icon" :size="14" />
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </section>

        <nav class="trace-tabs" aria-label="Trace 详情">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            type="button"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            <component :is="tab.icon" :size="14" />
            <span>{{ tab.label }}</span>
            <strong>{{ tab.count }}</strong>
          </button>
        </nav>

        <div class="trace-content">
          <section v-if="activeTab === 'timeline'" class="trace-list">
            <article
              v-for="event in orderedEvents"
              :key="event.id"
              class="timeline-event"
              :class="`group-${eventGroup(event.event_type)}`"
            >
              <div class="timeline-marker">
                <component :is="eventIcon(event.event_type)" :size="14" />
              </div>
              <div class="timeline-event-body">
                <header>
                  <strong>{{ eventTypeLabel(event.event_type) }}</strong>
                  <span>{{ formatShortTime(event.created_at) }}</span>
                </header>
                <pre>{{ eventPreview(event) }}</pre>
              </div>
            </article>

            <UiState v-if="orderedEvents.length === 0" compact title="暂无事件" />
          </section>

          <section v-else-if="activeTab === 'steps'" class="trace-list">
            <article v-for="step in orderedSteps" :key="step.id" class="trace-record">
              <header class="record-header">
                <div>
                  <Route :size="15" />
                  <strong>{{ step.description || step.step_id }}</strong>
                </div>
                <ElTag size="small" round effect="light" :type="statusTagType(step.status)">
                  {{ statusLabel(step.status) }}
                </ElTag>
              </header>
              <div class="record-meta">
                <span>{{ formatDateTime(step.started_at || step.created_at) }}</span>
                <span>{{ formatStepDuration(step) }}</span>
              </div>
              <pre>{{ stepResultPreview(step) }}</pre>
            </article>

            <UiState v-if="orderedSteps.length === 0" compact title="暂无步骤" />
          </section>

          <section v-else-if="activeTab === 'tools'" class="trace-list">
            <article v-for="call in orderedToolCalls" :key="call.id" class="trace-record">
              <header class="record-header">
                <div>
                  <Wrench :size="15" />
                  <strong>{{ call.tool_id || call.function_name }}</strong>
                </div>
                <ElTag size="small" round effect="light" :type="statusTagType(call.status)">
                  {{ statusLabel(call.status) }}
                </ElTag>
              </header>
              <div class="record-meta">
                <span>{{ call.executor_type || 'tool' }}</span>
                <span>{{ call.source_type || 'unknown' }}</span>
                <ElTag v-if="call.risk_level" size="small" effect="plain" :type="riskTagType(call.risk_level)">
                  {{ call.risk_level }}
                </ElTag>
                <span>{{ formatElapsed(call.latency_ms) }}</span>
              </div>
              <div class="record-split">
                <section>
                  <h3>参数</h3>
                  <pre>{{ call.arguments_preview || previewValue(call.arguments, '暂无参数') }}</pre>
                </section>
                <section>
                  <h3>结果</h3>
                  <pre>{{ toolResultPreview(call) }}</pre>
                </section>
              </div>
            </article>

            <UiState v-if="orderedToolCalls.length === 0" compact title="暂无工具调用" />
          </section>

          <section v-else class="trace-list">
            <article v-for="call in orderedModelCalls" :key="call.id" class="trace-record">
              <header class="record-header">
                <div>
                  <Bot :size="15" />
                  <strong>{{ call.model_name || call.provider || 'model' }}</strong>
                </div>
                <ElTag size="small" round effect="light" :type="statusTagType(call.status)">
                  {{ statusLabel(call.status) }}
                </ElTag>
              </header>
              <div class="record-meta">
                <span>{{ call.agent_name }}</span>
                <span>{{ call.provider || 'provider' }}</span>
                <span>{{ call.message_count }} messages</span>
                <span>{{ call.tool_schema_count }} tools</span>
                <span>{{ call.total_tokens ? `${formatNumber(call.total_tokens)} tokens` : 'tokens -' }}</span>
                <span>{{ formatElapsed(call.latency_ms) }}</span>
              </div>
              <div class="record-split">
                <section>
                  <h3>请求</h3>
                  <pre>{{ modelRequestPreview(call) }}</pre>
                </section>
                <section>
                  <h3>响应</h3>
                  <pre>{{ modelResponsePreview(call) }}</pre>
                </section>
              </div>
            </article>

            <UiState v-if="orderedModelCalls.length === 0" compact title="暂无模型调用" />
          </section>
        </div>
      </template>

      <UiState v-else-if="loadingDetail" class="trace-loading" kind="loading" title="正在加载 Trace" />
    </div>

    <footer class="trace-footer">
      <span v-if="lastLoadedLabel">刷新于 {{ lastLoadedLabel }}</span>
      <span v-else>Trace</span>
      <span v-if="selectedRun">{{ selectedRun.id }}</span>
    </footer>
  </aside>
</template>

<style scoped>
.trace-panel {
  border-left: 1px solid var(--border-light);
  background: var(--surface-secondary);
}

.trace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 64px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-light);
  background: var(--surface-primary);
}

.trace-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.trace-title-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  background: var(--accent-soft);
  color: var(--accent-primary);
}

.trace-title div {
  min-width: 0;
}

.trace-title p {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 750;
  line-height: 1.35;
}

.trace-title span {
  display: block;
  overflow: hidden;
  max-width: 420px;
  color: var(--text-tertiary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}

.trace-body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.trace-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 12px 0;
  padding: 9px 10px;
  border: 1px solid #fecaca;
  border-radius: 8px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 12px;
}

.run-strip {
  display: flex;
  gap: 8px;
  min-height: 82px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  overflow-x: auto;
  background: var(--surface-secondary);
}

.run-item {
  display: flex;
  flex: 0 0 248px;
  flex-direction: column;
  justify-content: center;
  gap: 7px;
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--surface-primary);
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
}

.run-item.active {
  border-color: var(--accent-primary);
  background: var(--accent-soft);
}

.run-item-main {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.run-item-main strong,
.run-item-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-item-main strong {
  min-width: 0;
  color: #1f2937;
  font-size: 12px;
  font-weight: 650;
}

.run-item-meta {
  color: #64748b;
  font-size: 11px;
}

.compact-state {
  flex: 1 1 auto;
  min-width: 180px;
}

.run-summary {
  padding: 12px;
  border-bottom: 1px solid var(--border-light);
  background: var(--surface-primary);
}

.run-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.run-heading div {
  min-width: 0;
}

.run-heading p {
  overflow: hidden;
  color: #111827;
  font-size: 14px;
  font-weight: 720;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-heading span {
  color: #64748b;
  font-size: 12px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.summary-cell {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: center;
  gap: 4px 7px;
  min-width: 0;
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  color: #64748b;
  font-size: 11px;
}

.summary-cell strong {
  grid-column: 1 / -1;
  overflow: hidden;
  color: #111827;
  font-size: 16px;
  font-weight: 750;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-tabs {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  background: var(--surface-secondary);
}

.trace-tabs button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 0;
  min-height: 32px;
  padding: 0 8px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--surface-primary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 650;
}

.trace-tabs button.active {
  border-color: var(--accent-primary);
  background: var(--accent-soft);
  color: var(--accent-primary);
}

.trace-tabs strong {
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}

.trace-content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  background: #f8fafc;
}

.trace-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
}

.timeline-event {
  position: relative;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 8px;
}

.timeline-event::before {
  content: '';
  position: absolute;
  top: 30px;
  bottom: -10px;
  left: 14px;
  width: 1px;
  background: #dbe3ef;
}

.timeline-event:last-child::before {
  display: none;
}

.timeline-marker {
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #ffffff;
  color: #64748b;
}

.group-model .timeline-marker {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #2563eb;
}

.group-tool .timeline-marker {
  border-color: #fed7aa;
  background: #fff7ed;
  color: #c2410c;
}

.group-step .timeline-marker {
  border-color: #bbf7d0;
  background: #f0fdf4;
  color: #15803d;
}

.group-error .timeline-marker {
  border-color: #fecaca;
  background: #fef2f2;
  color: #dc2626;
}

.timeline-event-body,
.trace-record {
  min-width: 0;
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}

.timeline-event-body header,
.record-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.timeline-event-body header strong,
.record-header strong {
  overflow: hidden;
  color: #111827;
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-event-body header span,
.record-meta {
  color: #64748b;
  font-size: 11px;
}

.record-header div {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.record-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin-top: 7px;
}

pre {
  margin: 8px 0 0;
  max-height: 260px;
  overflow: auto;
  border: 1px solid #edf2f7;
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 11px;
  line-height: 1.55;
  overflow-wrap: anywhere;
  padding: 9px;
  white-space: pre-wrap;
}

.record-split {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  margin-top: 9px;
}

.record-split h3 {
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.trace-loading {
  gap: 8px;
}

.trace-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 34px;
  padding: 7px 12px;
  border-top: 1px solid #e2e8f0;
  background: #ffffff;
  color: #64748b;
  font-size: 11px;
}

.trace-footer span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spinning {
  animation: trace-spin 0.8s linear infinite;
}

@keyframes trace-spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 720px) {
  .trace-title span {
    max-width: 260px;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trace-tabs {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
