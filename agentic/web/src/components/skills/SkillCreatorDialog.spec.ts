import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { sessionApi } from '@/lib/api/session'
import type { SendMessageInput } from '@/types/skill'
import SkillDraftHandoffButton from './SkillDraftHandoffButton.vue'
import SkillCreatorDialog from './SkillCreatorDialog.vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}))

describe('SkillCreatorDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    push.mockReset()
  })

  it('opens on demand and starts a normal session with the bundled creator ref', async () => {
    let submitted: SendMessageInput | undefined
    vi.spyOn(sessionApi, 'createSessionWithInitialMessage').mockImplementation(
      async (input) => {
        submitted = input
        return { sessionId: 'session-1', init: 'encoded-init' }
      },
    )
    const wrapper = mount(SkillCreatorDialog, { props: { open: false } })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.setProps({ open: true })

    await wrapper.get('[data-testid="creator-goal"]').setValue('Create release notes')
    await wrapper.get('[data-testid="creator-examples"]').setValue('Summarize merged changes')
    await wrapper.get('[data-testid="creator-resources"]').setValue('Use references/style.md')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(submitted?.skills).toEqual([
      { source: 'bundled', skill_id: null, name: 'skill-creator' },
    ])
    expect(submitted?.message).toContain('Create release notes')
    expect(submitted?.message).toContain('Summarize merged changes')
    expect(submitted?.message).toContain('Use references/style.md')
    expect(push).toHaveBeenCalledWith('/sessions/session-1?init=encoded-init')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('keeps the start action disabled until a goal is provided', () => {
    const wrapper = mount(SkillCreatorDialog, { props: { open: true } })
    expect(wrapper.get('[data-testid="start-creator"]').attributes('disabled')).toBeDefined()
  })
})

describe('Skill Creator draft handoff', () => {
  beforeEach(() => push.mockReset())

  it('opens the draft returned by skill_draft_create', async () => {
    const wrapper = mount(SkillDraftHandoffButton, {
      props: { draftId: 'draft-1' },
    })

    await wrapper.get('.tool-open-draft').trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'skills',
      query: { draft: 'draft-1' },
    })
  })
})
