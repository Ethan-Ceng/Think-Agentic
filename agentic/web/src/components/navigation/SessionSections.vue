<script setup lang="ts">
import ProjectSections from '@/components/navigation/ProjectSections.vue'

withDefaults(defineProps<{
  query?: string
}>(), {
  query: '',
})
</script>

<template>
  <section class="session-sections" aria-label="任务历史">
    <ProjectSections :query="query" />
  </section>
</template>
