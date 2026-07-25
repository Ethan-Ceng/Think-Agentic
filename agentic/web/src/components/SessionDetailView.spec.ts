import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BranchFamilyResponse, SessionDetail } from '@/lib/api/types'
import SessionDetailView from './SessionDetailView.vue'

const mocks = vi.hoisted(() => ({
  detail: undefined as unknown,
  toastInfo: vi.fn(),
  getBranchFamily: vi.fn(),
  createBranch: vi.fn(),
  stopSession: vi.fn(),
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

vi.mock('@/lib/api/session', () => ({
  sessionApi: {
    getBranchFamily: mocks.getBranchFamily,
    createBranch: mocks.createBranch,
    stopSession: mocks.stopSession,
  },
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

function makeDetail(session: Partial<SessionDetail> = {}) {
  return {
    session: ref({
      session_id: 'session-1',
      title: 'Task',
      status: 'completed',
      archived_at: null,
      events: [],
      next_message: null,
      source_session_id: null,
      source_session_title: null,
      forked_from_event_id: null,
      branch_operation: null,
      ...session,
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
}

function makeFamily(currentSessionId = 'branch-1'): BranchFamilyResponse {
  return {
    source_session_id: 'source-1',
    target_event_id: 'event-1',
    current_session_id: currentSessionId,
    variants: [
      {
        session_id: 'source-1',
        title: 'Source task',
        operation: 'original',
        status: 'completed',
        archived_at: null,
        created_at: '2026-07-25T09:00:00',
        is_current: currentSessionId === 'source-1',
      },
      {
        session_id: 'branch-1',
        title: 'Regenerated task',
        operation: 'regenerate',
        status: 'completed',
        archived_at: null,
        created_at: '2026-07-25T09:01:00',
        is_current: currentSessionId === 'branch-1',
      },
      {
        session_id: 'branch-2',
        title: 'Edited task',
        operation: 'edit',
        status: 'completed',
        archived_at: '2026-07-25T10:00:00',
        created_at: '2026-07-25T09:02:00',
        is_current: currentSessionId === 'branch-2',
      },
    ],
  }
}

async function mountView(
  path: string,
  sessionId: string,
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/sessions/:id', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(SessionDetailView, {
    props: { sessionId },
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
  return { router, wrapper }
}

describe('SessionDetailView archived state', () => {
  beforeEach(() => {
    mocks.toastInfo.mockReset()
    mocks.getBranchFamily.mockReset()
    mocks.detail = makeDetail({
        session_id: 'session-1',
        title: 'Archived task',
        archived_at: '2026-07-24T10:00:00',
      })
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

describe('SessionDetailView branch version navigation', () => {
  beforeEach(() => {
    mocks.toastInfo.mockReset()
    mocks.getBranchFamily.mockReset()
    mocks.createBranch.mockReset()
    mocks.stopSession.mockReset()
  })

  it('loads a child family automatically and returns to its source with branchEvent', async () => {
    mocks.detail = makeDetail({
      session_id: 'branch-1',
      title: 'Regenerated task',
      source_session_id: 'source-1',
      source_session_title: 'Source task',
      forked_from_event_id: 'event-1',
      branch_operation: 'regenerate',
    })
    mocks.getBranchFamily.mockResolvedValue(makeFamily('branch-1'))
    const { router, wrapper } = await mountView(
      '/sessions/branch-1',
      'branch-1',
    )

    await vi.waitFor(() => {
      expect(mocks.getBranchFamily).toHaveBeenCalledWith(
        'branch-1',
        undefined,
      )
    })
    await flushPromises()
    expect(wrapper.get('.branch-version-count').text()).toBe('2 / 3')

    await wrapper.get('.branch-version-previous').trigger('click')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe('/sessions/source-1')
    })
    expect(router.currentRoute.value.query).toEqual({
      branchEvent: 'event-1',
    })
    expect(router.currentRoute.value.query.runQueued).toBeUndefined()
  })

  it('restores a source family from branchEvent and switches children without runQueued', async () => {
    mocks.detail = makeDetail({
      session_id: 'source-1',
      title: 'Source task',
    })
    mocks.getBranchFamily.mockResolvedValue(makeFamily('source-1'))
    const { router, wrapper } = await mountView(
      '/sessions/source-1?branchEvent=event-1',
      'source-1',
    )

    await vi.waitFor(() => {
      expect(mocks.getBranchFamily).toHaveBeenCalledWith(
        'source-1',
        'event-1',
      )
    })
    await flushPromises()
    await wrapper.get('select[aria-label="选择对话版本"]').setValue('branch-2')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe('/sessions/branch-2')
    })
    expect(router.currentRoute.value.query).toEqual({})
    expect(router.currentRoute.value.query.runQueued).toBeUndefined()
  })

  it('keeps the lineage fallback when family loading fails', async () => {
    mocks.detail = makeDetail({
      session_id: 'branch-1',
      title: 'Regenerated task',
      source_session_id: 'source-1',
      source_session_title: 'Source task',
      forked_from_event_id: 'event-1',
      branch_operation: 'regenerate',
    })
    mocks.getBranchFamily.mockRejectedValue(new Error('network unavailable'))
    const { router, wrapper } = await mountView(
      '/sessions/branch-1',
      'branch-1',
    )

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('版本导航加载失败')
    })
    expect(wrapper.text()).toContain('network unavailable')
    await wrapper.get('[data-action="source"]').trigger('click')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe('/sessions/source-1')
    })
    expect(router.currentRoute.value.query.branchEvent).toBe('event-1')
  })

  it('closes an invalid source branchEvent without blocking the session', async () => {
    mocks.detail = makeDetail({
      session_id: 'source-1',
      title: 'Source task',
    })
    mocks.getBranchFamily.mockRejectedValue(new Error('invalid anchor'))
    const { router, wrapper } = await mountView(
      '/sessions/source-1?branchEvent=invalid',
      'source-1',
    )

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('版本导航加载失败')
    })
    await wrapper.get('[data-action="close"]').trigger('click')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.query.branchEvent).toBeUndefined()
    })
    expect(wrapper.find('.conversation-scroll').exists()).toBe(true)
  })
})
