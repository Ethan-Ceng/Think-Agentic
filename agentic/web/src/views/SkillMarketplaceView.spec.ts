import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { skillsApi } from '@/lib/api/skills'
import type { MarketplaceSkill } from '@/types/skill'
import SkillMarketplaceView from './SkillMarketplaceView.vue'

vi.mock('@/lib/api/skills', () => ({
  skillsApi: {
    listMarketplace: vi.fn(),
    installMarketplace: vi.fn(),
    updateMarketplace: vi.fn(),
    uninstallMarketplace: vi.fn(),
    forkMarketplace: vi.fn(),
  },
}))

const version = {
  id: 'version-2',
  skill_id: 'market-1',
  version: 2,
  manifest: { name: 'market-research', description: 'Research a market.' },
  package_sha256: 'a'.repeat(64),
  package_size: 100,
  file_count: 2,
  status: 'published' as const,
  changelog: 'Reliable sources',
  created_at: '2026-07-16T00:00:00Z',
}

function item(id: string, name: string): MarketplaceSkill {
  return {
    id,
    name,
    display_name: name === 'market-research' ? 'Market Research' : 'Report Writer',
    description: name === 'market-research' ? 'Research a market.' : 'Write reports.',
    latest_version: { ...version, id: `${id}-version`, skill_id: id },
    versions: [{ ...version, id: `${id}-version`, skill_id: id }],
    installation: null,
    update_available: false,
  }
}

describe('SkillMarketplaceView', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
  })

  async function render() {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/skills/marketplace', component: SkillMarketplaceView },
        { path: '/skills', name: 'skills', component: { template: '<div />' } },
      ],
    })
    await router.push('/skills/marketplace')
    await router.isReady()
    return mount(SkillMarketplaceView, { global: { plugins: [router] } })
  }

  it('browses, searches, installs and shows version information', async () => {
    const first = item('market-1', 'market-research')
    const second = item('market-2', 'report-writer')
    vi.mocked(skillsApi.listMarketplace).mockResolvedValue([first, second])
    vi.mocked(skillsApi.installMarketplace).mockResolvedValue({
      ...first,
      installation: {
        pinned_version_id: first.latest_version.id,
        enabled: true,
        auto_invoke: true,
        auto_update: false,
        installed_at: '2026-07-16T00:00:00Z',
        updated_at: '2026-07-16T00:00:00Z',
      },
    })
    const wrapper = await render()
    await flushPromises()

    expect(wrapper.findAll('[data-testid="marketplace-card"]')).toHaveLength(2)
    await wrapper.get('[data-testid="marketplace-search"]').setValue('Research')
    expect(wrapper.findAll('[data-testid="marketplace-card"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('v2')

    await wrapper.get('[data-testid="marketplace-install"]').trigger('click')
    await flushPromises()
    expect(skillsApi.installMarketplace).toHaveBeenCalledWith('market-1')
    expect(wrapper.text()).toContain('已安装')
  })

  it('keeps the prior state when a backend mutation fails', async () => {
    const skill = item('market-1', 'market-research')
    vi.mocked(skillsApi.listMarketplace).mockResolvedValue([skill])
    vi.mocked(skillsApi.installMarketplace).mockRejectedValue(new Error('offline'))
    const wrapper = await render()
    await flushPromises()

    await wrapper.get('[data-testid="marketplace-install"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('offline')
    expect(wrapper.text()).not.toContain('已安装')
  })

  it('updates, uninstalls and routes a fork into the personal draft editor', async () => {
    const base = item('market-1', 'market-research')
    const installed: MarketplaceSkill = {
      ...base,
      update_available: true,
      installation: {
        pinned_version_id: 'version-1',
        enabled: true,
        auto_invoke: true,
        auto_update: false,
        installed_at: '2026-07-15T00:00:00Z',
        updated_at: '2026-07-15T00:00:00Z',
      },
    }
    const updated = {
      ...installed,
      update_available: false,
      installation: { ...installed.installation!, pinned_version_id: base.latest_version.id },
    }
    vi.mocked(skillsApi.listMarketplace).mockResolvedValue([installed])
    vi.mocked(skillsApi.updateMarketplace).mockResolvedValue(updated)
    vi.mocked(skillsApi.uninstallMarketplace).mockResolvedValue({})
    vi.mocked(skillsApi.forkMarketplace).mockResolvedValue({
      draft_id: 'draft-fork',
      skill_name: 'market-research',
      revision: 'b'.repeat(64),
    })
    window.confirm = vi.fn(() => true)
    const wrapper = await render()
    await flushPromises()

    await wrapper.get('[data-testid="marketplace-update"]').trigger('click')
    await flushPromises()
    expect(skillsApi.updateMarketplace).toHaveBeenCalledWith('market-1')
    await wrapper.get('[data-testid="marketplace-uninstall"]').trigger('click')
    await flushPromises()
    expect(skillsApi.uninstallMarketplace).toHaveBeenCalledWith('market-1')
    await wrapper.get('[data-testid="marketplace-fork"]').trigger('click')
    await flushPromises()
    expect(wrapper.vm.$router.currentRoute.value.fullPath).toBe('/skills?draft=draft-fork')
  })
})
