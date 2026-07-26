<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'
import { ArchiveRestore, ExternalLink, Loader2, Search, Trash2 } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { useToast } from '@/composables/useToast'
import type { Session } from '@/lib/api/types'
import { formatRelativeDate } from '@/lib/utils'
import { useSessionsStore } from '@/stores/sessions'
import { useProjectsStore } from '@/stores/projects'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const router = useRouter()
const sessionsStore = useSessionsStore()
const projectsStore = useProjectsStore()
const toast = useToast()
const query = ref('')
const busyAction = ref<{ sessionId: string; action: 'restore' | 'delete' } | null>(
  null,
)
let previouslyFocusedElement: HTMLElement | null = null

const dialogOpen = computed({
  get: () => props.open,
  set: (value: boolean) => emit('update:open', value),
})
const normalizedQuery = computed(() => query.value.trim().toLocaleLowerCase())
const filteredSessions = computed(() => {
  if (!normalizedQuery.value) return sessionsStore.archivedSessions
  return sessionsStore.archivedSessions.filter((session) =>
    [session.title, session.latest_message]
      .filter(Boolean)
      .some((value) =>
        String(value).toLocaleLowerCase().includes(normalizedQuery.value),
      ),
  )
})

watch(
  () => props.open,
  (open) => {
    if (!open) return
    previouslyFocusedElement =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    query.value = ''
    void loadArchivedSessions()
  },
  { immediate: true },
)

async function loadArchivedSessions() {
  try {
    await sessionsStore.loadArchivedSessions()
  } catch {
    // Store exposes the actionable error state in the dialog.
  }
}

function restoreOpeningFocus() {
  previouslyFocusedElement?.focus()
  previouslyFocusedElement = null
}

function isBusy(session: Session, action?: 'restore' | 'delete') {
  return (
    busyAction.value?.sessionId === session.session_id &&
    (!action || busyAction.value.action === action)
  )
}

function projectName(session: Session): string {
  if (!session.project_id) return '未分组'
  return (
    projectsStore.projects.find((project) => project.id === session.project_id)
      ?.name ?? '未分组'
  )
}

function openSession(session: Session) {
  dialogOpen.value = false
  void router.push(`/sessions/${session.session_id}`)
}

function openSessionInNewTab(session: Session) {
  const href = router.resolve(`/sessions/${session.session_id}`).href
  window.open(href, '_blank', 'noopener,noreferrer')
}

async function restoreSession(session: Session) {
  if (busyAction.value) return
  busyAction.value = { sessionId: session.session_id, action: 'restore' }
  try {
    await sessionsStore.updateOrganization(session.session_id, { archived: false })
    toast.success(`已恢复任务「${session.title || '新任务'}」`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '恢复失败，请重试')
  } finally {
    busyAction.value = null
  }
}

async function permanentlyDeleteSession(session: Session) {
  if (busyAction.value) return
  try {
    await ElMessageBox.confirm(
      '永久删除后，该任务下的所有聊天记录、上传文件与生成文件都无法找回。',
      `要永久删除任务「${session.title || '新任务'}」吗？`,
      {
        confirmButtonText: '永久删除',
        cancelButtonText: '取消',
        type: 'warning',
        distinguishCancelAndClose: true,
      },
    )
  } catch {
    return
  }

  busyAction.value = { sessionId: session.session_id, action: 'delete' }
  try {
    const deleted = await sessionsStore.deleteSession(session.session_id)
    if (deleted) {
      toast.success(`已永久删除任务「${session.title || '新任务'}」`)
    } else {
      toast.error(`永久删除任务「${session.title || '新任务'}」失败，请重试`)
    }
  } finally {
    busyAction.value = null
  }
}
</script>

<template>
  <ElDialog
    v-model="dialogOpen"
    title="已归档任务"
    width="min(720px, calc(100vw - 24px))"
    append-to-body
    align-center
    destroy-on-close
    class="archived-sessions-dialog"
    @closed="restoreOpeningFocus"
  >
    <div class="archived-sessions-body">
      <label class="archived-sessions-search">
        <Search :size="16" aria-hidden="true" />
        <span class="sr-only">筛选已归档任务</span>
        <input
          v-model="query"
          type="search"
          placeholder="搜索标题或最近消息"
          autocomplete="off"
        />
      </label>

      <div
        v-if="sessionsStore.archivedLoading"
        class="archived-sessions-state"
        role="status"
      >
        <Loader2 :size="20" class="spin" />
        <span>正在加载已归档任务…</span>
      </div>

      <div
        v-else-if="sessionsStore.archivedError"
        class="archived-sessions-state"
        role="alert"
      >
        <p>{{ sessionsStore.archivedError }}</p>
        <button type="button" class="button small" @click="loadArchivedSessions">
          重试
        </button>
      </div>

      <div
        v-else-if="sessionsStore.archivedSessions.length === 0"
        class="archived-sessions-state"
        role="status"
      >
        <p>还没有已归档任务</p>
        <span>归档后的任务会保留在这里。</span>
      </div>

      <div
        v-else-if="filteredSessions.length === 0"
        class="archived-sessions-state"
        role="status"
      >
        <p>没有匹配的已归档任务</p>
        <span>请尝试搜索其他关键词。</span>
      </div>

      <div v-else class="archived-sessions-list" aria-live="polite">
        <article
          v-for="session in filteredSessions"
          :key="session.session_id"
          class="archived-session-row"
        >
          <button
            type="button"
            class="archived-session-main"
            :aria-label="`打开已归档任务：${session.title || '新任务'}`"
            @click="openSession(session)"
          >
            <span class="archived-session-title">{{ session.title || '新任务' }}</span>
            <span class="archived-session-message">
              {{ session.latest_message || '暂无消息' }}
            </span>
            <span class="archived-session-project">
              {{ projectName(session) }}
            </span>
            <span class="archived-session-date">
              归档于 {{ formatRelativeDate(session.archived_at) }}
            </span>
          </button>

          <div class="archived-session-actions">
            <button
              type="button"
              class="icon-button subtle tiny"
              :aria-label="`在新标签页打开：${session.title || '新任务'}`"
              title="在新标签页打开"
              :disabled="Boolean(busyAction)"
              @click="openSessionInNewTab(session)"
            >
              <ExternalLink :size="15" />
            </button>
            <button
              type="button"
              class="icon-button subtle tiny"
              :aria-label="`恢复任务：${session.title || '新任务'}`"
              title="恢复"
              :disabled="Boolean(busyAction)"
              @click="restoreSession(session)"
            >
              <Loader2 v-if="isBusy(session, 'restore')" :size="15" class="spin" />
              <ArchiveRestore v-else :size="15" />
            </button>
            <button
              type="button"
              class="icon-button subtle tiny danger"
              :aria-label="`永久删除任务：${session.title || '新任务'}`"
              title="永久删除"
              :disabled="Boolean(busyAction)"
              @click="permanentlyDeleteSession(session)"
            >
              <Loader2 v-if="isBusy(session, 'delete')" :size="15" class="spin" />
              <Trash2 v-else :size="15" />
            </button>
          </div>
        </article>
      </div>
    </div>
  </ElDialog>
</template>
