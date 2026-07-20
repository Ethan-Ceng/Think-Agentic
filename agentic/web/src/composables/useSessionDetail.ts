import { computed, onBeforeUnmount, ref, unref, watch, type Ref } from 'vue'
import { sessionApi } from '@/lib/api/session'
import { normalizeEvent, normalizeEvents } from '@/lib/session-events'
import type {
  ResolveInteractionParams,
  ResumeMode,
  SSEEventData,
  SessionDetail,
  SessionFile,
} from '@/lib/api/types'
import type { SendMessageInput } from '@/types/skill'

export type UseSessionDetailResult = {
  session: Ref<SessionDetail | null>
  files: Ref<SessionFile[]>
  events: Ref<SSEEventData[]>
  loading: Ref<boolean>
  error: Ref<Error | null>
  refresh: () => Promise<void>
  refreshFiles: () => Promise<void>
  sendMessage: (input: SendMessageInput) => Promise<void>
  resumeTask: (mode: ResumeMode) => Promise<void>
  resolveInteraction: (actionId: string, params: ResolveInteractionParams) => Promise<void>
  streaming: Ref<boolean>
}

function normalizeFileList(raw: unknown): SessionFile[] {
  if (Array.isArray(raw)) return raw as SessionFile[]
  if (raw && typeof raw === 'object' && 'files' in raw) {
    const files = (raw as { files?: unknown }).files
    return Array.isArray(files) ? (files as SessionFile[]) : []
  }
  if (raw && typeof raw === 'object' && 'data' in raw) {
    const data = (raw as { data?: unknown }).data
    return Array.isArray(data) ? (data as SessionFile[]) : []
  }
  return []
}

export function useSessionDetail(
  sessionId: Ref<string | null> | string | null,
  initialSkipEmptyStream: Ref<boolean> | boolean = false,
): UseSessionDetailResult {
  const id = computed(() => unref(sessionId))
  const session = ref<SessionDetail | null>(null)
  const files = ref<SessionFile[]>([])
  const events = ref<SSEEventData[]>([])
  const loading = ref(true)
  const error = ref<Error | null>(null)
  const streaming = ref(false)
  const skipEmptyStream = ref(Boolean(unref(initialSkipEmptyStream)))

  let emptyStreamCleanup: (() => void) | null = null
  let messageStreamCleanup: (() => void) | null = null
  let emptyReconnectTimer: number | null = null
  let emptyReconnectAttempt = 0
  let isSendMessage = false
  let lastEventId: string | null = null
  let seenEventIds = new Set<string>()

  function finishRunStream(): void {
    streaming.value = false
    isSendMessage = false
    if (session.value && session.value.status !== 'waiting') {
      session.value = { ...session.value, status: 'completed' }
    }
  }

  function appendEvent(ev: SSEEventData): void {
    emptyReconnectAttempt = 0
    if (emptyReconnectTimer !== null) {
      window.clearTimeout(emptyReconnectTimer)
      emptyReconnectTimer = null
    }
    let evToAppend = ev
    if (
      ev.data &&
      typeof ev.data === 'object' &&
      ('event' in ev.data || 'type' in ev.data) &&
      'data' in ev.data
    ) {
      const normalized = normalizeEvent(ev.data as { event?: string; type?: string; data?: unknown })
      if (normalized) evToAppend = normalized
    }

    const eventId = (evToAppend.data as { event_id?: string })?.event_id
    if (eventId) {
      if (seenEventIds.has(eventId)) return
      seenEventIds.add(eventId)
      lastEventId = eventId
    }

    events.value.push(evToAppend)

    if (
      evToAppend.type === 'title' &&
      evToAppend.data &&
      typeof (evToAppend.data as { title?: string }).title === 'string'
    ) {
      session.value = session.value
        ? { ...session.value, title: (evToAppend.data as { title: string }).title }
        : null
    }

    if (evToAppend.type === 'step') {
      const stepData = evToAppend.data as { status?: string }
      if (stepData.status === 'running') {
        session.value = session.value ? { ...session.value, status: 'running' } : null
      }
      if (stepData.status === 'waiting') {
        session.value = session.value ? { ...session.value, status: 'waiting' } : null
        streaming.value = false
      }
    }

    if (evToAppend.type === 'tool') {
      const toolData = evToAppend.data as { function?: string; status?: string }
      if (toolData.function === 'message_ask_user' && toolData.status === 'calling') {
        session.value = session.value ? { ...session.value, status: 'waiting' } : null
        streaming.value = false
      }
    }

    if (evToAppend.type === 'interaction') {
      const interaction = evToAppend.data as { status?: string }
      session.value = session.value
        ? { ...session.value, status: interaction.status === 'pending' ? 'waiting' : 'running' }
        : null
      if (interaction.status === 'pending') streaming.value = false
    }

    if (evToAppend.type === 'wait') {
      session.value = session.value ? { ...session.value, status: 'waiting' } : null
      streaming.value = false
    }

    if (evToAppend.type === 'done' || evToAppend.type === 'error') {
      session.value = session.value ? { ...session.value, status: 'completed' } : null
      streaming.value = false
      isSendMessage = false
    }
  }

  function stopEmptyStream(): void {
    if (emptyReconnectTimer !== null) {
      window.clearTimeout(emptyReconnectTimer)
      emptyReconnectTimer = null
    }
    if (emptyStreamCleanup) {
      emptyStreamCleanup()
      emptyStreamCleanup = null
    }
  }

  function startEmptyStream(): void {
    const currentId = id.value
    if (!currentId || session.value?.status === 'completed') return

    stopEmptyStream()
    emptyStreamCleanup = sessionApi.chat(
      currentId,
      { event_id: lastEventId || undefined },
      (ev) => appendEvent(ev),
      (err) => {
        if (err.name === 'AbortError') return
        if (err.message === 'SSE_STREAM_END') {
          emptyStreamCleanup = null
          void refresh().finally(() => scheduleEmptyStreamReconnect())
          return
        }
        console.warn('Session detail empty stream error:', err)
        emptyStreamCleanup = null
        scheduleEmptyStreamReconnect()
      },
    )
  }

  function scheduleEmptyStreamReconnect(): void {
    if (
      emptyReconnectTimer !== null ||
      isSendMessage ||
      !id.value ||
      session.value?.status === 'completed'
    ) return

    const delay = Math.min(1000 * 2 ** emptyReconnectAttempt, 15_000)
    emptyReconnectAttempt += 1
    emptyReconnectTimer = window.setTimeout(() => {
      emptyReconnectTimer = null
      if (!emptyStreamCleanup && !isSendMessage) startEmptyStream()
    }, delay)
  }

  async function refresh(): Promise<void> {
    const currentId = id.value
    if (!currentId) return

    error.value = null
    try {
      const [detail, fileListRaw] = await Promise.all([
        sessionApi.getSessionDetail(currentId),
        sessionApi.getSessionFiles(currentId),
      ])
      session.value = detail
      files.value = normalizeFileList(fileListRaw)

      const rawEvents = (detail as { events?: unknown }).events
      const normalized = normalizeEvents(rawEvents)
      seenEventIds = new Set(
        normalized
          .map((event) => (event.data as { event_id?: string })?.event_id)
          .filter((eventId): eventId is string => Boolean(eventId)),
      )
      events.value = normalized
      const lastEvId = (normalized[normalized.length - 1]?.data as { event_id?: string })?.event_id
      if (lastEvId) lastEventId = lastEvId
    } catch (e) {
      error.value = e instanceof Error ? e : new Error('加载失败')
    } finally {
      loading.value = false
    }
  }

  async function refreshFiles(): Promise<void> {
    const currentId = id.value
    if (!currentId) return
    try {
      const fileListRaw = await sessionApi.getSessionFiles(currentId)
      files.value = normalizeFileList(fileListRaw)
    } catch (e) {
      console.error('刷新文件列表失败:', e)
    }
  }

  async function sendMessage(input: SendMessageInput): Promise<void> {
    const currentId = id.value
    if (!currentId) return

    stopEmptyStream()
    if (messageStreamCleanup) {
      messageStreamCleanup()
      messageStreamCleanup = null
    }

    skipEmptyStream.value = false
    isSendMessage = true
    streaming.value = true
    error.value = null
    session.value = session.value ? { ...session.value, status: 'running' } : null

    const onEvent = (ev: SSEEventData) => {
      appendEvent(ev)
      if (ev.type === 'done') {
        streaming.value = false
        isSendMessage = false
        if (messageStreamCleanup) {
          messageStreamCleanup()
          messageStreamCleanup = null
        }
        startEmptyStream()
      }
    }

    messageStreamCleanup = sessionApi.chat(
      currentId,
      { message: input.message, attachments: input.attachmentIds, skills: input.skills },
      onEvent,
      (err) => {
        if (err.name === 'AbortError') {
          streaming.value = false
          isSendMessage = false
          return
        }
        if (err.message === 'SSE_STREAM_END') {
          finishRunStream()
          if (messageStreamCleanup) {
            messageStreamCleanup()
            messageStreamCleanup = null
          }
          startEmptyStream()
          return
        }
        error.value = err instanceof Error ? err : new Error('流式响应异常')
        streaming.value = false
        isSendMessage = false
        session.value = session.value ? { ...session.value, status: 'completed' } : null
        if (messageStreamCleanup) {
          messageStreamCleanup()
          messageStreamCleanup = null
        }
        startEmptyStream()
      },
    )
  }

  async function resumeTask(mode: ResumeMode): Promise<void> {
    const currentId = id.value
    if (!currentId) return

    stopEmptyStream()
    if (messageStreamCleanup) {
      messageStreamCleanup()
      messageStreamCleanup = null
    }

    skipEmptyStream.value = false
    isSendMessage = true
    streaming.value = true
    error.value = null
    session.value = session.value ? { ...session.value, status: 'running' } : null

    messageStreamCleanup = sessionApi.resumeSession(
      currentId,
      { mode },
      (ev) => {
        appendEvent(ev)
        if (ev.type === 'done') {
          finishRunStream()
          messageStreamCleanup?.()
          messageStreamCleanup = null
        }
      },
      (err) => {
        if (err.name === 'AbortError') return
        messageStreamCleanup = null
        if (err.message === 'SSE_STREAM_END') {
          finishRunStream()
          return
        }
        finishRunStream()
        error.value = err
      },
    )
  }

  async function resolveInteraction(
    actionId: string,
    params: ResolveInteractionParams,
  ): Promise<void> {
    const currentId = id.value
    if (!currentId) return

    stopEmptyStream()
    messageStreamCleanup?.()
    messageStreamCleanup = null
    isSendMessage = true
    streaming.value = true
    error.value = null

    await new Promise<void>((resolve, reject) => {
      let settled = false
      const finish = (streamError?: Error) => {
        if (settled) return
        settled = true
        finishRunStream()
        messageStreamCleanup?.()
        messageStreamCleanup = null
        if (streamError) reject(streamError)
        else resolve()
      }

      messageStreamCleanup = sessionApi.resolveInteraction(
        currentId,
        actionId,
        params,
        (ev) => {
          appendEvent(ev)
          if (ev.type === 'done') finish()
        },
        (streamError) => {
          if (streamError.name === 'AbortError') return
          if (streamError.message === 'SSE_STREAM_END') {
            finish()
            return
          }
          error.value = streamError
          finish(streamError)
        },
      )
    })
  }

  watch(
    id,
    () => {
      stopEmptyStream()
      if (messageStreamCleanup) {
        messageStreamCleanup()
        messageStreamCleanup = null
      }
      session.value = null
      files.value = []
      events.value = []
      error.value = null
      lastEventId = null
      seenEventIds = new Set()
      emptyReconnectAttempt = 0
      isSendMessage = false
      streaming.value = false
      skipEmptyStream.value = Boolean(unref(initialSkipEmptyStream))

      if (!id.value) {
        loading.value = false
        return
      }

      loading.value = true
      void refresh()
    },
    { immediate: true },
  )

  watch(
    () => [id.value, session.value?.status, skipEmptyStream.value] as const,
    () => {
      if (!id.value || !session.value) return
      const completed = session.value.status === 'completed'
      if (!completed && !isSendMessage && !skipEmptyStream.value) {
        startEmptyStream()
      } else {
        stopEmptyStream()
      }
    },
  )

  onBeforeUnmount(() => {
    stopEmptyStream()
    if (messageStreamCleanup) {
      messageStreamCleanup()
      messageStreamCleanup = null
    }
  })

  return {
    session,
    files,
    events,
    loading,
    error,
    refresh,
    refreshFiles,
    sendMessage,
    resumeTask,
    resolveInteraction,
    streaming,
  }
}
