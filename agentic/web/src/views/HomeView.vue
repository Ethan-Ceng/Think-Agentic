<script setup lang="ts">
import { computed, ref } from 'vue'
import { Bot, Folder, Sparkles, X } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import ChatHeader from '@/components/ChatHeader.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import SuggestedQuestions from '@/components/SuggestedQuestions.vue'
import { useToast } from '@/composables/useToast'
import { sessionApi } from '@/lib/api/session'
import type { ComposerAttachmentMetadata } from '@/lib/composer-attachments'
import type { SendMessageInput } from '@/types/skill'
import { encodeInitialSessionMessage } from '@/lib/session-init'
import { useAuthStore } from '@/stores/auth'
import { useProjectsStore } from '@/stores/projects'

const router = useRouter()
const route = useRoute()
const toast = useToast()
const auth = useAuthStore()
const projectsStore = useProjectsStore()
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
const targetProjectId = computed(() =>
  typeof route.query.project === 'string' && route.query.project.trim()
    ? route.query.project.trim()
    : null,
)
const targetProject = computed(() =>
  projectsStore.projects.find((project) => project.id === targetProjectId.value),
)
const projectTargetUnavailable = computed(
  () =>
    Boolean(targetProjectId.value) &&
    !projectsStore.loading &&
    !targetProject.value,
)

function handleQuestionClick(question: string) {
  chatInputRef.value?.setInputText(question)
}

function clearProjectTarget() {
  const query = { ...route.query }
  delete query.project
  void router.replace({ path: '/', query })
}

async function handleSend(input: SendMessageInput, _files: ComposerAttachmentMetadata[]) {
  if (sending.value) return
  sending.value = true

  try {
    const session = await sessionApi.createSession(
      targetProjectId.value
        ? { project_id: targetProjectId.value }
        : undefined,
    )
    const encoded = encodeInitialSessionMessage(input)
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
        <div
          v-if="targetProjectId"
          class="home-project-target"
          :class="{ invalid: projectTargetUnavailable }"
          role="status"
        >
          <Folder :size="15" aria-hidden="true" />
          <span v-if="projectsStore.loading">正在确认目标项目…</span>
          <span v-else-if="targetProject">
            将创建在「{{ targetProject.name }}」
          </span>
          <span v-else>目标项目不可用，发送时将由服务端重新确认</span>
          <button
            type="button"
            data-testid="clear-project-target"
            aria-label="清除目标项目"
            @click="clearProjectTarget"
          >
            <X :size="14" />
          </button>
        </div>
        <ChatInput ref="chatInputRef" :disabled="sending" :on-send="handleSend" />
        <SuggestedQuestions @select="handleQuestionClick" />
      </section>
    </main>
  </div>
</template>
