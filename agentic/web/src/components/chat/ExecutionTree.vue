<script setup lang="ts">
import { computed, type Component } from 'vue'
import {
  AlertCircle,
  Bot,
  Check,
  Circle,
  Clock3,
  LoaderCircle,
  Route,
  Sparkles,
  Wrench,
} from 'lucide-vue-next'
import PlannerNode from '@/components/chat/PlannerNode.vue'
import type { ExecutionNode, ExecutionNodeKind, ExecutionNodeStatus } from '@/lib/api/types'

const props = withDefaults(defineProps<{
  nodes: ExecutionNode[]
  density?: 'chat' | 'diagnostic'
}>(), {
  density: 'chat',
})

const emit = defineEmits<{
  toolClick: [node: ExecutionNode]
}>()

type FlatNode = { node: ExecutionNode; depth: number; stepNumber?: number }

const visibleNodes = computed<FlatNode[]>(() => {
  const source = props.nodes.filter((node) => (
    node.kind !== 'run' &&
    (props.density === 'diagnostic' || (node.kind !== 'model' && node.kind !== 'skill'))
  ))
  const sourceIds = new Set(source.map((node) => node.node_id))
  const children = new Map<string, ExecutionNode[]>()
  const roots: ExecutionNode[] = []

  for (const node of source) {
    if (!node.parent_node_id || !sourceIds.has(node.parent_node_id)) {
      roots.push(node)
      continue
    }
    const list = children.get(node.parent_node_id) || []
    list.push(node)
    children.set(node.parent_node_id, list)
  }

  const sort = (items: ExecutionNode[]) =>
    [...items].sort((a, b) => a.cursor - b.cursor || a.node_id.localeCompare(b.node_id))
  const flattened: FlatNode[] = []
  const seen = new Set<string>()
  let stepNumber = 0
  const visit = (node: ExecutionNode, depth: number) => {
    if (seen.has(node.node_id)) return
    seen.add(node.node_id)
    flattened.push({
      node,
      depth,
      stepNumber: node.kind === 'step' ? ++stepNumber : undefined,
    })
    for (const child of sort(children.get(node.node_id) || [])) visit(child, depth + 1)
  }
  for (const root of sort(roots)) visit(root, 0)
  for (const node of sort(source)) visit(node, 0)
  return flattened
})

const kindIcons: Record<ExecutionNodeKind, Component> = {
  run: Route,
  strategy: Route,
  plan: Route,
  step: Circle,
  model: Bot,
  tool: Wrench,
  skill: Sparkles,
  interaction: Clock3,
  error: AlertCircle,
  completion: Check,
}

function statusIcon(status: ExecutionNodeStatus): Component {
  if (status === 'running') return LoaderCircle
  if (status === 'waiting') return Clock3
  if (status === 'failed') return AlertCircle
  if (status === 'succeeded') return Check
  return Circle
}

function formatDuration(value?: number | null): string {
  if (value == null) return ''
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)} s`
}

function statusLabel(status: ExecutionNodeStatus): string {
  return {
    pending: '等待中',
    running: '进行中',
    waiting: '等待输入',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已停止',
  }[status]
}
</script>

<template>
  <div class="execution-tree" :class="`density-${density}`">
    <div
      v-for="item in visibleNodes"
      :key="item.node.node_id"
      class="execution-tree-row"
      :class="[`kind-${item.node.kind}`, `status-${item.node.status}`]"
      :style="{ '--execution-depth': item.depth }"
    >
      <PlannerNode v-if="item.node.kind === 'plan'" :node="item.node" />
      <component
        :is="item.node.kind === 'tool' ? 'button' : 'div'"
        v-else
        class="execution-node"
        :class="{ 'execution-node-action': item.node.kind === 'tool' }"
        :type="item.node.kind === 'tool' ? 'button' : undefined"
        @click="item.node.kind === 'tool' && emit('toolClick', item.node)"
      >
        <span class="execution-node-icon">
          <component
            :is="item.node.status === 'running' || item.node.status === 'waiting'
              ? statusIcon(item.node.status)
              : kindIcons[item.node.kind]"
            :size="15"
            :class="{ spin: item.node.status === 'running' }"
          />
        </span>
        <div class="execution-node-copy">
          <div class="execution-node-title-row">
            <strong>
              {{ item.stepNumber ? `${item.stepNumber}. ${item.node.title}` : item.node.title }}
            </strong>
            <span v-if="item.node.kind === 'step'" class="execution-node-state">
              {{ statusLabel(item.node.status) }}
            </span>
            <span v-if="formatDuration(item.node.latency_ms)">{{ formatDuration(item.node.latency_ms) }}</span>
          </div>
          <p v-if="item.node.summary && item.node.summary !== item.node.title">{{ item.node.summary }}</p>
          <small v-if="density === 'diagnostic'">
            {{ item.node.phase }} · #{{ item.node.cursor }} · {{ item.node.node_id }}
          </small>
          <small v-if="item.node.failure?.debug_id">参考编号：{{ item.node.failure.debug_id }}</small>
        </div>
      </component>
    </div>
  </div>
</template>
