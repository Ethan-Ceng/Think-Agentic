<script setup lang="ts">
import { computed, ref } from 'vue'
import { Bot, Sparkles } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import ChatHeader from '@/components/ChatHeader.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import SuggestedQuestions from '@/components/SuggestedQuestions.vue'
import { useToast } from '@/composables/useToast'
import { sessionApi } from '@/lib/api/session'
import type { FileInfo } from '@/lib/api/types'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const toast = useToast()
const auth = useAuthStore()
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null)
const sending = ref(false)
const displayName = computed(() => auth.user?.name?.trim() || auth.user?.email?.split('@')[0] || '朋友')
const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 11) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

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
        <div class="agent-identity">
          <span class="agent-identity-icon"><Bot :size="18" /></span>
          <span>通用 Agent</span>
          <span class="agent-ready"><i /> 已就绪</span>
        </div>
        <div class="home-greeting">
          <p>{{ greeting }}，{{ displayName }}</p>
          <h1>今天想完成什么？</h1>
          <p class="home-subtitle">
            <Sparkles :size="15" />
            我可以规划任务、使用工具，并将执行过程清晰地呈现给你。
          </p>
        </div>
        <ChatInput ref="chatInputRef" :disabled="sending" :on-send="handleSend" />
        <SuggestedQuestions @select="handleQuestionClick" />
      </section>
    </main>
  </div>
</template>
