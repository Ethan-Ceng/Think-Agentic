import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { skillsApi } from '@/lib/api/skills'
import { useAuthStore } from '@/stores/auth'
import type { SkillDetail, SkillSummary } from '@/types/skill'
import SkillsSidePanel from './SkillsSidePanel.vue'

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/lib/api/skills', () => ({
  skillsApi: {
    list: vi.fn(),
    setEnabled: vi.fn(),
    setAutoInvoke: vi.fn(),
  },
}))

const skill: SkillSummary = {
  id: 'skill-1',
  name: 'report-writer',
  display_name: 'Report Writer',
  description: 'Write reports.',
  scope: 'personal',
  status: 'active',
  enabled: true,
  auto_invoke: true,
  current_version_id: 'version-1',
  updated_at: '2026-07-16T00:00:00Z',
  created_at: '2026-07-15T00:00:00Z',
}

const detail = (changes: Partial<SkillSummary> = {}): SkillDetail => ({
  skill: { ...skill, ...changes },
  version: null,
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function mountPanel() {
  return mount(SkillsSidePanel, {
    global: {
      stubs: {
        RouterLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('SkillsSidePanel', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.user = {
      id: 'user-1',
      email: 'user@example.com',
      name: 'User',
      avatar: '',
      status: 'active',
    }
  })

  it('shows loading, empty and error states', async () => {
    const pending = deferred<SkillSummary[]>()
    vi.mocked(skillsApi.list).mockReturnValueOnce(pending.promise)
    const wrapper = mountPanel()
    await Promise.resolve()
    expect(wrapper.find('[data-testid="skills-loading"]').exists()).toBe(true)

    pending.resolve([])
    await flushPromises()
    expect(wrapper.find('[data-testid="skills-empty"]').exists()).toBe(true)

    vi.mocked(skillsApi.list).mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('[data-testid="skills-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="skills-error"]').text()).toContain('offline')
  })

  it('renders source and status labels and updates both switches', async () => {
    vi.mocked(skillsApi.list).mockResolvedValue([skill])
    vi.mocked(skillsApi.setEnabled).mockResolvedValue(detail({ enabled: false }))
    vi.mocked(skillsApi.setAutoInvoke).mockResolvedValue(detail({ auto_invoke: false }))
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.text()).toContain('个人')
    expect(wrapper.text()).toContain('已发布')
    await wrapper.get('[data-testid="auto-skill-1"]').setValue(false)
    await wrapper.get('[data-testid="enabled-skill-1"]').setValue(false)
    await flushPromises()

    expect(skillsApi.setEnabled).toHaveBeenCalledWith('skill-1', false)
    expect(skillsApi.setAutoInvoke).toHaveBeenCalledWith('skill-1', false)
  })

  it('reloads isolated state when the authenticated user changes', async () => {
    const second = { ...skill, id: 'skill-2', name: 'code-reviewer', display_name: 'Code Reviewer' }
    vi.mocked(skillsApi.list).mockResolvedValueOnce([skill]).mockResolvedValueOnce([second])
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('Report Writer')

    useAuthStore().user = {
      id: 'user-2',
      email: 'second@example.com',
      name: 'Second',
      avatar: '',
      status: 'active',
    }
    await flushPromises()

    expect(wrapper.text()).not.toContain('Report Writer')
    expect(wrapper.text()).toContain('Code Reviewer')
  })
})
