<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import SessionDetailView from '@/components/SessionDetailView.vue'

const route = useRoute()

const sessionId = computed(() => String(route.params.id || ''))
const initialData = computed<{
  message?: string
  attachments?: string[]
  hasInitialMessage: boolean
}>(() => {
  const initParam = typeof route.query.init === 'string' ? route.query.init : ''
  if (!initParam) return { hasInitialMessage: false }

  try {
    const decoded = decodeURIComponent(atob(initParam))
    const parsed = JSON.parse(decoded) as { message?: string; attachments?: string[] }
    return {
      message: parsed.message,
      attachments: Array.isArray(parsed.attachments) ? parsed.attachments : [],
      hasInitialMessage: Boolean(parsed.message),
    }
  } catch (error) {
    console.error('Failed to parse init param:', error)
    return { hasInitialMessage: false }
  }
})
</script>

<template>
  <SessionDetailView
    :key="sessionId"
    :session-id="sessionId"
    :initial-message="initialData.message"
    :initial-attachments="initialData.attachments"
    :has-initial-message="initialData.hasInitialMessage"
  />
</template>
