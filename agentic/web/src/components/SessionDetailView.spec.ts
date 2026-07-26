import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BranchFamilyResponse, SessionDetail } from '@/lib/api/types'
import {
  consumeQueuedRunIntent,
  createQueuedRunIntent,
} from '@/lib/session-init'
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
  props: {
    disabled: Boolean,
    isRunning: Boolean,
    onSend: Function,
    sessionId: String,
  },
  template:
    '<div class="stub-chat-input" :data-disabled="disabled" :data-running="isRunning" />',
})

const ArchivedDialogStub = defineComponent({
  name: 'ArchivedSessionsDialog',
  props: { open: Boolean },
  emits: ['update:open'],
  template: '<div class="stub-archived-dialog" :data-open="open" />',
})

const ChatMessageStub = defineComponent({
  name: 'ChatMessage',
  props: {
    item: { type: Object, required: true },
    editing: Boolean,
    editBusy: Boolean,
  },
  emits: ['branchAction', 'editSubmit', 'editCancel', 'artifactOpen'],
  setup(_, { emit }) {
    return {
      openArtifact: () => emit('artifactOpen', {
        id: 'event-assistant-1:fence:0',
        scope: 'event-assistant-1',
        index: 0,
        title: 'artifact-1.html',
        language: 'html',
        content: '<main>demo</main>\n',
        kind: 'html',
        availableViews: ['source', 'preview'],
      }),
    }
  },
  template: `
    <article
      class="stub-chat-message"
      :data-event-id="item.sourceEventId"
      :data-editing="editing ? 'true' : 'false'"
      :data-edit-busy="editBusy ? 'true' : 'false'"
    >
      <button
        v-if="item.kind === 'user'"
        class="start-inline-edit"
        type="button"
        @click="$emit('branchAction', 'edit', item)"
      />
      <button
        v-if="editing"
        class="submit-inline-edit"
        type="button"
        @click="$emit('editSubmit', ' revised question ')"
      />
      <button
        v-if="editing"
        class="cancel-inline-edit"
        type="button"
        @click="$emit('editCancel')"
      />
      <button
        v-if="item.kind === 'assistant'"
        class="open-inline-artifact"
        type="button"
        @click="openArtifact"
      />
    </article>
  `,
})

const ArtifactPreviewStub = defineComponent({
  name: 'ChatArtifactPreviewPanel',
  props: { artifact: { type: Object, required: true } },
  emits: ['close'],
  template:
    '<aside class="stub-artifact-preview" :data-artifact-id="artifact.id"><button class="close-artifact-preview" @click="$emit(\'close\')" /></aside>',
})

const ToolPreviewStub = defineComponent({
  name: 'ToolPreviewPanel',
  props: { tool: { type: Object, required: true } },
  emits: ['close', 'jumpToLatest', 'openVnc'],
  template:
    '<aside class="stub-tool-preview" :data-tool-id="tool.tool_call_id"><button class="close-tool-preview" @click="$emit(\'close\')" /></aside>',
})

const FilePreviewStub = defineComponent({
  name: 'FilePreviewPanel',
  props: { file: { type: Object, required: true } },
  emits: ['close'],
  template: '<aside class="stub-file-preview" />',
})

const TracePanelStub = defineComponent({
  name: 'TracePanel',
  emits: ['close'],
  template: '<aside class="stub-trace-preview" />',
})

function makeDetail(session: Partial<SessionDetail> = {}) {
  const sessionValue = {
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
  } as SessionDetail
  return {
    session: ref(sessionValue),
    files: ref([]),
    events: ref(sessionValue.events),
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

function makeEditableEvents() {
  return [
    {
      type: 'message',
      data: {
        role: 'user',
        message: 'first question',
        event_id: 'event-user-1',
        created_at: '2026-07-25T11:00:00',
      },
    },
    {
      type: 'message',
      data: {
        role: 'assistant',
        message: 'first answer',
        event_id: 'event-assistant-1',
        created_at: '2026-07-25T11:00:10',
      },
    },
    {
      type: 'message',
      data: {
        role: 'user',
        message: 'second question',
        event_id: 'event-user-2',
        created_at: '2026-07-25T11:01:00',
      },
    },
  ] as SessionDetail['events']
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
        ChatArtifactPreviewPanel: ArtifactPreviewStub,
        ChatInput: ChatInputStub,
        ChatMessage: ChatMessageStub,
        FilePreviewPanel: FilePreviewStub,
        PlanPanel: true,
        SessionHeader: true,
        ThinkingIndicator: true,
        ToolPreviewPanel: ToolPreviewStub,
        TracePanel: TracePanelStub,
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
          ChatArtifactPreviewPanel: ArtifactPreviewStub,
          ChatInput: ChatInputStub,
          ChatMessage: ChatMessageStub,
          FilePreviewPanel: FilePreviewStub,
          PlanPanel: true,
          SessionHeader: true,
          ThinkingIndicator: true,
          ToolPreviewPanel: ToolPreviewStub,
          TracePanel: TracePanelStub,
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

describe('SessionDetailView attachment sending', () => {
  beforeEach(() => {
    mocks.toastInfo.mockReset()
    mocks.getBranchFamily.mockReset()
    mocks.createBranch.mockReset()
    mocks.stopSession.mockReset()
  })

  it('passes attachment IDs through the normal session send path', async () => {
    const detail = makeDetail({ status: 'completed' })
    mocks.detail = detail
    const { wrapper } = await mountView('/sessions/session-1', 'session-1')
    const chatInput = wrapper.getComponent(ChatInputStub)
    const onSend = chatInput.props('onSend') as (
      input: {
        message: string
        attachmentIds: string[]
        skills: never[]
      },
      files: Array<{
        id: string
        filename: string
        extension: string
        size: number
        contentType: string
      }>,
    ) => Promise<void>
    const input = {
      message: 'review the file',
      attachmentIds: ['library-1'],
      skills: [] as never[],
    }

    await onSend(input, [{
      id: 'library-1',
      filename: 'notes.pdf',
      extension: 'pdf',
      size: 128,
      contentType: 'application/pdf',
    }])

    expect(detail.sendMessage).toHaveBeenCalledWith(input)
    expect(detail.queueNextMessage).not.toHaveBeenCalled()
  })

  it('passes attachment IDs through the running-session next-message queue', async () => {
    const detail = makeDetail({ status: 'running' })
    mocks.detail = detail
    const { wrapper } = await mountView('/sessions/session-1', 'session-1')
    const chatInput = wrapper.getComponent(ChatInputStub)
    const onSend = chatInput.props('onSend') as (
      input: {
        message: string
        attachmentIds: string[]
        skills: never[]
      },
      files: never[],
    ) => Promise<void>
    const input = {
      message: 'use this next',
      attachmentIds: ['library-queue'],
      skills: [] as never[],
    }

    await onSend(input, [])

    expect(detail.queueNextMessage).toHaveBeenCalledWith(input)
    expect(detail.sendMessage).not.toHaveBeenCalled()
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

describe('SessionDetailView inline branch editing', () => {
  beforeEach(() => {
    mocks.toastInfo.mockReset()
    mocks.getBranchFamily.mockReset()
    mocks.createBranch.mockReset()
    mocks.stopSession.mockReset()
    window.sessionStorage.clear()
    mocks.detail = makeDetail({ events: makeEditableEvents() })
  })

  it('keeps at most one user message in edit mode and supports cancel', async () => {
    const { wrapper } = await mountView('/sessions/session-1', 'session-1')

    await wrapper
      .get('[data-event-id="event-user-1"] .start-inline-edit')
      .trigger('click')
    expect(
      wrapper.get('[data-event-id="event-user-1"]').attributes('data-editing'),
    ).toBe('true')

    await wrapper
      .get('[data-event-id="event-user-2"] .start-inline-edit')
      .trigger('click')
    expect(
      wrapper.get('[data-event-id="event-user-1"]').attributes('data-editing'),
    ).toBe('false')
    expect(
      wrapper.get('[data-event-id="event-user-2"]').attributes('data-editing'),
    ).toBe('true')

    await wrapper
      .get('[data-event-id="event-user-2"] .cancel-inline-edit')
      .trigger('click')
    expect(
      wrapper.get('[data-event-id="event-user-2"]').attributes('data-editing'),
    ).toBe('false')
  })

  it('retains the editor after failure and reuses the request id on retry', async () => {
    mocks.createBranch
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValueOnce({
        session_id: 'branch-1',
        forked_from_event_id: 'event-user-1',
        queued: true,
      })
    const randomUuid = vi
      .spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('de305d54-75b4-431b-adb2-eb6b9e546014')
      .mockReturnValueOnce('123e4567-e89b-42d3-a456-426614174000')
    const { router, wrapper } = await mountView(
      '/sessions/session-1',
      'session-1',
    )

    await wrapper
      .get('[data-event-id="event-user-1"] .start-inline-edit')
      .trigger('click')
    await wrapper
      .get('[data-event-id="event-user-1"] .submit-inline-edit')
      .trigger('click')
    await flushPromises()
    expect(
      wrapper.get('[data-event-id="event-user-1"]').attributes('data-editing'),
    ).toBe('true')

    await wrapper
      .get('[data-event-id="event-user-1"] .submit-inline-edit')
      .trigger('click')
    await flushPromises()

    expect(mocks.createBranch).toHaveBeenCalledTimes(2)
    const firstPayload = mocks.createBranch.mock.calls[0][1]
    const retryPayload = mocks.createBranch.mock.calls[1][1]
    expect(firstPayload).toMatchObject({
      operation: 'edit',
      target_event_id: 'event-user-1',
      message: ' revised question ',
    })
    expect(retryPayload.request_id).toBe(firstPayload.request_id)
    expect(router.currentRoute.value.path).toBe('/sessions/branch-1')
    expect(router.currentRoute.value.query.branchEvent).toBe('event-user-1')
    const queuedToken = String(router.currentRoute.value.query.runQueued)
    expect(consumeQueuedRunIntent(queuedToken, 'branch-1')).toBe(true)
    expect(consumeQueuedRunIntent(queuedToken, 'branch-1')).toBe(false)
    randomUuid.mockRestore()
  })

  it('cancels editing when the session becomes unavailable for branching', async () => {
    const { wrapper } = await mountView('/sessions/session-1', 'session-1')
    await wrapper
      .get('[data-event-id="event-user-1"] .start-inline-edit')
      .trigger('click')
    expect(
      wrapper.get('[data-event-id="event-user-1"]').attributes('data-editing'),
    ).toBe('true')

    ;(mocks.detail as ReturnType<typeof makeDetail>).session.value.status =
      'running'
    await nextTick()

    expect(
      wrapper.get('[data-event-id="event-user-1"]').attributes('data-editing'),
    ).toBe('false')
  })

  it('falls back to manual queued sending when session storage is unavailable', () => {
    const setItem = vi
      .spyOn(window.sessionStorage, 'setItem')
      .mockImplementationOnce(() => {
        throw new DOMException('blocked')
      })

    expect(createQueuedRunIntent('branch-1')).toBe('')
    setItem.mockRestore()
  })
})

describe('SessionDetailView preview selection', () => {
  beforeEach(() => {
    mocks.toastInfo.mockReset()
    mocks.getBranchFamily.mockReset()
    mocks.createBranch.mockReset()
    mocks.stopSession.mockReset()
    mocks.detail = makeDetail({
      status: 'running',
      events: [
        {
          type: 'message',
          data: {
            role: 'assistant',
            message: 'artifact response',
            event_id: 'event-assistant-1',
          },
        },
      ] as SessionDetail['events'],
    })
  })

  it('pins a user artifact, ignores new auto tools, and resumes following after close', async () => {
    const detail = mocks.detail as ReturnType<typeof makeDetail>
    const { wrapper } = await mountView('/sessions/session-1', 'session-1')

    await wrapper.get('.open-inline-artifact').trigger('click')
    await flushPromises()
    expect(wrapper.get('.stub-artifact-preview').attributes('data-artifact-id')).toBe(
      'event-assistant-1:fence:0',
    )

    detail.events.value = [
      ...(detail.events.value ?? []),
      {
        type: 'tool',
        data: {
          tool_call_id: 'tool-1',
          name: 'shell_execute',
          function: 'shell_execute',
          status: 'completed',
          args: {},
          content: { result: 'first' },
        },
      },
    ] as SessionDetail['events']
    await nextTick()
    await flushPromises()

    expect(wrapper.find('.stub-artifact-preview').exists()).toBe(true)
    expect(wrapper.find('.stub-tool-preview').exists()).toBe(false)

    await wrapper.get('.close-artifact-preview').trigger('click')
    detail.events.value = [
      ...(detail.events.value ?? []),
      {
        type: 'tool',
        data: {
          tool_call_id: 'tool-2',
          name: 'shell_execute',
          function: 'shell_execute',
          status: 'completed',
          args: {},
          content: { result: 'second' },
        },
      },
    ] as SessionDetail['events']
    await nextTick()
    await flushPromises()

    expect(wrapper.find('.stub-artifact-preview').exists()).toBe(false)
    expect(wrapper.get('.stub-tool-preview').attributes('data-tool-id')).toBe('tool-2')
  })

  it('clears a pinned preview when the Session changes', async () => {
    const { wrapper } = await mountView('/sessions/session-1', 'session-1')
    await wrapper.get('.open-inline-artifact').trigger('click')
    await flushPromises()
    expect(wrapper.find('.stub-artifact-preview').exists()).toBe(true)

    await wrapper.setProps({ sessionId: 'session-2' })
    await nextTick()

    expect(wrapper.find('.stub-artifact-preview').exists()).toBe(false)
  })
})
