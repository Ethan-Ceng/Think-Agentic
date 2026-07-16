<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import SessionDetailView from '@/components/SessionDetailView.vue'
import type { SkillRef } from '@/types/skill'
import { decodeInitialSessionMessage } from '@/lib/session-init'

const route = useRoute()

const sessionId = computed(() => String(route.params.id || ''))
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
</script>

<template>
  <SessionDetailView
    :key="sessionId"
    :session-id="sessionId"
    :initial-message="initialData.message"
    :initial-attachments="initialData.attachments"
    :initial-skills="initialData.skills"
    :has-initial-message="initialData.hasInitialMessage"
  />
</template>
