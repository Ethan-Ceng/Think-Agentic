import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessageBox } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { projectApi } from '@/lib/api/project'
import { sessionApi } from '@/lib/api/session'
import type { Project, Session } from '@/lib/api/types'
import { useProjectsStore } from '@/stores/projects'
import { useSessionsStore } from '@/stores/sessions'
import ProjectSections from './ProjectSections.vue'

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => toast,
}))

vi.mock('@/composables/useSidebar', () => ({
  useSidebar: () => ({ close: vi.fn() }),
}))

const SessionListStub = defineComponent({
  name: 'SessionList',
  props: {
    items: { type: Array, default: () => [] },
    query: String,
    flat: Boolean,
    showEmpty: Boolean,
    showArchivedEntry: Boolean,
  },
  emits: ['move'],
  template:
    '<div class="stub-session-list"><button v-for="item in items" :key="item.session_id" class="stub-session" :data-session-id="item.session_id" @click="$emit(\'move\', item)">{{ item.title }}</button></div>',
})

const ProjectDialogStub = defineComponent({
  name: 'ProjectDialog',
  props: {
    open: Boolean,
    mode: String,
    project: Object,
  },
  emits: ['update:open', 'saved'],
  template:
    '<div class="stub-project-dialog" :data-open="open" :data-mode="mode" :data-project-id="project?.id || \'\'" />',
})

const MoveDialogStub = defineComponent({
  name: 'MoveSessionProjectDialog',
  props: {
    open: Boolean,
    session: Object,
  },
  emits: ['update:open', 'moved'],
  template:
    '<div class="stub-move-dialog" :data-open="open" :data-session-id="session?.session_id || \'\'" />',
})

const DropdownStub = defineComponent({
  name: 'ElDropdown',
  emits: ['command'],
  template: '<div class="stub-dropdown"><slot /><slot name="dropdown" /></div>',
})
const DropdownMenuStub = defineComponent({
  name: 'ElDropdownMenu',
  template: '<div><slot /></div>',
})
const DropdownItemStub = defineComponent({
  name: 'ElDropdownItem',
  props: { command: String },
  template: '<div><slot /></div>',
})

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'project-1',
    name: 'Research',
    created_at: '2026-07-24T10:00:00',
    updated_at: '2026-07-24T10:00:00',
    ...overrides,
  }
}

function session(overrides: Partial<Session> = {}): Session {
  return {
    session_id: 'session-1',
    title: 'Task',
    project_id: null,
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

async function mountSections(
  projects: Project[],
  sessions: Session[],
  initialPath = '/',
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  vi.spyOn(projectApi, 'listProjects').mockResolvedValue({ projects })
  vi.spyOn(sessionApi, 'getSessions').mockResolvedValue({ sessions })
  await useProjectsStore().load()
  await useSessionsStore().refresh()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/sessions/:id', component: { template: '<div />' } },
    ],
  })
  await router.push(initialPath)
  await router.isReady()

  const wrapper = mount(ProjectSections, {
    global: {
      plugins: [pinia, router],
      stubs: {
        SessionList: SessionListStub,
        ProjectDialog: ProjectDialogStub,
        MoveSessionProjectDialog: MoveDialogStub,
        ElDropdown: DropdownStub,
        ElDropdownMenu: DropdownMenuStub,
        ElDropdownItem: DropdownItemStub,
        ArchivedSessionsDialog: true,
      },
    },
  })
  return { router, wrapper }
}

describe('ProjectSections', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    toast.success.mockReset()
    toast.error.mockReset()
    window.localStorage.clear()
  })

  it('renders exactly one Project → Session path with stable directory ordering', async () => {
    const { wrapper } = await mountSections(
      [
        project({ id: 'older', name: 'Older', created_at: '2026-07-23T10:00:00' }),
        project({ id: 'newer', name: 'Newer', created_at: '2026-07-25T10:00:00' }),
      ],
      [
        session({ session_id: 'newer-regular', title: 'Regular', project_id: 'newer' }),
        session({
          session_id: 'newer-pinned',
          title: 'Pinned',
          project_id: 'newer',
          is_pinned: true,
          latest_message_at: '2026-07-22T10:00:00',
        }),
        session({ session_id: 'older-task', title: 'Older task', project_id: 'older' }),
        session({ session_id: 'free', title: 'Free task' }),
        session({ session_id: 'unknown', title: 'Unknown task', project_id: 'gone' }),
      ],
    )

    const sections = wrapper.findAll('[data-project-section]')
    expect(sections.map((item) => item.attributes('data-project-section'))).toEqual([
      'newer',
      'older',
      'unassigned',
    ])
    expect(
      sections[0].findAll('.stub-session').map((item) => item.attributes('data-session-id')),
    ).toEqual(['newer-pinned', 'newer-regular'])
    expect(
      sections[2].findAll('.stub-session').map((item) => item.attributes('data-session-id')),
    ).toEqual(['free', 'unknown'])
    expect(wrapper.findAll('.stub-session')).toHaveLength(5)
    expect(wrapper.text()).not.toContain('今天')
    expect(wrapper.text()).not.toContain('昨天')
  })

  it('keeps empty projects visible and starts a task through a query without creating a Session', async () => {
    const createSession = vi.spyOn(sessionApi, 'createSession')
    const { router, wrapper } = await mountSections([project()], [])

    expect(wrapper.get('[data-project-section="project-1"]').text()).toContain(
      '暂无任务',
    )
    await wrapper
      .get('[data-testid="create-task-project-1"]')
      .trigger('click')
    await flushPromises()

    expect(createSession).not.toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.query.project).toBe('project-1')
  })

  it('persists only existing expansion keys and preserves all sessions on load failure', async () => {
    window.localStorage.setItem(
      'agentic.projects.expanded',
      JSON.stringify(['project-1', 'missing']),
    )
    const { wrapper } = await mountSections(
      [project(), project({ id: 'project-2', name: 'Release' })],
      [session({ session_id: 'one', project_id: 'project-1' }), session({ session_id: 'two', project_id: 'project-2' })],
    )

    expect(wrapper.get('[data-project-section="project-1"]').classes()).toContain(
      'expanded',
    )
    expect(wrapper.get('[data-project-section="project-2"]').classes()).not.toContain(
      'expanded',
    )
    expect(window.localStorage.getItem('agentic.projects.expanded')).not.toContain(
      'missing',
    )

    vi.mocked(projectApi.listProjects).mockRejectedValueOnce(
      new Error('project offline'),
    )
    await expect(useProjectsStore().load()).rejects.toThrow('project offline')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('project offline')
    expect(wrapper.findAll('.stub-session')).toHaveLength(2)
  })

  it('opens create, rename and move controls and strongly confirms safe deletion', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as never)
    vi.spyOn(projectApi, 'deleteProject').mockResolvedValue()
    const { wrapper } = await mountSections(
      [project()],
      [session({ status: 'running', project_id: 'project-1' })],
    )

    await wrapper.get('[data-testid="create-project"]').trigger('click')
    expect(wrapper.get('.stub-project-dialog').attributes('data-mode')).toBe(
      'create',
    )

    const dropdown = wrapper.findComponent(DropdownStub)
    dropdown.vm.$emit('command', 'rename')
    await flushPromises()
    expect(wrapper.get('.stub-project-dialog').attributes('data-mode')).toBe(
      'rename',
    )
    expect(wrapper.get('.stub-project-dialog').attributes('data-project-id')).toBe(
      'project-1',
    )

    await wrapper.get('.stub-session').trigger('click')
    expect(wrapper.get('.stub-move-dialog').attributes('data-session-id')).toBe(
      'session-1',
    )

    dropdown.vm.$emit('command', 'delete')
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('任务将移到未分组'),
      expect.any(String),
      expect.any(Object),
    )
    expect(projectApi.deleteProject).toHaveBeenCalledWith('project-1')
    expect(wrapper.find('[data-project-section="project-1"]').exists()).toBe(false)
  })
})
