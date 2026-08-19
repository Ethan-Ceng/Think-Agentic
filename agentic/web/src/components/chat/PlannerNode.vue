<script setup lang="ts">
import { computed } from 'vue'
import { ListChecks } from 'lucide-vue-next'
import type { ExecutionNode } from '@/lib/api/types'

const props = defineProps<{
  node: ExecutionNode
  density?: 'chat' | 'diagnostic'
}>()

const progress = computed(() => {
  const completed = props.node.metrics.completed_steps ?? 0
  const total = props.node.metrics.step_count ?? 0
  return total > 0 ? `${completed}/${total}` : ''
})
</script>

<template>
  <div class="execution-node execution-node-plan" :class="`status-${node.status}`">
    <span class="execution-node-icon"><ListChecks :size="15" /></span>
    <div class="execution-node-copy">
      <div class="execution-node-title-row">
        <strong>{{ node.title }}</strong>
        <span v-if="progress" class="execution-node-progress">{{ progress }}</span>
      </div>
      <p v-if="density === 'diagnostic' && node.summary">{{ node.summary }}</p>
      <small v-if="node.metrics.replan_count">计划已调整 {{ node.metrics.replan_count }} 次</small>
    </div>
  </div>
</template>
