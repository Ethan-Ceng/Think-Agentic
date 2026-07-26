import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { sessionApi } from '@/lib/api/session'
import type { Session, UpdateSessionOrganizationParams } from '@/lib/api/types'

const RETRY_CONFIG = {
  maxRetries: 10,
  baseDelay: 1000,
  maxDelay: 30000,
} as const

function normalizeSessions(raw: unknown): Session[] {
  if (Array.isArray(raw)) return raw as Session[]
  if (raw && typeof raw === 'object' && 'sessions' in raw) {
    const sessions = (raw as { sessions?: unknown }).sessions
    return Array.isArray(sessions) ? (sessions as Session[]) : []
  }
  return []
}

export const useSessionsStore = defineStore('sessions', () => {
  const sessions = ref<Session[]>([])
  const archivedSessions = ref<Session[]>([])
  const loading = ref(true)
  const archivedLoading = ref(false)
  const error = ref<string | null>(null)
  const archivedError = ref<string | null>(null)

  let cleanup: (() => void) | null = null
  let retryTimer: ReturnType<typeof window.setTimeout> | null = null
  let initialFetched = false
  let sseReceived = false
  let mounted = false

  const sortedSessions = computed(() =>
    [...sessions.value].sort((left, right) => {
      if (left.is_pinned !== right.is_pinned) return left.is_pinned ? -1 : 1
      const leftTime = left.latest_message_at
        ? new Date(left.latest_message_at).getTime()
        : 0
      const rightTime = right.latest_message_at
        ? new Date(right.latest_message_at).getTime()
        : 0
      if (leftTime !== rightTime) return rightTime - leftTime
      return 0
    }),
  )

  async function refresh(): Promise<void> {
    try {
      loading.value = true
      error.value = null
      const raw = await sessionApi.getSessions()
      sessions.value = normalizeSessions(raw)
    } catch (err) {
      console.error('[Sessions] REST 获取失败:', err)
      error.value = err instanceof Error ? err.message : '获取会话列表失败'
    } finally {
      loading.value = false
    }
  }

  async function fetchInitial(): Promise<void> {
    if (initialFetched) return
    initialFetched = true

    try {
      const raw = await sessionApi.getSessions()
      if (!sseReceived) {
        sessions.value = normalizeSessions(raw)
      }
      error.value = null
    } catch (err) {
      console.error('[Sessions] 初始获取失败:', err)
      error.value = err instanceof Error ? err.message : '获取会话列表失败'
    } finally {
      loading.value = false
    }
  }

  function clearRetryTimer(): void {
    if (retryTimer) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  function connectStream(): void {
    let retryCount = 0

    const connect = () => {
      if (!mounted) return

      if (cleanup) {
        cleanup()
        cleanup = null
      }

      cleanup = sessionApi.streamSessions(
        (newSessions) => {
          retryCount = 0
          sseReceived = true
          sessions.value = newSessions
          loading.value = false
          error.value = null
        },
        (err) => {
          if (!mounted) return
          console.warn('[Sessions] SSE 断开:', err.message)

          if (retryCount >= RETRY_CONFIG.maxRetries) {
            return
          }

          const delay = Math.min(
            RETRY_CONFIG.baseDelay * Math.pow(2, retryCount),
            RETRY_CONFIG.maxDelay,
          )
          retryCount++
          retryTimer = window.setTimeout(connect, delay)
        },
      )
    }

    connect()
  }

  function start(): void {
    if (mounted) return
    mounted = true
    void fetchInitial()
    connectStream()
  }

  function stop(): void {
    mounted = false
    clearRetryTimer()
    if (cleanup) {
      cleanup()
      cleanup = null
    }
  }

  function clear(): void {
    sessions.value = []
    archivedSessions.value = []
    error.value = null
    archivedError.value = null
    loading.value = false
    archivedLoading.value = false
    initialFetched = false
    sseReceived = false
  }

  async function deleteSession(sessionId: string): Promise<boolean> {
    try {
      await sessionApi.deleteSession(sessionId)
      sessions.value = sessions.value.filter((session) => session.session_id !== sessionId)
      archivedSessions.value = archivedSessions.value.filter(
        (session) => session.session_id !== sessionId,
      )
      return true
    } catch {
      return false
    }
  }

  async function loadArchivedSessions(): Promise<void> {
    archivedLoading.value = true
    archivedError.value = null
    try {
      const raw = await sessionApi.getSessions('archived')
      archivedSessions.value = normalizeSessions(raw)
    } catch (err) {
      console.error('[Sessions] 获取归档会话失败:', err)
      archivedError.value = err instanceof Error ? err.message : '获取归档会话失败'
      throw err
    } finally {
      archivedLoading.value = false
    }
  }

  async function updateOrganization(
    sessionId: string,
    params: UpdateSessionOrganizationParams,
  ): Promise<Session> {
    const updated = await sessionApi.updateOrganization(sessionId, params)
    if (updated.archived_at) {
      sessions.value = sessions.value.filter(
        (session) => session.session_id !== sessionId,
      )
      const archivedIndex = archivedSessions.value.findIndex(
        (session) => session.session_id === sessionId,
      )
      if (archivedIndex >= 0) {
        archivedSessions.value[archivedIndex] = updated
      } else {
        archivedSessions.value = [updated, ...archivedSessions.value]
      }
    } else {
      archivedSessions.value = archivedSessions.value.filter(
        (session) => session.session_id !== sessionId,
      )
      const index = sessions.value.findIndex(
        (session) => session.session_id === sessionId,
      )
      if (index >= 0) {
        sessions.value[index] = updated
      } else {
        sessions.value = [updated, ...sessions.value]
      }
    }
    return updated
  }

  function unassignProject(projectId: string): void {
    const unassign = (items: Session[]) =>
      items.map((session) =>
        session.project_id === projectId
          ? { ...session, project_id: null }
          : session,
      )

    sessions.value = unassign(sessions.value)
    archivedSessions.value = unassign(archivedSessions.value)
  }

  return {
    sessions: sortedSessions,
    archivedSessions,
    loading,
    archivedLoading,
    error,
    archivedError,
    refresh,
    loadArchivedSessions,
    start,
    stop,
    clear,
    deleteSession,
    updateOrganization,
    unassignProject,
  }
})
