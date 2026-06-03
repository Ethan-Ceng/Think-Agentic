<script setup lang="ts">
const props = defineProps<{
  visible: boolean
  title: string
  data: unknown
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()
</script>

<template>
  <el-drawer
    :model-value="props.visible"
    :title="props.title"
    size="680px"
    @update:model-value="emit('update:visible', $event)"
  >
    <pre class="max-h-full overflow-auto whitespace-pre-wrap rounded-md bg-slate-950 p-4 text-xs leading-5 text-slate-100">{{ JSON.stringify(props.data, null, 2) }}</pre>
  </el-drawer>
</template>
