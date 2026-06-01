<script setup lang="ts">
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'
import { useRoute, useRouter } from 'vue-router'
import { useSidebar } from '@/composables/useSidebar'
import { useToast } from '@/composables/useToast'
import type { Session } from '@/lib/api/types'
import { useSessionsStore } from '@/stores/sessions'
import SessionListItem from '@/components/SessionListItem.vue'

const route = useRoute()
const router = useRouter()
const sessionsStore = useSessionsStore()
const sidebar = useSidebar()
const toast = useToast()

const activeId = computed(() => String(route.params.id ?? ''))

function handleSessionClick(sessionId: string) {
  void router.push(`/sessions/${sessionId}`)
  if (window.innerWidth <= 900) {
    sidebar.close()
  }
}

async function requestDelete(session: Session) {
  const title = session.title || '新任务'

  try {
    await ElMessageBox.confirm(
      '删除任务信息后，该任务下的所有聊天记录、上传文件与生成文件都将无法找回。',
      '要删除任务信息吗？',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        distinguishCancelAndClose: true,
      },
    )
  } catch {
    return
  }

  try {
    const success = await sessionsStore.deleteSession(session.session_id)
    if (success) {
      toast.success(`已删除任务「${title}」`)
      if (activeId.value === session.session_id) {
        void router.push('/')
      }
    } else {
      toast.error(`删除任务「${title}」失败，请重试`)
    }
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '删除失败，请重试')
  }
}
</script>

<template>
  <div v-if="sessionsStore.loading" class="session-skeleton-list">
    <div v-for="i in 3" :key="i" class="session-skeleton">
      <span />
      <div>
        <b />
        <b />
      </div>
    </div>
  </div>

  <div v-else-if="sessionsStore.error" class="empty-state">
    <p>加载失败</p>
    <button type="button" class="link-button" @click="sessionsStore.refresh">重试</button>
  </div>

  <div v-else-if="sessionsStore.sessions.length === 0" class="empty-state">
    暂无任务
  </div>

  <div v-else class="session-list">
    <SessionListItem
      v-for="session in sessionsStore.sessions"
      :key="session.session_id"
      :session="session"
      :active="session.session_id === activeId"
      @open="handleSessionClick"
      @delete="requestDelete"
    />
  </div>
</template>
