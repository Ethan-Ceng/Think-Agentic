import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { SkillRef, SkillSummary } from '@/types/skill'
import SkillPicker from './SkillPicker.vue'

const makeSkill = (index: number, enabled = true): SkillSummary => ({
  id: `skill-${index}`,
  name: `report-${index}`,
  display_name: `Report ${index}`,
  description: `Report helper ${index}`,
  scope: 'personal',
  status: 'active',
  enabled,
  auto_invoke: true,
  current_version_id: `version-${index}`,
  updated_at: '2026-07-16T00:00:00Z',
  created_at: '2026-07-16T00:00:00Z',
})

const refFor = (skill: SkillSummary): SkillRef => ({
  source: 'personal',
  skill_id: skill.id,
  name: skill.name,
})

describe('SkillPicker', () => {
  it('filters enabled skills and selects the keyboard-highlighted match', async () => {
    const skills = [makeSkill(1), makeSkill(2), makeSkill(3, false)]
    const wrapper = mount(SkillPicker, {
      props: { skills, query: '2', selected: [] },
    })

    expect(wrapper.text()).toContain('Report 2')
    expect(wrapper.text()).not.toContain('Report 1')
    expect(wrapper.text()).not.toContain('Report 3')
    await wrapper.trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('select')?.[0]).toEqual([skills[1]])
  })

  it('rejects duplicate choices and enforces the maximum of five', async () => {
    const skills = Array.from({ length: 6 }, (_, index) => makeSkill(index + 1))
    const duplicate = mount(SkillPicker, {
      props: { skills, query: '1', selected: [refFor(skills[0])] },
    })
    await duplicate.trigger('keydown', { key: 'Enter' })
    expect(duplicate.emitted('select')).toBeUndefined()

    const full = mount(SkillPicker, {
      props: { skills, query: '', selected: skills.slice(0, 5).map(refFor), max: 5 },
    })
    await full.findAll('button')[5]?.trigger('click')
    expect(full.emitted('select')).toBeUndefined()
    expect(full.text()).toContain('最多选择 5 个')
  })
})
