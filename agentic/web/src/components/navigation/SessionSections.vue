<script setup lang="ts">
import SessionList from '@/components/SessionList.vue'

withDefaults(defineProps<{
  query?: string
}>(), {
  query: '',
})
</script>

<template>
  <section class="session-sections" aria-label="任务历史">
    <SessionList :query="query" />
  </section>
</template>
