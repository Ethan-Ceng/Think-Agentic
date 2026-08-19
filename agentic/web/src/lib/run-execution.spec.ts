import { describe, expect, it } from 'vitest'
import type { ExecutionNode } from '@/lib/api/types'
import { mergeExecutionNodes } from './run-execution'

describe('mergeExecutionNodes', () => {
  it('keeps lifecycle metadata while applying the newest node status', () => {
    const started = node({
      cursor: 4,
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
