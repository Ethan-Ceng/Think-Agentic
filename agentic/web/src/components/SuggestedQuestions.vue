<script setup lang="ts">
import { ArrowUpRight } from 'lucide-vue-next'
import { suggestedQuestions } from '@/config/app.config'

const emit = defineEmits<{
  select: [question: string]
}>()
</script>

<template>
  <div class="suggested-questions">
    <button
      v-for="question in suggestedQuestions"
      :key="question"
      type="button"
      class="button secondary suggestion-button"
      @click="emit('select', question)"
    >
      <span>{{ question }}</span>
      <ArrowUpRight :size="15" />
    </button>
  </div>
</template>
