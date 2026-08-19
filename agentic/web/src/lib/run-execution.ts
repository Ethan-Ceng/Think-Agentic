import type { ExecutionMetrics, ExecutionNode } from '@/lib/api/types'

export function mergeExecutionNodes(
  currentNodes: ExecutionNode[],
  incomingNodes: ExecutionNode[],
): ExecutionNode[] {
  const nodes = new Map(currentNodes.map((node) => [node.node_id, node]))
  for (const incoming of incomingNodes) {
    const current = nodes.get(incoming.node_id)
    if (!current || incoming.cursor >= current.cursor) {
      nodes.set(incoming.node_id, mergeExecutionNode(current, incoming))
    }
  }
  return [...nodes.values()].sort(
    (left, right) => left.cursor - right.cursor || left.node_id.localeCompare(right.node_id),
  )
}

function mergeExecutionNode(
  current: ExecutionNode | undefined,
  incoming: ExecutionNode,
): ExecutionNode {
  if (!current) return incoming
  const incomingMetrics = Object.fromEntries(
    Object.entries(incoming.metrics).filter(([, value]) => value != null),
  ) as ExecutionNode['metrics']
  return {
    ...current,
    ...incoming,
    parent_node_id: incoming.parent_node_id || current.parent_node_id,
    phase: current.phase,
    summary: incoming.summary || current.summary,
    ordinal: incoming.ordinal ?? current.ordinal,
    started_at: current.started_at || incoming.started_at,
    finished_at: incoming.finished_at || current.finished_at,
    latency_ms: incoming.latency_ms ?? current.latency_ms,
    metrics: { ...current.metrics, ...incomingMetrics },
    detail_kind: incoming.detail_kind || current.detail_kind,
    detail_id: incoming.detail_id || current.detail_id,
  }
}

export function executionMetricsFromNodes(nodes: ExecutionNode[]): ExecutionMetrics {
  const stepNodes = nodes.filter((node) => node.kind === 'step')
  const toolNodes = nodes.filter((node) => node.kind === 'tool')
  const modelNodes = nodes.filter((node) => node.kind === 'model')
  const promptTokens = sumMetric(modelNodes, 'prompt_tokens')
  const completionTokens = sumMetric(modelNodes, 'completion_tokens')
  const totalTokens = sumMetric(modelNodes, 'total_tokens')
  const ttftValues = modelNodes
    .map((node) => node.metrics.ttft_ms)
    .filter((value): value is number => value != null)

  return {
    ...(promptTokens == null ? {} : { prompt_tokens: promptTokens }),
    ...(completionTokens == null ? {} : { completion_tokens: completionTokens }),
    ...(totalTokens == null ? {} : { total_tokens: totalTokens }),
    ...(ttftValues.length ? { ttft_ms: Math.min(...ttftValues) } : {}),
    step_count: stepNodes.length,
    completed_steps: stepNodes.filter((node) => node.status === 'succeeded').length,
    tool_count: toolNodes.length,
    model_count: modelNodes.length,
    replan_count: Math.max(...nodes.map((node) => node.metrics.replan_count || 0), 0),
  }
}

function sumMetric(
  nodes: ExecutionNode[],
  field: 'prompt_tokens' | 'completion_tokens' | 'total_tokens',
): number | undefined {
  const values = nodes
    .map((node) => node.metrics[field])
    .filter((value): value is number => value != null)
  return values.length ? values.reduce((sum, value) => sum + value, 0) : undefined
}
