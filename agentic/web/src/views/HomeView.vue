<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import ChatHeader from '@/components/ChatHeader.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import SuggestedQuestions from '@/components/SuggestedQuestions.vue'
import { useToast } from '@/composables/useToast'
import { sessionApi } from '@/lib/api/session'
import type { FileInfo } from '@/lib/api/types'

const router = useRouter()
const toast = useToast()
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null)
const sending = ref(false)

function handleQuestionClick(question: string) {
  chatInputRef.value?.setInputText(question)
}

async function handleSend(message: string, files: FileInfo[]) {
  if (sending.value) return
  sending.value = true

  try {
    const session = await sessionApi.createSession()
    const attachments = files.map((file) => file.id)
    const payload = JSON.stringify({ message, attachments })
    const encoded = btoa(encodeURIComponent(payload))
    await router.push(`/sessions/${session.session_id}?init=${encoded}`)
  } catch (error) {
    const messageText = error instanceof Error ? error.message : '创建会话失败'
    toast.error(messageText)
    sending.value = false
    throw error
  }
}
</script>

<template>
  <div class="home-page">
    <ChatHeader />

    <main class="home-main">
      <section class="home-composer">
        <div class="home-greeting">
          <p>您好，慕学者</p>
          <p>我能为您做什么？</p>
        </div>
        <ChatInput ref="chatInputRef" :disabled="sending" :on-send="handleSend" />
        <SuggestedQuestions @select="handleQuestionClick" />
      </section>
    </main>
  </div>
</template>
