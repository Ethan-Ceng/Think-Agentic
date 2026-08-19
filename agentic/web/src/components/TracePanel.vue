<script setup lang="ts">
import { computed, ref, watch, type Component } from 'vue'
import {
  Activity,
  AlertCircle,
  Bot,
  Braces,
  Clock3,
  ListTree,
  RefreshCw,
  Sparkles,
  Timer,
  Wrench,
  X,
} from 'lucide-vue-next'
import ExecutionTree from '@/components/chat/ExecutionTree.vue'
import RunSkillsPanel from '@/components/skills/RunSkillsPanel.vue'
import UiState from '@/components/ui/UiState.vue'
import { runsApi } from '@/lib/api/runs'
import type {
  AgentRun,
  ModelCallRecord,
  RunExecutionView,
  ToolCallRecord,
  TraceEventRecord,
} from '@/lib/api/types'
import type { RunSkill } from '@/types/skill'

type TraceTab = 'execution' | 'overview' | 'tools' | 'models' | 'skills' | 'events'
type ResourceTab = Exclude<TraceTab, 'execution' | 'overview'>

const props = defineProps<{ sessionId: string }>()
const emit = defineEmits<{ close: [] }>()

const runs = ref<AgentRun[]>([])
const selectedRunId = ref<string | null>(null)
const execution = ref<RunExecutionView | null>(null)
const activeTab = ref<TraceTab>('execution')
const loadingRuns = ref(false)
const loadingExecution = ref(false)
const error = ref('')
const lastLoadedAt = ref<number | null>(null)
const toolCalls = ref<ToolCallRecord[]>([])
const modelCalls = ref<ModelCallRecord[]>([])
const events = ref<TraceEventRecord[]>([])
const skills = ref<RunSkill[]>([])
const resourceLoading = ref<Record<ResourceTab, boolean>>({
  tools: false,
  models: false,
  skills: false,
  events: false,
})
const resourceLoaded = ref<Record<ResourceTab, boolean>>({
  tools: false,
  models: false,
  skills: false,
  events: false,
})
const resourceHasMore = ref<Record<'tools' | 'models' | 'events', boolean>>({
  tools: false,
  models: false,
  events: false,
})
const resourceCursor = ref<Record<'tools' | 'models' | 'events', string | number | null>>({
  tools: null,
  models: null,
  events: null,
})
let requestVersion = 0

const selectedRun = computed(
  () => runs.value.find((run) => run.id === selectedRunId.value) || null,
)
const totalTokens = computed(() =>
  modelCalls.value.reduce((sum, call) => sum + Number(call.total_tokens || 0), 0),
)
const summaryStats = computed(() => {
  const metrics = execution.value?.run.metrics || {}
  return [
    { label: '步骤', value: metrics.step_count ?? 0, icon: ListTree },
    { label: '工具', value: metrics.tool_count ?? 0, icon: Wrench },
    { label: '模型', value: metrics.model_count ?? 0, icon: Bot },
    { label: 'Token', value: totalTokens.value || '-', icon: Braces },
    { label: '耗时', value: formatElapsed(execution.value?.run.latency_ms), icon: Timer },
    { label: 'Trace', value: execution.value?.trace_complete === false ? '不完整' : '完整', icon: Activity },
  ]
})
const tabs = computed<Array<{ key: TraceTab; label: string; icon: Component; count?: number }>>(() => [
  { key: 'execution', label: '执行链', icon: ListTree, count: execution.value?.nodes.length || 0 },
  { key: 'overview', label: '概览', icon: Activity },
  { key: 'tools', label: '工具', icon: Wrench, count: toolCalls.value.length },
  { key: 'models', label: '模型', icon: Bot, count: modelCalls.value.length },
  { key: 'skills', label: 'Skills', icon: Sparkles, count: skills.value.length },
  { key: 'events', label: '技术事件', icon: Clock3, count: events.value.length },
])

watch(
  () => props.sessionId,
  () => void loadRuns(false),
  { immediate: true },
)

watch(activeTab, (tab) => {
  if (tab !== 'execution' && tab !== 'overview') void loadResource(tab)
})

async function loadRuns(keepSelection = true): Promise<void> {
  const version = ++requestVersion
  loadingRuns.value = true
  error.value = ''
  try {
    const data = await runsApi.listRuns({ session_id: props.sessionId, limit: 30 })
    if (version !== requestVersion) return
    runs.value = data.runs || []
    const retained = keepSelection
      ? runs.value.find((run) => run.id === selectedRunId.value)?.id
      : null
    const next = retained || runs.value[0]?.id || null
    if (next !== selectedRunId.value) resetRunResources()
    selectedRunId.value = next
    lastLoadedAt.value = Date.now()
    if (next) await loadExecution(next, Boolean(retained && execution.value), version)
    else execution.value = null
  } catch (reason) {
    if (version === requestVersion) error.value = errorMessage(reason, '加载运行记录失败')
  } finally {
    if (version === requestVersion) loadingRuns.value = false
  }
}

async function loadExecution(
  runId: string,
  incremental: boolean,
  version = requestVersion,
): Promise<void> {
  loadingExecution.value = true
  try {
    let after = incremental ? execution.value?.next_cursor ?? undefined : undefined
    let hasMore = true
    let merged = incremental ? execution.value : null
    while (hasMore) {
      const page = await runsApi.getExecution(runId, {
        after,
        limit: 200,
        detail: 'detail',
      })
      if (version !== requestVersion || runId !== selectedRunId.value) return
      merged = mergeExecutionViews(merged, page)
      hasMore = page.has_more
      if (!hasMore || page.next_cursor == null || page.next_cursor === after) break
      after = page.next_cursor
    }
    execution.value = merged
  } catch (reason) {
    if (version === requestVersion) error.value = errorMessage(reason, '加载执行链失败')
  } finally {
    if (version === requestVersion) loadingExecution.value = false
  }
}

function selectRun(run: AgentRun): void {
  if (run.id === selectedRunId.value) return
  requestVersion += 1
  selectedRunId.value = run.id
  activeTab.value = 'execution'
  error.value = ''
  resetRunResources()
  void loadExecution(run.id, false)
}

function refreshTrace(): void {
  void loadRuns(true).then(() => {
    if (activeTab.value !== 'execution' && activeTab.value !== 'overview') {
      void loadResource(activeTab.value, true)
    }
  })
}

function resetRunResources(): void {
  execution.value = null
  toolCalls.value = []
  modelCalls.value = []
  events.value = []
  skills.value = []
  resourceLoaded.value = { tools: false, models: false, skills: false, events: false }
  resourceHasMore.value = { tools: false, models: false, events: false }
  resourceCursor.value = { tools: null, models: null, events: null }
}

async function loadResource(tab: ResourceTab, reset = false): Promise<void> {
  const runId = selectedRunId.value
  if (!runId || resourceLoading.value[tab]) return
  if (!reset && resourceLoaded.value[tab] && tab === 'skills') return
  if (
    !reset &&
    tab !== 'skills' &&
    resourceLoaded.value[tab] &&
    !resourceHasMore.value[tab]
  ) return
  resourceLoading.value = { ...resourceLoading.value, [tab]: true }
  try {
    if (tab === 'tools') {
      const data = await runsApi.listToolCalls(runId, {
        after: reset ? undefined : (resourceCursor.value.tools as string | null) || undefined,
        limit: 100,
      })
      toolCalls.value = reset ? data.tool_calls : mergeRecords(toolCalls.value, data.tool_calls)
      resourceCursor.value = { ...resourceCursor.value, tools: data.next_cursor }
      resourceHasMore.value = { ...resourceHasMore.value, tools: data.has_more }
    } else if (tab === 'models') {
      const data = await runsApi.listModelCalls(runId, {
        after: reset ? undefined : (resourceCursor.value.models as string | null) || undefined,
        limit: 100,
      })
      modelCalls.value = reset ? data.model_calls : mergeRecords(modelCalls.value, data.model_calls)
      resourceCursor.value = { ...resourceCursor.value, models: data.next_cursor }
      resourceHasMore.value = { ...resourceHasMore.value, models: data.has_more }
    } else if (tab === 'events') {
      const data = await runsApi.listEvents(runId, {
        after: reset ? undefined : Number(resourceCursor.value.events || 0) || undefined,
        limit: 100,
      })
      events.value = reset ? data.events : mergeRecords(events.value, data.events)
      resourceCursor.value = { ...resourceCursor.value, events: data.next_cursor }
      resourceHasMore.value = { ...resourceHasMore.value, events: data.has_more }
    } else {
      skills.value = await runsApi.listSkills(runId)
    }
    resourceLoaded.value = { ...resourceLoaded.value, [tab]: true }
  } catch (reason) {
    error.value = errorMessage(reason, `加载${tab}记录失败`)
  } finally {
    resourceLoading.value = { ...resourceLoading.value, [tab]: false }
  }
}

function mergeExecutionViews(
  current: RunExecutionView | null,
  incoming: RunExecutionView,
): RunExecutionView {
  if (!current) return incoming
  const nodes = new Map(current.nodes.map((node) => [node.node_id, node]))
  for (const node of incoming.nodes) {
    const existing = nodes.get(node.node_id)
    if (!existing || node.cursor >= existing.cursor) nodes.set(node.node_id, node)
  }
  const mergedNodes = [...nodes.values()].sort(
    (a, b) => a.cursor - b.cursor || a.node_id.localeCompare(b.node_id),
  )
  const stepNodes = mergedNodes.filter((node) => node.kind === 'step')
  return {
    ...incoming,
    run: {
      ...current.run,
      ...incoming.run,
      mode: incoming.run.mode || current.run.mode,
      summary: incoming.run.summary || current.run.summary,
      metrics: {
        ...current.run.metrics,
        ...incoming.run.metrics,
        step_count: stepNodes.length,
        completed_steps: stepNodes.filter((node) => node.status === 'succeeded').length,
        tool_count: mergedNodes.filter((node) => node.kind === 'tool').length,
        model_count: mergedNodes.filter((node) => node.kind === 'model').length,
        replan_count: Math.max(
          ...mergedNodes.map((node) => node.metrics.replan_count || 0),
          0,
        ),
      },
    },
    nodes: mergedNodes,
    trace_complete: current.trace_complete && incoming.trace_complete,
    warnings: [...new Set([...current.warnings, ...incoming.warnings])],
  }
}

function mergeRecords<T extends { id: string }>(current: T[], incoming: T[]): T[] {
  const records = new Map(current.map((item) => [item.id, item]))
  for (const item of incoming) records.set(item.id, item)
  return [...records.values()]
}

function runLabel(run: AgentRun): string {
  return `Run ${run.id.slice(0, 8)}`
}

function statusLabel(status?: string | null): string {
  const labels: Record<string, string> = {
    pending: '待运行',
    running: '运行中',
    waiting: '等待输入',
    completed: '已完成',
    succeeded: '已完成',
    failed: '失败',
    calling: '调用中',
    called: '已完成',
  }
  return labels[status || ''] || status || '-'
}

function formatElapsed(value?: number | null): string {
  if (value == null || !Number.isFinite(Number(value))) return '-'
  const ms = Number(value)
  if (ms < 1000) return `${ms} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`
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

function errorMessage(value: unknown, fallback: string): string {
  return value instanceof Error ? value.message : fallback
}
</script>

<template>
  <aside class="preview-panel trace-panel" role="dialog" aria-modal="true" aria-label="运行 Trace">
    <header class="trace-header">
      <div class="trace-title">
        <span class="trace-title-icon"><Activity :size="18" /></span>
        <div><p>运行 Trace</p><span>{{ selectedRun ? runLabel(selectedRun) : '无运行记录' }}</span></div>
      </div>
      <div class="trace-actions">
        <button class="icon-button subtle" type="button" title="刷新 Trace" :disabled="loadingRuns || loadingExecution" @click="refreshTrace">
          <RefreshCw :size="16" :class="{ spinning: loadingRuns || loadingExecution }" />
        </button>
        <button class="icon-button subtle" type="button" aria-label="关闭 Trace" @click="emit('close')"><X :size="16" /></button>
      </div>
    </header>

    <div class="trace-body">
      <div v-if="error" class="trace-error"><AlertCircle :size="16" /><span>{{ error }}</span></div>
      <div class="run-strip">
        <button v-for="run in runs" :key="run.id" class="run-item" :class="{ active: run.id === selectedRunId }" type="button" @click="selectRun(run)">
          <span class="run-item-main"><strong>{{ runLabel(run) }}</strong><em :class="`status-${run.status}`">{{ statusLabel(run.status) }}</em></span>
          <span class="run-item-meta">{{ formatDateTime(run.started_at || run.created_at) }}</span>
        </button>
        <UiState v-if="loadingRuns && !runs.length" kind="loading" compact title="正在加载运行记录" />
        <UiState v-else-if="!loadingRuns && !runs.length" compact title="暂无运行记录" />
      </div>

      <template v-if="selectedRun && execution">
        <section class="run-summary">
          <div class="run-heading">
            <div><p>{{ runLabel(selectedRun) }}</p><span>{{ formatDateTime(execution.run.started_at) }}</span></div>
            <strong :class="`run-status status-${execution.run.status}`">{{ statusLabel(execution.run.status) }}</strong>
          </div>
          <div class="summary-grid">
            <div v-for="item in summaryStats" :key="item.label" class="summary-cell">
              <component :is="item.icon" :size="14" /><span>{{ item.label }}</span><strong>{{ item.value }}</strong>
            </div>
          </div>
          <div v-if="!execution.trace_complete" class="trace-incomplete"><AlertCircle :size="14" />执行记录暂不完整</div>
        </section>

        <nav class="trace-tabs" aria-label="Trace 详情">
          <button v-for="tab in tabs" :key="tab.key" type="button" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
            <component :is="tab.icon" :size="14" /><span>{{ tab.label }}</span><strong v-if="tab.count != null">{{ tab.count }}</strong>
          </button>
        </nav>

        <div class="trace-content">
          <section v-if="activeTab === 'execution'" class="execution-tab">
            <ExecutionTree :nodes="execution.nodes" density="diagnostic" />
            <UiState v-if="!execution.nodes.length" compact title="暂无执行节点" />
          </section>

          <section v-else-if="activeTab === 'overview'" class="overview-tab">
            <dl>
              <dt>Run ID</dt><dd><code>{{ execution.run.run_id }}</code></dd>
              <dt>输入事件</dt><dd><code>{{ execution.run.input_event_id || '-' }}</code></dd>
              <dt>执行模式</dt><dd>{{ execution.run.mode || '-' }}</dd>
              <dt>状态</dt><dd>{{ statusLabel(execution.run.status) }}</dd>
              <dt>开始时间</dt><dd>{{ formatDateTime(execution.run.started_at) }}</dd>
              <dt>结束时间</dt><dd>{{ formatDateTime(execution.run.finished_at) }}</dd>
              <dt>总耗时</dt><dd>{{ formatElapsed(execution.run.latency_ms) }}</dd>
              <dt>最新摘要</dt><dd>{{ execution.run.summary || '-' }}</dd>
            </dl>
          </section>

          <section v-else-if="activeTab === 'tools'" class="trace-list">
            <article v-for="call in toolCalls" :key="call.id" class="trace-record">
              <header><div><Wrench :size="15" /><strong>{{ call.function_name || call.tool_id }}</strong></div><span>{{ statusLabel(call.status) }}</span></header>
              <div class="record-meta"><span>{{ call.provider_id || call.source_type || 'builtin' }}</span><span>{{ call.executor_type || 'tool' }}</span><span>{{ formatElapsed(call.latency_ms) }}</span></div>
              <dl><dt>Tool ID</dt><dd><code>{{ call.tool_id }}</code></dd><dt>参数哈希</dt><dd><code>{{ call.arguments_hash || '-' }}</code></dd><dt>Sandbox</dt><dd>{{ call.requires_sandbox ? '需要' : '不需要' }}</dd></dl>
            </article>
            <UiState v-if="resourceLoading.tools && !toolCalls.length" kind="loading" compact title="正在加载工具记录" />
            <UiState v-else-if="resourceLoaded.tools && !toolCalls.length" compact title="暂无工具调用" />
            <button v-if="resourceHasMore.tools" class="load-more" type="button" :disabled="resourceLoading.tools" @click="loadResource('tools')">加载更多</button>
          </section>

          <section v-else-if="activeTab === 'models'" class="trace-list">
            <article v-for="call in modelCalls" :key="call.id" class="trace-record">
              <header><div><Bot :size="15" /><strong>{{ call.model_name || call.provider || 'model' }}</strong></div><span>{{ statusLabel(call.status) }}</span></header>
              <div class="record-meta"><span>{{ call.agent_name }}</span><span>{{ call.provider }}</span><span>{{ call.message_count }} messages</span><span>{{ call.tool_schema_count }} tools</span></div>
              <dl><dt>首 Token</dt><dd>{{ formatElapsed(call.ttft_ms) }}</dd><dt>总耗时</dt><dd>{{ formatElapsed(call.latency_ms) }}</dd><dt>Token</dt><dd>{{ call.total_tokens ?? '-' }}</dd><dt>结束原因</dt><dd>{{ call.finish_reason || '-' }}</dd></dl>
            </article>
            <UiState v-if="resourceLoading.models && !modelCalls.length" kind="loading" compact title="正在加载模型记录" />
            <UiState v-else-if="resourceLoaded.models && !modelCalls.length" compact title="暂无模型调用" />
            <button v-if="resourceHasMore.models" class="load-more" type="button" :disabled="resourceLoading.models" @click="loadResource('models')">加载更多</button>
          </section>

          <RunSkillsPanel v-else-if="activeTab === 'skills'" :skills="skills" :events="[]" />

          <section v-else class="trace-list technical-events">
            <article v-for="event in events" :key="event.id" class="trace-record">
              <header><div><Activity :size="15" /><strong>{{ event.event_type }}</strong></div><span>#{{ event.ingest_seq ?? '-' }}</span></header>
              <p>{{ event.summary || event.event_type }}</p>
              <dl><dt>Node</dt><dd><code>{{ event.node_id || '-' }}</code></dd><dt>Parent</dt><dd><code>{{ event.parent_node_id || '-' }}</code></dd><dt>时间</dt><dd>{{ formatDateTime(event.created_at) }}</dd></dl>
            </article>
            <UiState v-if="resourceLoading.events && !events.length" kind="loading" compact title="正在加载技术事件" />
            <UiState v-else-if="resourceLoaded.events && !events.length" compact title="暂无技术事件" />
            <button v-if="resourceHasMore.events" class="load-more" type="button" :disabled="resourceLoading.events" @click="loadResource('events')">加载更多</button>
          </section>
        </div>
      </template>

      <UiState v-else-if="loadingExecution" class="trace-loading" kind="loading" title="正在加载执行链" />
    </div>

    <footer class="trace-footer"><span>{{ lastLoadedAt ? `刷新于 ${new Date(lastLoadedAt).toLocaleTimeString('zh-CN')}` : 'Trace' }}</span><span v-if="selectedRunId">{{ selectedRunId }}</span></footer>
  </aside>
</template>

<style scoped>
.trace-panel { border-left: 1px solid var(--border-light); background: var(--surface-secondary); }
.trace-header, .trace-title, .trace-actions, .run-item-main, .run-heading, .trace-record header, .trace-record header div, .record-meta, .trace-incomplete { display: flex; align-items: center; }
.trace-header { justify-content: space-between; gap: 12px; min-height: 64px; padding: 12px 14px; border-bottom: 1px solid var(--border-light); background: var(--surface-primary); }
.trace-title { gap: 10px; min-width: 0; }.trace-title-icon { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; border: 1px solid var(--border-light); border-radius: var(--radius-md); background: var(--accent-soft); color: var(--accent-primary); }
.trace-title p { color: var(--text-primary); font-size: 15px; font-weight: 750; }.trace-title span { color: var(--text-tertiary); font-size: 12px; }.trace-actions { gap: 4px; }
.trace-body { display: flex; flex: 1 1 auto; flex-direction: column; min-height: 0; overflow: hidden; }.trace-error { display: flex; align-items: center; gap: 8px; margin: 10px 12px 0; padding: 9px; border: 1px solid #fecaca; border-radius: 8px; background: #fef2f2; color: #b91c1c; font-size: 12px; }
.run-strip { display: flex; gap: 8px; min-height: 76px; padding: 10px 12px; overflow-x: auto; border-bottom: 1px solid var(--border-light); }.run-item { display: grid; flex: 0 0 220px; gap: 6px; padding: 9px 10px; border: 1px solid var(--border-light); border-radius: var(--radius-sm); background: var(--surface-primary); color: var(--text-secondary); cursor: pointer; text-align: left; }.run-item.active { border-color: var(--accent-primary); background: var(--accent-soft); }.run-item-main { justify-content: space-between; gap: 8px; }.run-item-main strong { font-size: 12px; }.run-item-main em, .run-status { font-size: 10px; font-style: normal; }.run-item-meta { color: var(--text-tertiary); font-size: 11px; }
.status-running { color: #2563eb; }.status-waiting { color: #d97706; }.status-failed { color: #dc2626; }.status-completed, .status-succeeded { color: #16a34a; }
.run-summary { padding: 12px; border-bottom: 1px solid var(--border-light); background: var(--surface-primary); }.run-heading { justify-content: space-between; gap: 10px; margin-bottom: 10px; }.run-heading p { color: var(--text-primary); font-size: 14px; font-weight: 720; }.run-heading span { color: var(--text-tertiary); font-size: 11px; }.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; }.summary-cell { display: grid; grid-template-columns: auto 1fr; gap: 4px 7px; padding: 8px; border: 1px solid var(--border-light); border-radius: 8px; background: var(--surface-secondary); color: var(--text-tertiary); font-size: 11px; }.summary-cell strong { grid-column: 1 / -1; color: var(--text-primary); font-size: 15px; }.trace-incomplete { gap: 6px; margin-top: 8px; color: #b45309; font-size: 11px; }
.trace-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; padding: 10px 12px; border-bottom: 1px solid var(--border-light); }.trace-tabs button { display: inline-flex; align-items: center; justify-content: center; gap: 5px; min-height: 32px; padding: 0 6px; border: 1px solid var(--border-light); border-radius: var(--radius-sm); background: var(--surface-primary); color: var(--text-secondary); cursor: pointer; font-size: 11px; }.trace-tabs button.active { border-color: var(--accent-primary); background: var(--accent-soft); color: var(--accent-primary); }.trace-tabs strong { color: var(--text-tertiary); font-size: 10px; }
.trace-content { flex: 1 1 auto; min-height: 0; overflow: auto; background: var(--surface-secondary); }.execution-tab, .overview-tab, .trace-list { padding: 12px; }.execution-tab :deep(.execution-node) { background: var(--surface-primary); }.overview-tab dl, .trace-record dl { display: grid; grid-template-columns: 86px minmax(0, 1fr); gap: 7px 10px; margin: 0; font-size: 11px; }.overview-tab { background: var(--surface-primary); }.overview-tab dt, .trace-record dt { color: var(--text-tertiary); }.overview-tab dd, .trace-record dd { min-width: 0; margin: 0; overflow-wrap: anywhere; color: var(--text-secondary); }.trace-list { display: grid; gap: 10px; }.trace-record { padding: 11px; border: 1px solid var(--border-light); border-radius: 8px; background: var(--surface-primary); }.trace-record header { justify-content: space-between; gap: 8px; }.trace-record header div { gap: 7px; min-width: 0; }.trace-record header strong { overflow: hidden; color: var(--text-primary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.trace-record header > span { color: var(--text-tertiary); font-size: 10px; }.record-meta { flex-wrap: wrap; gap: 5px 10px; margin: 8px 0; color: var(--text-tertiary); font-size: 10px; }.trace-record p { margin: 7px 0; color: var(--text-secondary); font-size: 11px; line-height: 1.5; }.load-more { min-height: 34px; border: 1px solid var(--border-light); border-radius: 8px; background: var(--surface-primary); color: var(--text-secondary); cursor: pointer; }.trace-loading { flex: 1; }.trace-footer { display: flex; justify-content: space-between; gap: 10px; padding: 8px 12px; border-top: 1px solid var(--border-light); color: var(--text-tertiary); font-size: 10px; }.trace-footer span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.spinning { animation: trace-spin 1s linear infinite; }@keyframes trace-spin { to { transform: rotate(360deg); } }
@media (max-width: 720px) { .summary-grid, .trace-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }.run-item { flex-basis: 190px; } }
</style>
