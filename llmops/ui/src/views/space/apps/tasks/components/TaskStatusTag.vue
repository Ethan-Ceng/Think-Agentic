<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: string
}>()

const statusMeta = computed(() => {
  const value = props.status || 'created'
  const map: Record<string, { label: string; type: 'success' | 'warning' | 'danger' | 'info' | 'primary' }> = {
    created: { label: '已创建', type: 'info' },
    running: { label: '运行中', type: 'primary' },
    waiting: { label: '待处理', type: 'warning' },
    waiting_user: { label: '待补充', type: 'warning' },
    waiting_approval: { label: '待审批', type: 'warning' },
    succeeded: { label: '成功', type: 'success' },
    failed: { label: '失败', type: 'danger' },
    cancelled: { label: '已取消', type: 'info' },
  }
  return map[value] || { label: value, type: 'info' }
})
</script>

<template>
  <el-tag size="small" :type="statusMeta.type">{{ statusMeta.label }}</el-tag>
</template>
