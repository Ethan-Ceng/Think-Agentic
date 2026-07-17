import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { skillsApi } from '@/lib/api/skills'
import type { SkillValidationResult } from '@/types/skill'
import SkillEditor from './SkillEditor.vue'

vi.mock('@/lib/api/skills', () => ({
  skillsApi: {
    getDraftTree: vi.fn(),
    readDraftFile: vi.fn(),
    writeDraftFile: vi.fn(),
    validateDraft: vi.fn(),
    publishDraft: vi.fn(),
  },
}))

const invalid: SkillValidationResult = {
  valid: false,
  revision: 'a'.repeat(64),
  manifest: null,
  diagnostics: [
    {
      file: 'references/guide.md',
      line: 2,
      column: 1,
      code: 'invalid_reference',
      message: 'Broken reference',
    },
  ],
}

describe('SkillEditor', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    vi.mocked(skillsApi.getDraftTree).mockResolvedValue({
      tree: [
        { path: 'SKILL.md', kind: 'file', size: 20 },
        { path: 'references', kind: 'directory' },
        { path: 'references/guide.md', kind: 'file', size: 10 },
      ],
      revision: '0'.repeat(64),
    })
    vi.mocked(skillsApi.readDraftFile).mockImplementation(async (_draftId, path) => ({
      path,
      content: path === 'SKILL.md' ? '# Original' : 'guide',
    }))
    vi.mocked(skillsApi.writeDraftFile).mockResolvedValue({ path: 'SKILL.md' })
  })

  it('opens SKILL.md first, tracks dirty content and saves it', async () => {
    const wrapper = mount(SkillEditor, { props: { draftId: 'draft-1' } })
    await flushPromises()
    expect(wrapper.get('[data-testid="active-path"]').text()).toBe('SKILL.md')

    await wrapper.get('[data-testid="skill-content"]').setValue('# Changed')
    expect(wrapper.find('[data-testid="dirty-indicator"]').exists()).toBe(true)
    await wrapper.get('[data-testid="save-skill-file"]').trigger('click')
    await flushPromises()

    expect(skillsApi.writeDraftFile).toHaveBeenCalledWith('draft-1', 'SKILL.md', '# Changed')
    expect(wrapper.find('[data-testid="dirty-indicator"]').exists()).toBe(false)
  })

  it('navigates from diagnostics and blocks publish after failed validation', async () => {
    vi.mocked(skillsApi.validateDraft).mockResolvedValue(invalid)
    const wrapper = mount(SkillEditor, { props: { draftId: 'draft-1' } })
    await flushPromises()
    await wrapper.get('[data-testid="validate-skill"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="publish-skill"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="diagnostic-0"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="active-path"]').text()).toBe('references/guide.md')
  })
})
