import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { projectApi } from '@/lib/api/project'
import { sessionApi } from '@/lib/api/session'
import type { Session } from '@/lib/api/types'
import MoveSessionProjectDialog from './MoveSessionProjectDialog.vue'

const DialogStub = defineComponent({
  props: {
    modelValue: Boolean,
    title: String,
  },
  emits: ['update:modelValue', 'opened', 'closed'],
  template:
    '<section v-if="modelValue" role="dialog"><h2>{{ title }}</h2><button aria-label="关闭测试弹窗" @click="$emit(\'update:modelValue\', false); $emit(\'closed\')">Close</button><slot /><slot name="footer" /></section>',
})

function session(overrides: Partial<Session> = {}): Session {
  return {
    session_id: 'session-1',
    title: 'Original',
    project_id: 'project-1',
    latest_message: 'latest',
    latest_message_at: '2026-07-24T10:00:00',
    status: 'running',
    unread_message_count: 3,
    is_pinned: true,
    archived_at: null,
    has_next_message: true,
    ...overrides,
  }
}

function mountDialog(target = session()) {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(MoveSessionProjectDialog, {
    props: { open: true, session: target },
    global: {
      plugins: [pinia],
      stubs: { ElDialog: DialogStub },
    },
  })
}

describe('MoveSessionProjectDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('loads projects, marks the current project, and filters by name', async () => {
    vi.spyOn(projectApi, 'listProjects').mockResolvedValue({
      projects: [
        {
          id: 'project-1',
          name: 'Research',
          created_at: '2026-07-26T10:00:00',
          updated_at: '2026-07-26T10:00:00',
        },
        {
          id: 'project-2',
          name: 'Release',
          created_at: '2026-07-25T10:00:00',
          updated_at: '2026-07-25T10:00:00',
        },
      ],
    })
    const wrapper = mountDialog()
    await flushPromises()

    expect(wrapper.get('[data-project-id="project-1"]').attributes('aria-checked')).toBe(
      'true',
    )
    expect(wrapper.text()).toContain('未分组')
    await wrapper.get('input[type="search"]').setValue('release')
    expect(wrapper.text()).not.toContain('Research')
    expect(wrapper.text()).toContain('Release')
  })

  it('keeps the Session unchanged until a successful confirmation', async () => {
    vi.spyOn(projectApi, 'listProjects').mockResolvedValue({
      projects: [
        {
          id: 'project-2',
          name: 'Release',
          created_at: '2026-07-25T10:00:00',
          updated_at: '2026-07-25T10:00:00',
        },
      ],
    })
    let resolveMove: ((value: Session) => void) | undefined
    vi.spyOn(sessionApi, 'updateOrganization').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveMove = resolve
        }),
    )
    const original = session()
    const wrapper = mountDialog(original)
    await flushPromises()

    await wrapper.get('[data-project-id="project-2"]').trigger('click')
    expect(original.project_id).toBe('project-1')
    await wrapper.get('form').trigger('submit')
    expect(original.project_id).toBe('project-1')

    resolveMove?.(session({ project_id: 'project-2' }))
    await flushPromises()
    expect(sessionApi.updateOrganization).toHaveBeenCalledWith('session-1', {
      project_id: 'project-2',
    })
    expect(wrapper.emitted('moved')?.[0]?.[0]).toMatchObject({
      project_id: 'project-2',
    })
    expect(wrapper.emitted('update:open')).toContainEqual([false])
  })

  it('preserves the original assignment on failure and retries project loading', async () => {
    vi.spyOn(projectApi, 'listProjects')
      .mockRejectedValueOnce(new Error('project offline'))
      .mockResolvedValueOnce({
        projects: [
          {
            id: 'project-2',
            name: 'Release',
            created_at: '2026-07-25T10:00:00',
            updated_at: '2026-07-25T10:00:00',
          },
        ],
      })
    vi.spyOn(sessionApi, 'updateOrganization').mockRejectedValue(
      new Error('move failed'),
    )
    const original = session()
    const wrapper = mountDialog(original)
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('project offline')
    await wrapper.get('[data-testid="retry-projects"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-project-id="project-2"]').trigger('click')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('move failed')
    expect(original.project_id).toBe('project-1')
    expect(wrapper.emitted('update:open')).toBeUndefined()
  })

  it('can explicitly move a Session to ungrouped', async () => {
    vi.spyOn(projectApi, 'listProjects').mockResolvedValue({ projects: [] })
    vi.spyOn(sessionApi, 'updateOrganization').mockResolvedValue(
      session({ project_id: null }),
    )
    const wrapper = mountDialog()
    await flushPromises()

    await wrapper.get('[data-project-id="unassigned"]').trigger('click')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(sessionApi.updateOrganization).toHaveBeenCalledWith('session-1', {
      project_id: null,
    })
  })

  it('cancels without moving and returns focus to the opening control', async () => {
    vi.spyOn(projectApi, 'listProjects').mockResolvedValue({ projects: [] })
    const updateSpy = vi.spyOn(sessionApi, 'updateOrganization')
    const Host = defineComponent({
      components: { MoveSessionProjectDialog },
      setup() {
        return { open: ref(false), target: session() }
      },
      template:
        '<button id="move-opener" @click="open = true">Move</button><MoveSessionProjectDialog v-model:open="open" :session="target" />',
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(Host, {
      attachTo: document.body,
      global: {
        plugins: [pinia],
        stubs: { ElDialog: DialogStub },
      },
    })
    const opener = wrapper.get('#move-opener')
    ;(opener.element as HTMLButtonElement).focus()
    await opener.trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="关闭测试弹窗"]').trigger('click')

    expect(updateSpy).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(opener.element)
    wrapper.unmount()
  })
})
