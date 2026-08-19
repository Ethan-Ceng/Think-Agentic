import type { ExecutionNode } from '@/lib/api/types'

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
    summary: incoming.summary || current.summary,
    started_at: current.started_at || incoming.started_at,
    finished_at: incoming.finished_at || current.finished_at,
    latency_ms: incoming.latency_ms ?? current.latency_ms,
    metrics: { ...current.metrics, ...incomingMetrics },
    detail_kind: incoming.detail_kind || current.detail_kind,
    detail_id: incoming.detail_id || current.detail_id,
  }
}
