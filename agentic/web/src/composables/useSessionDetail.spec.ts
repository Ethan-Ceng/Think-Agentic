import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionDetail, type UseSessionDetailResult } from './useSessionDetail'

const mocks = vi.hoisted(() => ({
  chat: vi.fn(),
  getSessionDetail: vi.fn(),
  getSessionFiles: vi.fn(),
}))

vi.mock('@/lib/api/session', () => ({
  sessionApi: {
    chat: mocks.chat,
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
    wrapper.unmount()
  })

  it('preserves waiting when the stream closes for a pending interaction', async () => {
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
    wrapper.unmount()
  })
})
