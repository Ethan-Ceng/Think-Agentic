import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { sessionApi } from '@/lib/api/session'
import type { Session } from '@/lib/api/types'

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
  const loading = ref(true)
  const error = ref<string | null>(null)

  let cleanup: (() => void) | null = null
  let retryTimer: ReturnType<typeof window.setTimeout> | null = null
  let initialFetched = false
  let sseReceived = false
  let mounted = false

  const sortedSessions = computed(() => sessions.value)

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
    error.value = null
    loading.value = false
    initialFetched = false
    sseReceived = false
  }

  async function deleteSession(sessionId: string): Promise<boolean> {
    try {
      await sessionApi.deleteSession(sessionId)
      sessions.value = sessions.value.filter((session) => session.session_id !== sessionId)
      return true
    } catch {
      return false
    }
  }

  return {
    sessions: sortedSessions,
    loading,
    error,
    refresh,
    start,
    stop,
    clear,
    deleteSession,
  }
})
