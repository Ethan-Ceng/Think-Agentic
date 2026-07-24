import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SessionDetailView from './SessionDetailView.vue'

const mocks = vi.hoisted(() => ({
  detail: undefined as unknown,
  toastInfo: vi.fn(),
}))

vi.mock('@/composables/useSessionDetail', () => ({
  useSessionDetail: () => mocks.detail,
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: mocks.toastInfo,
  }),
}))

const ChatInputStub = defineComponent({
  name: 'ChatInput',
  props: { disabled: Boolean },
  template: '<div class="stub-chat-input" :data-disabled="disabled" />',
})

const ArchivedDialogStub = defineComponent({
  name: 'ArchivedSessionsDialog',
  props: { open: Boolean },
  emits: ['update:open'],
  template: '<div class="stub-archived-dialog" :data-open="open" />',
})

describe('SessionDetailView archived state', () => {
  beforeEach(() => {
    mocks.toastInfo.mockReset()
    mocks.detail = {
      session: ref({
        session_id: 'session-1',
        title: 'Archived task',
        status: 'completed',
        archived_at: '2026-07-24T10:00:00',
        events: [],
        next_message: null,
        source_session_id: null,
        source_session_title: null,
        branch_operation: null,
      }),
      files: ref([]),
      events: ref([]),
      loading: ref(false),
      error: ref(null),
      streaming: ref(false),
      refresh: vi.fn(),
      refreshFiles: vi.fn(),
      sendMessage: vi.fn(),
      queueNextMessage: vi.fn(),
      cancelNextMessage: vi.fn(),
      runNextMessage: vi.fn(),
      resumeTask: vi.fn(),
      resolveInteraction: vi.fn(),
    }
  })

  it('shows the archived banner, disables the composer, and opens archive management', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/sessions/:id', component: { template: '<div />' } },
      ],
    })
    await router.push('/sessions/session-1')
    await router.isReady()

    const wrapper = mount(SessionDetailView, {
      props: { sessionId: 'session-1' },
      global: {
        plugins: [router],
        stubs: {
          ArchivedSessionsDialog: ArchivedDialogStub,
          ChatInput: ChatInputStub,
          ChatMessage: true,
          PlanPanel: true,
          SessionHeader: true,
          ThinkingIndicator: true,
          UiButton: true,
          UiState: true,
        },
      },
    })

    expect(wrapper.get('.archived-session-banner').text()).toContain(
      '恢复后才能继续发送消息或重新执行',
    )
    expect(wrapper.get('.stub-chat-input').attributes('data-disabled')).toBe('true')

    await wrapper.get('.archived-session-banner button').trigger('click')
    expect(wrapper.get('.stub-archived-dialog').attributes('data-open')).toBe('true')
  })
})
