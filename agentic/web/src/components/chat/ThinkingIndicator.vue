<script setup lang="ts">
import { Loader2, Sparkles } from 'lucide-vue-next'

withDefaults(defineProps<{
  title?: string
  description?: string
}>(), {
  title: 'MoocManus 正在思考',
  description: '正在分析上下文并准备下一步',
})
</script>

<template>
  <div class="thinking-indicator">
    <span class="thinking-indicator-icon">
      <Loader2 :size="16" class="spin" />
    </span>
    <span class="thinking-indicator-copy">
      <strong>
        <Sparkles :size="13" />
        {{ title }}
      </strong>
      <span>{{ description }}</span>
    </span>
    <span class="thinking-dots" aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  </div>
</template>
