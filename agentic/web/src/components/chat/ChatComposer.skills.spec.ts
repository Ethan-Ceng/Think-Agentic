import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { skillsApi } from '@/lib/api/skills'
import type { SkillSummary } from '@/types/skill'
import ChatInput from './ChatInput.vue'
import ChatComposer from './ChatComposer.vue'
import { decodeInitialSessionMessage, encodeInitialSessionMessage } from '@/lib/session-init'

vi.mock('@/lib/api/skills', () => ({
  skillsApi: { list: vi.fn() },
}))
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }),
}))
vi.mock('./ChatComposer.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      name: 'ChatComposer',
      inheritAttrs: false,
      props: ['modelValue', 'files', 'skills', 'selectedSkills'],
      emits: ['update:modelValue', 'selectSkill', 'removeSkill', 'send'],
      setup: () => () => h('div'),
    }),
  }
})

const skill: SkillSummary = {
  id: 'skill-1', name: 'report-writer', display_name: 'Report Writer', description: 'Reports',
  scope: 'personal', status: 'active', enabled: true, auto_invoke: true,
  current_version_id: 'version-1', updated_at: '2026-07-16T00:00:00Z', created_at: '2026-07-16T00:00:00Z',
}

describe('Chat composer skill serialization', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    vi.mocked(skillsApi.list).mockResolvedValue([skill])
  })

  it('sends stable refs separately and removing a chip preserves message text', async () => {
    const onSend = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(ChatInput, {
      props: { onSend },
      global: { stubs: { ElInput: true, ElTooltip: true, ElProgress: true } },
    })
    await flushPromises()
    const composer = wrapper.findComponent(ChatComposer)

    composer.vm.$emit('selectSkill', skill)
    composer.vm.$emit('update:modelValue', 'Keep this $ literal')
    await flushPromises()
    composer.vm.$emit('removeSkill', 'skill-1')
    expect(composer.props('modelValue')).toBe('Keep this $ literal')

    composer.vm.$emit('selectSkill', skill)
    composer.vm.$emit('send')
    await flushPromises()

    expect(onSend).toHaveBeenCalledWith(
      {
        message: 'Keep this $ literal',
        attachmentIds: [],
        skills: [{ source: 'personal', skill_id: 'skill-1', name: 'report-writer' }],
      },
      [],
    )
  })

  it('preserves stable skill refs when handing a new session through navigation', () => {
    const input = {
      message: 'Draft a report',
      attachmentIds: ['file-1'],
      skills: [{ source: 'personal' as const, skill_id: 'skill-1', name: 'report-writer' }],
    }

    expect(decodeInitialSessionMessage(encodeInitialSessionMessage(input))).toEqual({
      message: 'Draft a report',
      attachments: ['file-1'],
      skills: input.skills,
      hasInitialMessage: true,
    })
  })
})
