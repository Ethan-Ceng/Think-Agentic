<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'
import { useRoute, useRouter } from 'vue-router'
import { useSidebar } from '@/composables/useSidebar'
import { useToast } from '@/composables/useToast'
import type { Session } from '@/lib/api/types'
import type { UpdateSessionOrganizationParams } from '@/lib/api/types'
import { useSessionsStore } from '@/stores/sessions'
import ArchivedSessionsDialog from '@/components/ArchivedSessionsDialog.vue'
import SessionListItem from '@/components/SessionListItem.vue'

const route = useRoute()
const router = useRouter()
const sessionsStore = useSessionsStore()
const sidebar = useSidebar()
const toast = useToast()
const busyAction = ref<{ sessionId: string; action: string } | null>(null)
const archivedDialogOpen = ref(false)

const props = withDefaults(defineProps<{
  query?: string
}>(), {
  query: '',
})

const activeId = computed(() => String(route.params.id ?? ''))
const normalizedQuery = computed(() => props.query.trim().toLocaleLowerCase())
const filteredSessions = computed(() => {
  if (!normalizedQuery.value) return sessionsStore.sessions
  return sessionsStore.sessions.filter((session) =>
    [session.title, session.latest_message]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase().includes(normalizedQuery.value)),
  )
})

const groupedSessions = computed(() => {
  const pinned = filteredSessions.value.filter((session) => session.is_pinned)
  const regular = filteredSessions.value.filter((session) => !session.is_pinned)
  const groups = new Map<string, Session[]>()
  for (const session of regular) {
    const label = groupLabel(session.latest_message_at)
    groups.set(label, [...(groups.get(label) || []), session])
  }
  return [
    ...(pinned.length ? [{ label: '已置顶', sessions: pinned }] : []),
    ...Array.from(groups, ([label, sessions]) => ({ label, sessions })),
  ]
})

function groupLabel(value: string | null | undefined) {
  if (!value) return '更早'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '更早'
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const diff = Math.floor((today - target) / 86_400_000)
  if (diff <= 0) return '今天'
  if (diff === 1) return '昨天'
  if (diff < 7) return '过去 7 天'
  if (diff < 30) return '过去 30 天'
  return '更早'
}

function handleSessionClick(sessionId: string) {
  void router.push(`/sessions/${sessionId}`)
  if (window.innerWidth <= 900) {
    sidebar.close()
  }
}

function isBusy(session: Session): boolean {
  return busyAction.value?.sessionId === session.session_id
}

async function updateSession(
  session: Session,
  action: string,
  params: UpdateSessionOrganizationParams,
): Promise<Session | null> {
  if (busyAction.value) return null
  busyAction.value = { sessionId: session.session_id, action }
  try {
    return await sessionsStore.updateOrganization(session.session_id, params)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : `${action}失败，请重试`)
    return null
  } finally {
    busyAction.value = null
  }
}

async function renameSession(session: Session, title: string) {
  const updated = await updateSession(session, '重命名', { title })
  if (updated) toast.success(`已重命名为「${updated.title}」`)
}

async function togglePin(session: Session) {
  const updated = await updateSession(session, '置顶', {
    pinned: !session.is_pinned,
  })
  if (updated) toast.success(updated.is_pinned ? '已置顶任务' : '已取消置顶')
}

async function archiveSession(session: Session) {
  const updated = await updateSession(session, '归档', { archived: true })
  if (!updated) return
  toast.success(`已归档任务「${session.title || '新任务'}」`)
  if (activeId.value === session.session_id) {
    void router.push('/')
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
  <div class="session-list-shell">
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

    <div v-else-if="filteredSessions.length === 0" class="empty-state sidebar-empty-state">
      <p>{{ normalizedQuery ? '没有匹配的任务' : '还没有任务' }}</p>
      <span>{{ normalizedQuery ? '试试搜索其他关键词' : '创建任务后会显示在这里' }}</span>
    </div>

    <div v-else class="session-list" aria-live="polite">
      <section v-for="group in groupedSessions" :key="group.label" class="session-group">
        <h3>{{ group.label }}</h3>
        <SessionListItem
          v-for="session in group.sessions"
          :key="session.session_id"
          :session="session"
          :active="session.session_id === activeId"
          :busy="isBusy(session)"
          @open="handleSessionClick"
          @rename="renameSession"
          @toggle-pin="togglePin"
          @archive="archiveSession"
          @delete="requestDelete"
        />
      </section>
    </div>

    <button
      type="button"
      class="archived-sessions-entry"
      @click="archivedDialogOpen = true"
    >
      查看已归档任务
    </button>
  </div>

  <ArchivedSessionsDialog v-model:open="archivedDialogOpen" />
</template>
