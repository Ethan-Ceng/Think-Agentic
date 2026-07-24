import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { sessionApi } from '@/lib/api/session'
import type { Session } from '@/lib/api/types'
import { useSessionsStore } from '@/stores/sessions'
import SessionList from './SessionList.vue'

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  }),
}))

vi.mock('@/composables/useSidebar', () => ({
  useSidebar: () => ({
    close: vi.fn(),
  }),
}))

const SessionItemStub = defineComponent({
  name: 'SessionListItem',
  props: {
    session: { type: Object, required: true },
    active: Boolean,
    busy: Boolean,
  },
  template: '<div class="stub-session">{{ session.title }}</div>',
})

const ArchivedDialogStub = defineComponent({
  name: 'ArchivedSessionsDialog',
  props: { open: Boolean },
  emits: ['update:open'],
  template: '<div class="stub-archived-dialog" :data-open="open" />',
})

function session(overrides: Partial<Session>): Session {
  return {
    session_id: 'session-1',
    title: 'Task',
    latest_message: '',
    latest_message_at: '2026-07-24T10:00:00',
    status: 'completed',
    unread_message_count: 0,
    is_pinned: false,
    archived_at: null,
    has_next_message: false,
    ...overrides,
  }
}

describe('SessionList organization groups', () => {
  it('renders pinned sessions before date groups', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    vi.spyOn(sessionApi, 'getSessions').mockResolvedValue({
      sessions: [
        session({ session_id: 'regular', title: 'Regular' }),
        session({ session_id: 'pinned', title: 'Pinned', is_pinned: true }),
      ],
    })
    const store = useSessionsStore()
    await store.refresh()
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/sessions/:id', component: { template: '<div />' } },
      ],
    })
    await router.push('/')
    await router.isReady()

    const wrapper = mount(SessionList, {
      global: {
        plugins: [pinia, router],
        stubs: {
          SessionListItem: SessionItemStub,
          ArchivedSessionsDialog: ArchivedDialogStub,
        },
      },
    })

    const groups = wrapper.findAll('.session-group')
    expect(groups[0].get('h3').text()).toBe('已置顶')
    expect(groups[0].text()).toContain('Pinned')
    expect(groups[1].text()).toContain('Regular')

    await wrapper.get('.archived-sessions-entry').trigger('click')
    expect(wrapper.get('.stub-archived-dialog').attributes('data-open')).toBe('true')
  })
})
