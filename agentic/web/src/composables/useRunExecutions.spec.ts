import { effectScope, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { runsApi } from '@/lib/api/runs'
import type { RunExecutionView, SSEEventData } from '@/lib/api/types'
import { useRunExecutions } from './useRunExecutions'

vi.mock('@/lib/api/runs', () => ({
  runsApi: {
    listRuns: vi.fn(),
    getExecution: vi.fn(),
  },
}))

const baseView: RunExecutionView = {
  schema_version: 1,
  run: {
    run_id: 'run-1',
    session_id: 'session-1',
    input_event_id: 'input-1',
    status: 'running',
    mode: 'plan',
    summary: '执行中',
    metrics: { step_count: 1, completed_steps: 0 },
  },
  nodes: [
    {
      node_id: 'plan:1',
      parent_node_id: 'run:run-1',
      kind: 'plan',
      phase: 'plan',
      status: 'running',
      title: '任务计划',
      summary: '执行中',
      cursor: 2,
      metrics: { step_count: 1, completed_steps: 0 },
    },
  ],
  next_cursor: 2,
  has_more: false,
  trace_complete: true,
  warnings: [],
}

describe('useRunExecutions', () => {
  beforeEach(() => {
    vi.mocked(runsApi.listRuns).mockResolvedValue({ runs: [] })
    vi.mocked(runsApi.getExecution).mockResolvedValue(baseView)
  })

  it('binds transient updates to the input event and merges nodes by cursor', async () => {
    const events = ref<SSEEventData[]>([])
    const scope = effectScope()
    const result = scope.run(() => useRunExecutions(ref('session-1'), events))!
    await nextTick()

    events.value.push(executionUpdate(2, 'running'))
    await nextTick()
    expect(result.byInputEventId.value['input-1'].nodes[0].cursor).toBe(2)
    expect(result.states.value['run-1'].expanded).toBe(true)

    result.toggle('run-1')
    expect(result.states.value['run-1'].expanded).toBe(false)

    events.value.push(executionUpdate(3, 'succeeded'))
    await nextTick()
    expect(
      result.byInputEventId.value['input-1'].nodes.find((node) => node.node_id === 'step:1')?.cursor,
    ).toBe(3)
    expect(result.states.value['run-1'].expanded).toBe(false)
    scope.stop()
  })

  it('loads the full execution view only on first expansion', async () => {
    const events = ref<SSEEventData[]>([completedUpdate()])
    const scope = effectScope()
    const result = scope.run(() => useRunExecutions(ref('session-1'), events))!
    await nextTick()

    result.toggle('run-1')
    await vi.waitFor(() => expect(runsApi.getExecution).toHaveBeenCalledTimes(1))
    expect(runsApi.getExecution).toHaveBeenCalledWith('run-1', {
      after: undefined,
      limit: 200,
      detail: 'summary',
    })
    expect(result.states.value['run-1'].hydrated).toBe(true)
    scope.stop()
  })

  it('treats a failed completion node as a failed run', async () => {
    const events = ref<SSEEventData[]>([])
    const scope = effectScope()
    const result = scope.run(() => useRunExecutions(ref('session-1'), events))!
    await nextTick()

    result.applyExecutionUpdate({
      run_id: 'run-1',
      input_event_id: 'input-1',
      schema_version: 1,
      nodes: [
        {
          node_id: 'completion:run-1',
          parent_node_id: 'run:run-1',
          kind: 'completion',
          phase: 'finalize',
          status: 'failed',
          title: '本次执行未完成',
          summary: '本次执行未完成',
          cursor: 4,
          metrics: {},
        },
      ],
      next_cursor: 4,
      trace_complete: true,
    })

    expect(result.states.value['run-1'].run.status).toBe('failed')
    scope.stop()
  })
})

function executionUpdate(cursor: number, status: 'running' | 'succeeded'): SSEEventData {
  return {
    type: 'execution_update',
    data: {
      run_id: 'run-1',
      input_event_id: 'input-1',
      schema_version: 1,
      nodes: [
        {
          node_id: 'step:1',
          parent_node_id: 'plan:1',
          kind: 'step',
          phase: 'execute',
          status,
          title: '实现页面',
          summary: status === 'succeeded' ? '已完成' : '执行中',
          cursor,
          metrics: {},
        },
      ],
      next_cursor: cursor,
      trace_complete: true,
    },
  }
}

function completedUpdate(): SSEEventData {
  return {
    type: 'execution_update',
    data: {
      run_id: 'run-1',
      input_event_id: 'input-1',
      schema_version: 1,
      nodes: [{
        node_id: 'completion:run-1',
        parent_node_id: 'run:run-1',
        kind: 'completion',
        phase: 'finalize',
        status: 'succeeded',
        title: '任务已完成',
        summary: '任务已完成',
        cursor: 2,
        metrics: {},
      }],
      next_cursor: 2,
      trace_complete: true,
    },
  }
}
