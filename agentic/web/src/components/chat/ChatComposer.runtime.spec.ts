import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChatComposer from './ChatComposer.vue'

const ElInputStub = defineComponent({
  name: 'ElInput',
  inheritAttrs: false,
  template: '<textarea />',
})

const SlotStub = defineComponent({
  inheritAttrs: false,
  template: '<div><slot /></div>',
})

function mountComposer(isRunning: boolean, modelValue = 'draft') {
  return mount(ChatComposer, {
    props: { modelValue, isRunning },
    global: {
      stubs: {
        ElInput: ElInputStub,
        ElTooltip: SlotStub,
        ElProgress: true,
        SkillChip: true,
        SkillPicker: true,
      },
    },
  })
}

describe('ChatComposer runtime keyboard behavior', () => {
  it('queues with Enter without stopping the current run', () => {
    const wrapper = mountComposer(true)
    const event = new KeyboardEvent('keydown', {
      key: 'Enter',
      bubbles: true,
      cancelable: true,
    })

    wrapper.get('textarea').element.dispatchEvent(event)

    expect(wrapper.emitted('stop')).toBeUndefined()
    expect(wrapper.emitted('send')).toEqual([[]])
    expect(event.defaultPrevented).toBe(true)
  })

  it('keeps stop as an explicit button action during a run', async () => {
    const wrapper = mountComposer(true)

    await wrapper.get('[aria-label="停止任务"]').trigger('click')

    expect(wrapper.emitted('stop')).toEqual([[]])
    expect(wrapper.find('[aria-label="加入下一条"]').exists()).toBe(true)
  })

  it('still sends a non-empty draft with Enter after the run completes', () => {
    const wrapper = mountComposer(false)
    const event = new KeyboardEvent('keydown', {
      key: 'Enter',
      bubbles: true,
      cancelable: true,
    })

    wrapper.get('textarea').element.dispatchEvent(event)

    expect(wrapper.emitted('send')).toEqual([[]])
    expect(event.defaultPrevented).toBe(true)
  })
})
