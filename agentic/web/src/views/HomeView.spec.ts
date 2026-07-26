import { createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { decodeInitialSessionMessage } from '@/lib/session-init'
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

async function mountHome() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: HomeView },
      { path: '/sessions/:id', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  await router.isReady()

  const wrapper = mount(HomeView, {
    global: {
      plugins: [createPinia(), router],
      stubs: {
        ChatHeader: true,
        ChatInput: ChatInputStub,
        SuggestedQuestions: true,
      },
    },
  })
  return { router, wrapper }
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
})
