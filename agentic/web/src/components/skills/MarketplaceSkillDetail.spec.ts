import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { MarketplaceSkill } from '@/types/skill'
import MarketplaceSkillDetail from './MarketplaceSkillDetail.vue'

const skill: MarketplaceSkill = {
  id: 'market-1',
  name: 'market-research',
  display_name: 'Market Research',
  description: 'Research a market.',
  latest_version: {
    id: 'version-2',
    skill_id: 'market-1',
    version: 2,
    manifest: { name: 'market-research', description: 'Research a market.' },
    package_sha256: 'a'.repeat(64),
    package_size: 100,
    file_count: 2,
    status: 'published',
    changelog: 'Second release',
    created_at: '2026-07-16T00:00:00Z',
  },
  versions: [],
  installation: null,
  update_available: false,
}

describe('MarketplaceSkillDetail', () => {
  it('installs without a generic confirmation and can fork for editing', async () => {
    const confirm = vi.fn()
    window.confirm = confirm
    const wrapper = mount(MarketplaceSkillDetail, { props: { skill } })

    await wrapper.get('[data-testid="marketplace-install"]').trigger('click')
    await wrapper.get('[data-testid="marketplace-fork"]').trigger('click')

    expect(confirm).not.toHaveBeenCalled()
    expect(wrapper.emitted('install')).toHaveLength(1)
    expect(wrapper.emitted('fork')).toHaveLength(1)
    expect(wrapper.text()).toContain('v2')
  })

  it('shows update availability and confirms only uninstall', async () => {
    const installed: MarketplaceSkill = {
      ...skill,
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
    const confirm = vi.fn(() => true)
    window.confirm = confirm
    const wrapper = mount(MarketplaceSkillDetail, { props: { skill: installed } })

    await wrapper.get('[data-testid="marketplace-update"]').trigger('click')
    await wrapper.get('[data-testid="marketplace-uninstall"]').trigger('click')

    expect(wrapper.emitted('update')).toHaveLength(1)
    expect(wrapper.emitted('uninstall')).toHaveLength(1)
    expect(confirm).toHaveBeenCalledTimes(1)
  })
})
