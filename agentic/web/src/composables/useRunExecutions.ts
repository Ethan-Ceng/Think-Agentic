import { computed, ref, unref, watch, type Ref } from 'vue'
import { runsApi } from '@/lib/api/runs'
import { mergeExecutionNodes } from '@/lib/run-execution'
import type {
  AgentRun,
  ExecutionNode,
  ExecutionNodeStatus,
  ExecutionUpdateEvent,
  RunExecutionOverview,
  RunExecutionView,
  SSEEventData,
} from '@/lib/api/types'

export type RunExecutionState = {
  runId: string
  inputEventId: string | null
  run: RunExecutionOverview
  nodes: ExecutionNode[]
  cursor: number | null
  expanded: boolean
  hydrated: boolean
  loading: boolean
  error: string
  traceComplete: boolean
}

export function useRunExecutions(
  sessionId: Ref<string | null> | string | null,
  events: Ref<SSEEventData[]>,
  sessionStatus?: Ref<string | undefined>,
) {
  const states = ref<Record<string, RunExecutionState>>({})
  const loadingRuns = ref(false)
  let requestVersion = 0
  const seenUpdates = new Set<string>()

  const byInputEventId = computed<Record<string, RunExecutionState>>(() => {
    const mapped: Record<string, RunExecutionState> = {}
    for (const state of Object.values(states.value)) {
      if (state.inputEventId) mapped[state.inputEventId] = state
    }
    return mapped
  })

  function replaceState(state: RunExecutionState): void {
    states.value = { ...states.value, [state.runId]: state }
  }

  function statusFromUpdate(nodes: ExecutionNode[]): ExecutionNodeStatus {
    if (nodes.some((node) => node.kind === 'error' && node.status === 'failed')) return 'failed'
    if (nodes.some((node) => node.kind === 'completion' && node.status === 'failed')) return 'failed'
    if (nodes.some((node) => node.kind === 'interaction' && node.status === 'waiting')) {
      return 'waiting'
    }
    if (nodes.some((node) => node.kind === 'completion' && node.status === 'succeeded')) {
      return 'succeeded'
    }
    return 'running'
  }

  function modeFromNodes(nodes: ExecutionNode[]): 'direct' | 'react' | 'plan' | null {
    const strategy = [...nodes].reverse().find((node) => node.kind === 'strategy')
    if (!strategy) return nodes.some((node) => node.kind === 'plan') ? 'plan' : null
    if (strategy.title.includes('直接')) return 'direct'
    if (strategy.title.includes('计划')) return 'plan'
    return 'react'
  }

  function syntheticOverview(update: ExecutionUpdateEvent): RunExecutionOverview {
    const status = statusFromUpdate(update.nodes)
    const mode = modeFromNodes(update.nodes)
    const stepNodes = update.nodes.filter((node) => node.kind === 'step')
    const planNode = [...update.nodes].reverse().find((node) => node.kind === 'plan')
    return {
      run_id: update.run_id,
      session_id: String(unref(sessionId) || ''),
      input_event_id: update.input_event_id,
      status,
      mode,
      summary: update.nodes.at(-1)?.summary || '',
      started_at: update.nodes.find((node) => node.kind === 'run')?.started_at,
      finished_at: status === 'succeeded' || status === 'failed' ? update.nodes.at(-1)?.finished_at : null,
      latency_ms: null,
      metrics: {
        step_count: stepNodes.length,
        completed_steps: stepNodes.filter((node) => node.status === 'succeeded').length,
        tool_count: update.nodes.filter((node) => node.kind === 'tool').length,
        model_count: update.nodes.filter((node) => node.kind === 'model').length,
        replan_count: planNode?.metrics.replan_count ?? 0,
      },
    }
  }

  function applyExecutionUpdate(update: ExecutionUpdateEvent): void {
    const key = `${update.run_id}:${update.next_cursor ?? 0}`
    if (seenUpdates.has(key)) return
    seenUpdates.add(key)
    const current = states.value[update.run_id]
    const nodes = mergeExecutionNodes(current?.nodes || [], update.nodes)
    const patchOverview = syntheticOverview({ ...update, nodes })
    replaceState({
      runId: update.run_id,
      inputEventId: update.input_event_id || current?.inputEventId || null,
      run: {
        ...(current?.run || patchOverview),
        ...patchOverview,
        mode: patchOverview.mode || current?.run.mode || null,
        started_at: patchOverview.started_at || current?.run.started_at,
        finished_at: patchOverview.finished_at || current?.run.finished_at,
      },
      nodes,
      cursor: Math.max(current?.cursor || 0, update.next_cursor || 0) || null,
      expanded: current?.expanded ?? false,
      hydrated: current?.hydrated ?? false,
      loading: false,
      error: '',
      traceComplete: (current?.traceComplete ?? true) && update.trace_complete,
    })
  }

  function overviewFromRun(run: AgentRun): RunExecutionOverview {
    const statusMap: Record<AgentRun['status'], ExecutionNodeStatus> = {
      pending: 'pending',
      running: 'running',
      waiting: 'waiting',
      completed: 'succeeded',
      failed: 'failed',
    }
    return {
      run_id: run.id,
      session_id: run.session_id,
      input_event_id: run.input_event_id,
      status: statusMap[run.status],
      mode: null,
      summary: '',
      started_at: run.started_at,
      finished_at: run.finished_at,
      latency_ms: durationMs(run.started_at, run.finished_at),
      metrics: {},
    }
  }

  function mergeView(view: RunExecutionView, hydrated: boolean): void {
    const current = states.value[view.run.run_id]
    replaceState({
      runId: view.run.run_id,
      inputEventId: view.run.input_event_id || current?.inputEventId || null,
      run: {
        ...(current?.run || view.run),
        ...view.run,
        mode: view.run.mode || current?.run.mode || null,
      },
      nodes: mergeExecutionNodes(current?.nodes || [], view.nodes),
      cursor: Math.max(current?.cursor || 0, view.next_cursor || 0) || null,
      expanded: current?.expanded ?? false,
      hydrated: hydrated || current?.hydrated || false,
      loading: false,
      error: '',
      traceComplete: (current?.traceComplete ?? true) && view.trace_complete,
    })
  }

  async function loadExecution(runId: string, fromStart = false): Promise<void> {
    const initial = states.value[runId]
    if (!initial || initial.loading) return
    replaceState({ ...initial, loading: true, error: '' })
    try {
      let after: number | undefined = fromStart ? undefined : initial.cursor ?? undefined
      let hasMore = true
      while (hasMore) {
        const view = await runsApi.getExecution(runId, {
          after,
          limit: 200,
          detail: 'summary',
        })
        mergeView(view, fromStart)
        hasMore = view.has_more
        if (!hasMore || view.next_cursor == null || view.next_cursor === after) break
        after = view.next_cursor
      }
      const current = states.value[runId]
      if (current) replaceState({ ...current, loading: false, hydrated: current.hydrated || fromStart })
    } catch (error) {
      const current = states.value[runId]
      if (current) {
        replaceState({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : '执行详情加载失败',
          traceComplete: false,
        })
      }
    }
  }

  async function refreshRuns(syncTerminal = false): Promise<void> {
    const currentSessionId = unref(sessionId)
    if (!currentSessionId) return
    const version = ++requestVersion
    loadingRuns.value = true
    try {
      const data = await runsApi.listRuns({ session_id: currentSessionId, limit: 200 })
      if (version !== requestVersion || currentSessionId !== unref(sessionId)) return
      for (const run of data.runs || []) {
        const current = states.value[run.id]
        const runOverview = overviewFromRun(run)
        replaceState({
          runId: run.id,
          inputEventId: run.input_event_id || current?.inputEventId || null,
          run: {
            ...(current?.run || runOverview),
            ...runOverview,
            mode: current?.run.mode || null,
            summary: current?.run.summary || '',
            metrics: current?.run.metrics || {},
          },
          nodes: current?.nodes || [],
          cursor: current?.cursor || null,
          expanded: current?.expanded ?? false,
          hydrated: current?.hydrated ?? false,
          loading: current?.loading ?? false,
          error: current?.error || '',
          traceComplete: current?.traceComplete ?? true,
        })
        if (syncTerminal && current?.cursor != null) void loadExecution(run.id, false)
      }
    } catch {
      // Run cards are progressive enhancement; Session chat remains usable.
    } finally {
      if (version === requestVersion) loadingRuns.value = false
    }
  }

  function toggle(runId: string): void {
    const state = states.value[runId]
    if (!state) return
    const expanded = !state.expanded
    replaceState({ ...state, expanded })
    if (expanded && !state.hydrated) void loadExecution(runId, true)
  }

  watch(
    () => unref(sessionId),
    () => {
      requestVersion += 1
      states.value = {}
      seenUpdates.clear()
      void refreshRuns()
    },
    { immediate: true },
  )

  watch(
    events,
    (items) => {
      for (const event of items) {
        if (event.type === 'execution_update') applyExecutionUpdate(event.data)
      }
    },
    { deep: false, immediate: true },
  )

  if (sessionStatus) {
    watch(sessionStatus, (status, previous) => {
      if (status && status !== previous && status !== 'running') void refreshRuns(true)
    })
  }

  return {
    states,
    byInputEventId,
    loadingRuns,
    refreshRuns,
    loadExecution,
    toggle,
    applyExecutionUpdate,
  }
}

function durationMs(start?: string | null, end?: string | null): number | null {
  if (!start || !end) return null
  const value = new Date(end).getTime() - new Date(start).getTime()
  return Number.isFinite(value) ? Math.max(0, value) : null
}
