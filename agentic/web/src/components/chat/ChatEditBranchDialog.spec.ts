import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import ChatEditBranchDialog from './ChatEditBranchDialog.vue'
import {
  consumeQueuedRunIntent,
  createQueuedRunIntent,
} from '@/lib/session-init'

const DialogStub = defineComponent({
  props: { modelValue: Boolean },
  emits: ['update:modelValue'],
  template: '<section v-if="modelValue"><slot /><slot name="footer" /></section>',
})
const InputStub = defineComponent({
  props: { modelValue: String },
  emits: ['update:modelValue'],
  template:
    '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
})
const ButtonStub = defineComponent({
  props: { disabled: Boolean, loading: Boolean },
  emits: ['click'],
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
})

function mountDialog() {
  return mount(ChatEditBranchDialog, {
    props: {
      open: true,
      content: ' original question ',
      attachmentNames: ['brief.pdf'],
      skills: [{ source: 'bundled', name: 'browser' }],
    },
    global: {
      stubs: {
        ElDialog: DialogStub,
        ElInput: InputStub,
        ElButton: ButtonStub,
        ElTag: { template: '<span><slot /></span>' },
        SkillChip: { template: '<span>browser</span>' },
      },
    },
  })
}

describe('ChatEditBranchDialog', () => {
  it('shows read-only inherited context and submits trimmed content', async () => {
    const wrapper = mountDialog()
    expect(wrapper.text()).toContain('原对话不会改变')
    expect(wrapper.text()).toContain('brief.pdf')
    expect(wrapper.text()).toContain('沿用 Skills')

    await wrapper.get('textarea').setValue('  revised question  ')
    const submit = wrapper.findAll('button').find((button) =>
      button.text().includes('创建分支并发送'),
    )
    expect(submit).toBeDefined()
    await submit!.trigger('click')
    expect(wrapper.emitted('submit')).toEqual([['revised question']])
  })

  it('consumes queued-run navigation intent exactly once', () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(
      'de305d54-75b4-431b-adb2-eb6b9e546014',
    )
    const token = createQueuedRunIntent('branch-1')

    expect(consumeQueuedRunIntent(token, 'branch-1')).toBe(true)
    expect(consumeQueuedRunIntent(token, 'branch-1')).toBe(false)
  })

  it('falls back to manual queued sending when session storage is unavailable', () => {
    vi.spyOn(window.sessionStorage, 'setItem').mockImplementationOnce(() => {
      throw new DOMException('blocked')
    })

    expect(createQueuedRunIntent('branch-1')).toBe('')
  })
})
