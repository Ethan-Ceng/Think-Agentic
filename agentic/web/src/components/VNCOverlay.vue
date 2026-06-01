<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Loader2, WifiOff, X } from 'lucide-vue-next'
import VNCViewer from '@/components/VNCViewer.vue'
import { API_BASE_URL } from '@/lib/api/fetch'
import type { VNCStatus } from '@/types/vnc'

const props = defineProps<{
  sessionId: string
}>()

const emit = defineEmits<{
  close: []
}>()

const status = ref<VNCStatus>('connecting')
const errorDetail = ref('')

const vncUrl = computed(() => {
  let host: string
  let pathname: string
  let isHttps: boolean

  try {
    const url = new URL(API_BASE_URL)
    host = url.host
    pathname = url.pathname
    isHttps = url.protocol === 'https:'
  } catch {
    host = window.location.host
    pathname = API_BASE_URL
    isHttps = window.location.protocol === 'https:'
  }

  const protocol = isHttps ? 'wss:' : 'ws:'
  return `${protocol}//${host}${pathname}/sessions/${props.sessionId}/vnc`
})

const hasError = computed(() => status.value === 'error' || status.value === 'disconnected')

function handleStatusChange(nextStatus: VNCStatus, detail?: string) {
  status.value = nextStatus
  if (nextStatus === 'error' || nextStatus === 'disconnected') {
    errorDetail.value = detail || '连接失败'
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  document.body.style.overflow = 'hidden'
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div class="vnc-overlay">
      <VNCViewer :url="vncUrl" :view-only="false" @status-change="handleStatusChange" />

      <div v-if="status === 'connecting'" class="vnc-status">
        <Loader2 :size="32" class="spin" />
        <span>正在连接沙箱环境...</span>
      </div>

      <div v-if="hasError" class="vnc-status">
        <section class="vnc-error-card">
          <WifiOff :size="40" />
          <strong>无法连接到沙箱</strong>
          <p>{{ errorDetail || '沙箱环境可能已关闭，请确认任务仍在运行中' }}</p>
          <button class="button secondary dark" type="button" @click="emit('close')">
            <X :size="14" />
            退出远程桌面
          </button>
        </section>
      </div>

      <button v-if="status === 'connected'" class="vnc-exit" type="button" @click="emit('close')">
        <X :size="14" />
        退出远程桌面
      </button>
    </div>
  </Teleport>
</template>
