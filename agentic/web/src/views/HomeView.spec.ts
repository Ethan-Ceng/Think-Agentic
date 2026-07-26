import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { decodeInitialSessionMessage } from '@/lib/session-init'
import type { Project } from '@/lib/api/types'
import { useProjectsStore } from '@/stores/projects'
import HomeView from './HomeView.vue'

const mocks = vi.hoisted(() => ({
  createSession: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@/lib/api/session', () => ({
  sessionApi: {
    createSession: mocks.createSession,
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    error: mocks.toastError,
    success: vi.fn(),
    info: vi.fn(),
  }),
}))

const ChatInputStub = defineComponent({
  name: 'ChatInput',
  props: {
    disabled: Boolean,
    onSend: Function,
  },
  template: '<div class="chat-input-stub" :data-disabled="disabled" />',
})

async function mountHome(
  initialPath = '/',
  projects: Project[] = [],
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useProjectsStore().$patch({ projects })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: HomeView },
      { path: '/sessions/:id', component: { template: '<div />' } },
    ],
  })
  await router.push(initialPath)
  await router.isReady()

  const wrapper = mount(HomeView, {
    global: {
      plugins: [pinia, router],
      stubs: {
        ChatHeader: true,
        ChatInput: ChatInputStub,
        SuggestedQuestions: true,
      },
    },
  })
  return { router, wrapper }
}

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'project-1',
    name: 'Research',
    created_at: '2026-07-26T10:00:00',
    updated_at: '2026-07-26T10:00:00',
    ...overrides,
  }
}

describe('HomeView attachment handoff', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.createSession.mockResolvedValue({ session_id: 'session-created' })
  })

  it('preserves uploaded and library attachment IDs when creating a session', async () => {
    const { router, wrapper } = await mountHome()
    const onSend = wrapper.getComponent(ChatInputStub).props('onSend') as (
      input: {
        message: string
        attachmentIds: string[]
        skills: never[]
      },
      files: never[],
    ) => Promise<void>

    await onSend({
      message: 'start with these files',
      attachmentIds: ['upload-1', 'library-1'],
      skills: [],
    }, [])

    expect(mocks.createSession).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/sessions/session-created')
    expect(
      decodeInitialSessionMessage(String(router.currentRoute.value.query.init)),
    ).toEqual({
      message: 'start with these files',
      attachments: ['upload-1', 'library-1'],
      skills: [],
      hasInitialMessage: true,
    })
  })

  it('shows a removable Project target and attaches it only when the first message is sent', async () => {
    const { router, wrapper } = await mountHome(
      '/?project=project-1',
      [project()],
    )
    expect(wrapper.text()).toContain('将创建在「Research」')
    expect(mocks.createSession).not.toHaveBeenCalled()

    const onSend = wrapper.getComponent(ChatInputStub).props('onSend') as (
      input: { message: string; attachmentIds: string[]; skills: never[] },
      files: never[],
    ) => Promise<void>
    await onSend({ message: 'Project task', attachmentIds: [], skills: [] }, [])

    expect(mocks.createSession).toHaveBeenCalledWith({
      project_id: 'project-1',
    })
    expect(router.currentRoute.value.path).toBe('/sessions/session-created')
  })

  it('keeps the composer usable when a stale Project fails and can clear the target', async () => {
    mocks.createSession.mockRejectedValueOnce(new Error('项目不存在或无权访问'))
    const { router, wrapper } = await mountHome('/?project=missing')
    expect(wrapper.text()).toContain('目标项目不可用')

    const onSend = wrapper.getComponent(ChatInputStub).props('onSend') as (
      input: { message: string; attachmentIds: string[]; skills: never[] },
      files: never[],
    ) => Promise<void>
    await expect(
      onSend({ message: 'Keep me', attachmentIds: [], skills: [] }, []),
    ).rejects.toThrow('项目不存在或无权访问')

    expect(wrapper.get('.chat-input-stub').attributes('data-disabled')).toBe(
      'false',
    )
    expect(router.currentRoute.value.query.project).toBe('missing')
    await wrapper.get('[data-testid="clear-project-target"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.project).toBeUndefined()
  })
})
