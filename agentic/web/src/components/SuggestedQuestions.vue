<script setup lang="ts">
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
      {{ question }}
    </button>
  </div>
</template>
