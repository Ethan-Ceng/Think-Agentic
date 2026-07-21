import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionDetail, type UseSessionDetailResult } from './useSessionDetail'

const mocks = vi.hoisted(() => ({
  chat: vi.fn(),
  resumeSession: vi.fn(),
  resolveInteraction: vi.fn(),
  queueNextMessage: vi.fn(),
  cancelNextMessage: vi.fn(),
  runNextMessage: vi.fn(),
  getSessionDetail: vi.fn(),
  getSessionFiles: vi.fn(),
}))

vi.mock('@/lib/api/session', () => ({
  sessionApi: {
    chat: mocks.chat,
    resumeSession: mocks.resumeSession,
    resolveInteraction: mocks.resolveInteraction,
    queueNextMessage: mocks.queueNextMessage,
    cancelNextMessage: mocks.cancelNextMessage,
    runNextMessage: mocks.runNextMessage,
    getSessionDetail: mocks.getSessionDetail,
    getSessionFiles: mocks.getSessionFiles,
  },
}))

function mountComposable() {
  let detail!: UseSessionDetailResult
  const Host = defineComponent({
    setup() {
      detail = useSessionDetail(ref('session-1'))
      return () => h('div')
    },
  })
  const wrapper = mount(Host)
  return { detail, wrapper }
}

describe('useSessionDetail stream completion', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocks.getSessionDetail.mockResolvedValue({
      session_id: 'session-1',
      status: 'completed',
      events: [],
    })
    mocks.getSessionFiles.mockResolvedValue([])
  })

  it('returns the session to completed when a normal chat stream closes without done', async () => {
    mocks.chat.mockImplementation((_id, params, _onEvent, onError) => {
      if (params.message) queueMicrotask(() => onError(new Error('SSE_STREAM_END')))
      return vi.fn()
    })
    const { detail, wrapper } = mountComposable()
    await flushPromises()

    await detail.sendMessage({ message: 'hello', attachmentIds: [], skills: [] })
    await flushPromises()

    expect(detail.streaming.value).toBe(false)
    expect(detail.session.value?.status).toBe('completed')
    expect(mocks.getSessionDetail).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('preserves waiting when the stream closes for a pending interaction', async () => {
    mocks.getSessionDetail
      .mockResolvedValueOnce({ session_id: 'session-1', status: 'completed', events: [] })
      .mockResolvedValueOnce({ session_id: 'session-1', status: 'waiting', events: [] })
    mocks.chat.mockImplementation((_id, params, onEvent, onError) => {
      if (params.message) {
        queueMicrotask(() => {
          onEvent({ type: 'wait', data: {} })
          onError(new Error('SSE_STREAM_END'))
        })
      }
      return vi.fn()
    })
    const { detail, wrapper } = mountComposable()
    await flushPromises()

    await detail.sendMessage({ message: 'needs approval', attachmentIds: [], skills: [] })
    await flushPromises()

    expect(detail.streaming.value).toBe(false)
    expect(detail.session.value?.status).toBe('waiting')
    expect(mocks.getSessionDetail).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('reconnects the output stream when authoritative status is still running', async () => {
    mocks.getSessionDetail
      .mockResolvedValueOnce({ session_id: 'session-1', status: 'completed', events: [] })
      .mockResolvedValueOnce({ session_id: 'session-1', status: 'running', events: [] })
    mocks.chat.mockImplementation((_id, params, _onEvent, onError) => {
      if (params.message) queueMicrotask(() => onError(new Error('SSE_STREAM_END')))
      return vi.fn()
    })
    const { detail, wrapper } = mountComposable()
    await flushPromises()

    await detail.sendMessage({ message: 'keep running', attachmentIds: [], skills: [] })
    await flushPromises()

    expect(detail.session.value?.status).toBe('running')
    expect(mocks.getSessionDetail).toHaveBeenCalledTimes(2)
    expect(mocks.chat).toHaveBeenCalledTimes(2)
    expect(mocks.chat.mock.calls[1]?.[1]).toEqual({ event_id: undefined })
    wrapper.unmount()
  })

  it('reconciles session state when a resume stream closes', async () => {
    mocks.resumeSession.mockImplementation((_id, _params, _onEvent, onError) => {
      queueMicrotask(() => onError(new Error('SSE_STREAM_END')))
      return vi.fn()
    })
    const { detail, wrapper } = mountComposable()
    await flushPromises()

    await detail.resumeTask('continue')
    await flushPromises()

    expect(detail.session.value?.status).toBe('completed')
    expect(mocks.getSessionDetail).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('reconciles session state before resolving an interaction stream promise', async () => {
    mocks.resolveInteraction.mockImplementation((_id, _actionId, _params, _onEvent, onError) => {
      queueMicrotask(() => onError(new Error('SSE_STREAM_END')))
      return vi.fn()
    })
    const { detail, wrapper } = mountComposable()
    await flushPromises()

    await detail.resolveInteraction('action-1', { decision: 'approve' })
    await flushPromises()

    expect(detail.session.value?.status).toBe('completed')
    expect(mocks.getSessionDetail).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('ignores a terminal event delivered late by a replaced message stream', async () => {
    const streams: Array<{
      onEvent: (event: { type: 'done'; data: Record<string, never> }) => void
      cleanup: ReturnType<typeof vi.fn>
    }> = []
    mocks.chat.mockImplementation((_id, params, onEvent) => {
      const cleanup = vi.fn()
      if (params.message) streams.push({ onEvent, cleanup })
      return cleanup
    })
    const { detail, wrapper } = mountComposable()
    await flushPromises()

    await detail.sendMessage({ message: 'first', attachmentIds: [], skills: [] })
    await detail.sendMessage({ message: 'second', attachmentIds: [], skills: [] })
    streams[0].onEvent({ type: 'done', data: {} })
    await flushPromises()

    expect(streams[0].cleanup).toHaveBeenCalledOnce()
    expect(streams[1].cleanup).not.toHaveBeenCalled()
    expect(detail.session.value?.status).toBe('running')
    expect(detail.streaming.value).toBe(true)
    wrapper.unmount()
  })

  it('ignores an empty-stream refresh that finishes after a new send starts', async () => {
    let finishOldRefresh!: (value: { session_id: string; status: string; events: never[] }) => void
    let emptyStreamError!: (error: Error) => void
    const oldRefresh = new Promise<{ session_id: string; status: string; events: never[] }>(
      (resolve) => { finishOldRefresh = resolve },
    )
    mocks.getSessionDetail
      .mockResolvedValueOnce({ session_id: 'session-1', status: 'running', events: [] })
      .mockReturnValueOnce(oldRefresh)
    mocks.chat.mockImplementation((_id, params, _onEvent, onError) => {
      if (!params.message) emptyStreamError = onError
      return vi.fn()
    })
    const { detail, wrapper } = mountComposable()
    await flushPromises()

    emptyStreamError(new Error('SSE_STREAM_END'))
    await detail.sendMessage({ message: 'new run', attachmentIds: [], skills: [] })
    finishOldRefresh({ session_id: 'session-1', status: 'completed', events: [] })
    await flushPromises()

    expect(detail.session.value?.status).toBe('running')
    expect(detail.streaming.value).toBe(true)
    wrapper.unmount()
  })

  it('persists and cancels a next message without replacing the active stream', async () => {
    const queued = {
      id: 'next-1',
      message: 'follow up',
      attachment_ids: [],
      skills: [],
      state: 'queued',
      created_at: '2026-07-21T00:00:00',
    }
    mocks.getSessionDetail.mockResolvedValue({
      session_id: 'session-1',
      status: 'running',
      events: [],
      next_message: null,
    })
    mocks.chat.mockReturnValue(vi.fn())
    mocks.queueNextMessage.mockResolvedValue(queued)
    mocks.cancelNextMessage.mockResolvedValue(undefined)
    const { detail, wrapper } = mountComposable()
    await flushPromises()

    await detail.queueNextMessage({ message: 'follow up', attachmentIds: [], skills: [] })
    expect(detail.session.value?.next_message).toEqual(queued)
    expect(detail.streaming.value).toBe(false)

    await detail.cancelNextMessage()
    expect(detail.session.value?.next_message).toBeNull()
    wrapper.unmount()
  })

  it('runs a persisted next message through its own guarded SSE stream', async () => {
    mocks.getSessionDetail.mockResolvedValue({
      session_id: 'session-1',
      status: 'completed',
      events: [],
      next_message: {
        id: 'next-1',
        message: 'follow up',
        attachment_ids: [],
        skills: [],
        state: 'queued',
        created_at: '2026-07-21T00:00:00',
      },
    })
    mocks.runNextMessage.mockImplementation((_id, onEvent) => {
      queueMicrotask(() => onEvent({ type: 'done', data: {} }))
      return vi.fn()
    })
    const { detail, wrapper } = mountComposable()
    await flushPromises()

    await detail.runNextMessage()
    await flushPromises()

    expect(mocks.runNextMessage).toHaveBeenCalledOnce()
    expect(detail.session.value?.status).toBe('completed')
    expect(detail.session.value?.next_message).toBeNull()
    expect(detail.streaming.value).toBe(false)
    wrapper.unmount()
  })
})
