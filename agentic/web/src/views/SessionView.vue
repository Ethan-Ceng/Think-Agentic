<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import SessionDetailView from '@/components/SessionDetailView.vue'
import type { SkillRef } from '@/types/skill'
import { consumeQueuedRunIntent, decodeInitialSessionMessage } from '@/lib/session-init'

const route = useRoute()

const sessionId = computed(() => String(route.params.id || ''))
const runQueued = ref(false)
const initialData = computed<{
  message?: string
  attachments?: string[]
  skills?: SkillRef[]
  hasInitialMessage: boolean
}>(() => {
  const initParam = typeof route.query.init === 'string' ? route.query.init : ''
  if (!initParam) return { hasInitialMessage: false }

  try {
    return decodeInitialSessionMessage(initParam)
  } catch (error) {
    console.error('Failed to parse init param:', error)
    return { hasInitialMessage: false }
  }
})

watch(
  () => [sessionId.value, route.query.runQueued] as const,
  ([currentSessionId, token]) => {
    runQueued.value =
      typeof token === 'string' &&
      consumeQueuedRunIntent(token, currentSessionId)
  },
  { immediate: true },
)
</script>

<template>
  <SessionDetailView
    :key="sessionId"
    :session-id="sessionId"
    :initial-message="initialData.message"
    :initial-attachments="initialData.attachments"
    :initial-skills="initialData.skills"
    :has-initial-message="initialData.hasInitialMessage"
    :run-queued="runQueued"
  />
</template>
