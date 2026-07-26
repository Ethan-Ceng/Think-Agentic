import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessageBox } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { sessionApi } from '@/lib/api/session'
import type { Session } from '@/lib/api/types'
import type { Project } from '@/lib/api/types'
import { useProjectsStore } from '@/stores/projects'
import ArchivedSessionsDialog from './ArchivedSessionsDialog.vue'

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => toastMocks,
}))

const DialogStub = defineComponent({
  props: {
    modelValue: Boolean,
    title: String,
  },
  emits: ['update:modelValue', 'closed'],
  template:
    '<section v-if="modelValue"><h2>{{ title }}</h2><button aria-label="关闭测试弹窗" @click="$emit(\'update:modelValue\', false); $emit(\'closed\')">Close</button><slot /><slot name="footer" /></section>',
})

function session(overrides: Partial<Session> = {}): Session {
  return {
    session_id: 'archived-1',
    title: 'Archived research',
    project_id: null,
    latest_message: 'Final report',
    latest_message_at: '2026-07-23T10:00:00',
    status: 'completed',
    unread_message_count: 0,
    is_pinned: false,
    archived_at: '2026-07-24T10:00:00',
    has_next_message: false,
    ...overrides,
  }
}

async function mountDialog(projects: Project[] = []) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useProjectsStore().$patch({ projects })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/sessions/:id', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  await router.isReady()

  return mount(ArchivedSessionsDialog, {
    props: { open: true },
    global: {
      plugins: [pinia, router],
      stubs: { ElDialog: DialogStub },
    },
  })
}

describe('ArchivedSessionsDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    toastMocks.success.mockReset()
    toastMocks.error.mockReset()
    toastMocks.info.mockReset()
  })

  it('loads archived scope, filters locally, and removes a restored session', async () => {
    vi.spyOn(sessionApi, 'getSessions').mockResolvedValue({
      sessions: [session()],
    })
    vi.spyOn(sessionApi, 'updateOrganization').mockResolvedValue(
      session({ archived_at: null }),
    )

    const wrapper = await mountDialog()
    await flushPromises()

    expect(sessionApi.getSessions).toHaveBeenCalledWith('archived')
    expect(wrapper.text()).toContain('Archived research')

    await wrapper.get('input[type="search"]').setValue('missing')
    expect(wrapper.text()).toContain('没有匹配的已归档任务')

    await wrapper.get('input[type="search"]').setValue('')
    await wrapper.get('[aria-label="恢复任务：Archived research"]').trigger('click')
    await flushPromises()

    expect(sessionApi.updateOrganization).toHaveBeenCalledWith('archived-1', {
      archived: false,
    })
    expect(wrapper.text()).not.toContain('Archived research')
    expect(toastMocks.success).toHaveBeenCalledWith('已恢复任务「Archived research」')
  })

  it('uses strong confirmation before permanent deletion', async () => {
    vi.spyOn(sessionApi, 'getSessions').mockResolvedValue({
      sessions: [session()],
    })
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as never)
    vi.spyOn(sessionApi, 'deleteSession').mockResolvedValue()

    const wrapper = await mountDialog()
    await flushPromises()
    await wrapper
      .get('[aria-label="永久删除任务：Archived research"]')
      .trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect(sessionApi.deleteSession).toHaveBeenCalledWith('archived-1')
    expect(wrapper.text()).not.toContain('Archived research')
  })

  it('shows load failure and retries without closing the dialog', async () => {
    vi.spyOn(sessionApi, 'getSessions')
      .mockRejectedValueOnce(new Error('archive offline'))
      .mockResolvedValueOnce({ sessions: [session()] })

    const wrapper = await mountDialog()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('archive offline')
    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()

    expect(sessionApi.getSessions).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Archived research')
  })

  it('returns focus to the opening control after the dialog closes', async () => {
    vi.spyOn(sessionApi, 'getSessions').mockResolvedValue({ sessions: [] })
    const Host = defineComponent({
      components: { ArchivedSessionsDialog },
      setup() {
        return { open: ref(false) }
      },
      template:
        '<button id="archive-opener" @click="open = true">Open archive</button><ArchivedSessionsDialog v-model:open="open" />',
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(Host, {
      attachTo: document.body,
      global: {
        plugins: [pinia, router],
        stubs: { ElDialog: DialogStub },
      },
    })
    const opener = wrapper.get('#archive-opener')
    ;(opener.element as HTMLButtonElement).focus()
    await opener.trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="关闭测试弹窗"]').trigger('click')

    expect(document.activeElement).toBe(opener.element)
    wrapper.unmount()
  })

  it('shows the retained Project name and falls back to ungrouped', async () => {
    vi.spyOn(sessionApi, 'getSessions').mockResolvedValue({
      sessions: [
        session({ project_id: 'project-1' }),
        session({ session_id: 'orphaned', title: 'Orphaned', project_id: 'gone' }),
      ],
    })
    const wrapper = await mountDialog([
      {
        id: 'project-1',
        name: 'Research',
        created_at: '2026-07-26T10:00:00',
        updated_at: '2026-07-26T10:00:00',
      },
    ])
    await flushPromises()

    const rows = wrapper.findAll('.archived-session-row')
    expect(rows[0].text()).toContain('Research')
    expect(rows[1].text()).toContain('未分组')
  })
})
