import { createSSEStream, get, parseSSEStream, post } from './fetch'
import type {
  ChatParams,
  CreateSessionParams,
  ResumeSessionParams,
  SSEEventData,
  SSEEventHandler,
  Session,
  SessionDetail,
  SessionFile,
  SessionsData,
  ViewFileParams,
  ViewShellParams,
} from './types'
import type { SendMessageInput } from '@/types/skill'
import { encodeInitialSessionMessage } from '@/lib/session-init'

type SessionsStreamCallback = (sessions: Session[]) => void

export type SessionLaunch = {
  sessionId: string
  init: string
}

export const sessionApi = {
  getSessions: (): Promise<SessionsData> => {
    return get<SessionsData>('/sessions')
  },

  createSession: (params?: CreateSessionParams): Promise<Session> => {
    return post<Session>('/sessions', params || {})
  },

  createSessionWithInitialMessage: async (
    input: SendMessageInput,
  ): Promise<SessionLaunch> => {
    const session = await post<Session>('/sessions', {})
    return {
      sessionId: session.session_id,
      init: encodeInitialSessionMessage(input),
    }
  },

  streamSessions: (
    onSessions: SessionsStreamCallback,
    onError?: (error: Error) => void,
  ): (() => void) => {
    const controller = new AbortController()

    const startStream = async () => {
      try {
        const stream = await createSSEStream('/sessions/stream', {}, {
          signal: controller.signal,
        })

        await parseSSEStream(
          stream,
          (messageEvent) => {
            if (controller.signal.aborted) return

            const data =
              typeof messageEvent.data === 'string'
                ? JSON.parse(messageEvent.data)
                : messageEvent.data

            if (data?.sessions && Array.isArray(data.sessions)) {
              onSessions(data.sessions as Session[])
            }
          },
          (error) => {
            if (!controller.signal.aborted) {
              onError?.(error)
            }
          },
        )

        if (!controller.signal.aborted) {
          onError?.(new Error('SSE 流已结束'))
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          onError?.(error instanceof Error ? error : new Error('SSE 连接失败'))
        }
      }
    }

    void startStream()

    return () => {
      controller.abort()
    }
  },

  getSession: (sessionId: string): Promise<Session> => {
    return get<Session>(`/sessions/${sessionId}`)
  },

  getSessionDetail: (sessionId: string): Promise<SessionDetail> => {
    return get<SessionDetail>(`/sessions/${sessionId}`)
  },

  chat: (
    sessionId: string,
    params: ChatParams,
    onEvent: SSEEventHandler,
    onError?: (error: Error) => void,
  ): (() => void) => {
    const controller = new AbortController()

    const startStream = async () => {
      try {
        const stream = await createSSEStream(
          `/sessions/${sessionId}/chat`,
          params,
          {
            signal: controller.signal,
            timeout: 5 * 60 * 1000,
          },
        )

        await parseSSEStream(
          stream,
          (messageEvent) => {
            if (controller.signal.aborted) return

            const data =
              typeof messageEvent.data === 'string'
                ? JSON.parse(messageEvent.data)
                : messageEvent.data

            onEvent({
              type: messageEvent.type as SSEEventData['type'],
              data,
            } as SSEEventData)
          },
          (error) => {
            if (!controller.signal.aborted) {
              onError?.(error)
            }
          },
        )

        if (!controller.signal.aborted) {
          onError?.(new Error('SSE_STREAM_END'))
        }
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          return
        }
        if (!controller.signal.aborted) {
          onError?.(error instanceof Error ? error : new Error('启动聊天流失败'))
        }
      }
    }

    void startStream()

    return () => {
      controller.abort()
    }
  },

  resumeSession: (
    sessionId: string,
    params: ResumeSessionParams,
    onEvent: SSEEventHandler,
    onError?: (error: Error) => void,
  ): (() => void) => {
    const controller = new AbortController()

    const startStream = async () => {
      try {
        const stream = await createSSEStream(
          `/sessions/${sessionId}/resume`,
          params,
          {
            signal: controller.signal,
            timeout: 5 * 60 * 1000,
          },
        )

        await parseSSEStream(
          stream,
          (messageEvent) => {
            if (controller.signal.aborted) return
            const data =
              typeof messageEvent.data === 'string'
                ? JSON.parse(messageEvent.data)
                : messageEvent.data
            onEvent({
              type: messageEvent.type as SSEEventData['type'],
              data,
            } as SSEEventData)
          },
          (error) => {
            if (!controller.signal.aborted) onError?.(error)
          },
        )

        if (!controller.signal.aborted) onError?.(new Error('SSE_STREAM_END'))
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') return
        if (!controller.signal.aborted) {
          onError?.(error instanceof Error ? error : new Error('启动任务恢复流失败'))
        }
      }
    }

    void startStream()
    return () => controller.abort()
  },

  stopSession: (sessionId: string): Promise<void> => {
    return post<void>(`/sessions/${sessionId}/stop`, {})
  },

  deleteSession: (sessionId: string): Promise<void> => {
    return post<void>(`/sessions/${sessionId}/delete`, {})
  },

  clearUnreadMessageCount: (sessionId: string): Promise<void> => {
    return post<void>(`/sessions/${sessionId}/clear-unread-message-count`, {})
  },

  getSessionFiles: (sessionId: string): Promise<SessionFile[]> => {
    return get<SessionFile[]>(`/sessions/${sessionId}/files`)
  },

  viewFile: (
    sessionId: string,
    params: ViewFileParams,
  ): Promise<{ content: string; [key: string]: unknown }> => {
    return post<{ content: string; [key: string]: unknown }>(
      `/sessions/${sessionId}/file`,
      params,
    )
  },

  viewShell: (
    sessionId: string,
    params: ViewShellParams,
  ): Promise<{ output: string; [key: string]: unknown }> => {
    return post<{ output: string; [key: string]: unknown }>(
      `/sessions/${sessionId}/shell`,
      params,
    )
  },
}
