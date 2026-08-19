import { describe, expect, it } from 'vitest'
import type { ExecutionNode } from '@/lib/api/types'
import { executionMetricsFromNodes, mergeExecutionNodes } from './run-execution'

describe('mergeExecutionNodes', () => {
  it('keeps lifecycle metadata while applying the newest node status', () => {
    const started = node({
      cursor: 4,
      phase: 'plan',
      status: 'running',
      started_at: '2026-08-19T12:00:00Z',
      metrics: { message_count: 3, tool_schema_count: 2 },
    })
    const completed = node({
      cursor: 5,
      status: 'succeeded',
      started_at: null,
      finished_at: '2026-08-19T12:00:01Z',
      latency_ms: 1000,
      metrics: { total_tokens: 42 },
    })

    expect(mergeExecutionNodes([started], [completed])).toEqual([
      expect.objectContaining({
        status: 'succeeded',
        phase: 'plan',
        started_at: '2026-08-19T12:00:00Z',
        finished_at: '2026-08-19T12:00:01Z',
        latency_ms: 1000,
        metrics: { message_count: 3, tool_schema_count: 2, total_tokens: 42 },
      }),
    ])
  })

  it('ignores stale node updates', () => {
    const current = node({ cursor: 5, status: 'succeeded' })
    const stale = node({ cursor: 4, status: 'running' })

    expect(mergeExecutionNodes([current], [stale])).toEqual([current])
  })

  it('keeps a stable ordinal when later snapshots omit it', () => {
    const current = node({ cursor: 2, kind: 'step', ordinal: 0 })
    const incoming = node({ cursor: 3, kind: 'step' })

    expect(mergeExecutionNodes([current], [incoming])[0].ordinal).toBe(0)
  })

  it('derives complete token totals from merged model nodes', () => {
    const first = node({
      node_id: 'model:1',
      status: 'succeeded',
      metrics: { prompt_tokens: 20, completion_tokens: 5, total_tokens: 25, ttft_ms: 30 },
    })
    const second = node({
      node_id: 'model:2',
      status: 'succeeded',
      metrics: { prompt_tokens: 40, completion_tokens: 8, total_tokens: 48, ttft_ms: 12 },
    })

    expect(executionMetricsFromNodes([first, second])).toMatchObject({
      prompt_tokens: 60,
      completion_tokens: 13,
      total_tokens: 73,
      ttft_ms: 12,
      model_count: 2,
    })
  })

  it('does not truncate totals when a run has more than one model page', () => {
    const models = Array.from({ length: 150 }, (_, index) => node({
      node_id: `model:${index}`,
      status: 'succeeded',
      metrics: { prompt_tokens: 10, completion_tokens: 2, total_tokens: 12 },
    }))

    expect(executionMetricsFromNodes(models)).toMatchObject({
      prompt_tokens: 1500,
      completion_tokens: 300,
      total_tokens: 1800,
      model_count: 150,
    })
  })
})

function node(overrides: Partial<ExecutionNode>): ExecutionNode {
  return {
    node_id: 'model:1',
    parent_node_id: 'run:1',
    kind: 'model',
    phase: 'execute',
    status: 'running',
    title: '调用模型',
    summary: '',
    cursor: 1,
    metrics: {},
    ...overrides,
  }
}
