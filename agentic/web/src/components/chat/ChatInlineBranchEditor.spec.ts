import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import ChatInlineBranchEditor from './ChatInlineBranchEditor.vue'

function mountEditor(busy = false) {
  return mount(ChatInlineBranchEditor, {
    attachTo: document.body,
    props: {
      content: ' original question ',
      attachmentNames: ['brief.pdf', 'notes.txt'],
      skills: [{ source: 'bundled', name: 'browser' }],
      busy,
    },
    global: {
      stubs: {
        SkillChip: {
          props: ['skill'],
          template: '<span class="stub-skill">{{ skill.name }}</span>',
        },
      },
    },
  })
}

describe('ChatInlineBranchEditor', () => {
  it('focuses the original draft and displays immutable inherited context', async () => {
    const wrapper = mountEditor()
    await nextTick()
    const textarea = wrapper.get('textarea')

    expect(textarea.element.value).toBe(' original question ')
    expect(document.activeElement).toBe(textarea.element)
    expect(wrapper.text()).toContain('原对话不会改变')
    expect(wrapper.text()).toContain('brief.pdf')
    expect(wrapper.text()).toContain('notes.txt')
    expect(wrapper.text()).toContain('沿用 Skills')
    expect(wrapper.text()).toContain('browser')
    expect(textarea.attributes('maxlength')).toBe('10000')
  })

  it('submits trimmed content from the button and keyboard shortcut', async () => {
    const wrapper = mountEditor()
    const textarea = wrapper.get('textarea')
    await textarea.setValue('  revised question  ')
    await wrapper.get('[data-action="submit"]').trigger('click')
    await textarea.trigger('keydown', { key: 'Enter', ctrlKey: true })
    await textarea.trigger('keydown', { key: 'Enter', metaKey: true })

    expect(wrapper.emitted('submit')).toEqual([
      ['revised question'],
      ['revised question'],
      ['revised question'],
    ])
  })

  it('cancels with Escape or the cancel button and blocks invalid submission', async () => {
    const wrapper = mountEditor()
    const textarea = wrapper.get('textarea')
    await textarea.setValue('   ')
    expect(wrapper.get('[data-action="submit"]').attributes('disabled')).toBeDefined()
    await textarea.trigger('keydown', { key: 'Enter', ctrlKey: true })
    expect(wrapper.emitted('submit')).toBeUndefined()

    await textarea.trigger('keydown', { key: 'Escape' })
    await wrapper.get('[data-action="cancel"]').trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(2)
  })

  it('locks cancellation and submission while a branch request is active', async () => {
    const wrapper = mountEditor(true)
    const textarea = wrapper.get('textarea')

    expect(textarea.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-action="cancel"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-action="submit"]').attributes('disabled')).toBeDefined()
    await textarea.trigger('keydown', { key: 'Escape' })
    await textarea.trigger('keydown', { key: 'Enter', ctrlKey: true })
    expect(wrapper.emitted('cancel')).toBeUndefined()
    expect(wrapper.emitted('submit')).toBeUndefined()
  })
})
