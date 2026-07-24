import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MessageActions from './MessageActions.vue'

const global = {
  stubs: {
    ElTooltip: { template: '<span><slot /></span>' },
  },
}

describe('MessageActions', () => {
  it('shows fork and role-specific actions and emits stable operations', async () => {
    const user = mount(MessageActions, {
      props: {
        content: 'question',
        role: 'user',
        sourceEventId: 'event-user',
      },
      global,
    })

    expect(user.get('[aria-label="从这里分支"]').attributes('disabled')).toBeUndefined()
    expect(user.find('[aria-label="编辑并重新提交"]').exists()).toBe(true)
    expect(user.find('[aria-label="重新生成回复"]').exists()).toBe(false)
    await user.get('[aria-label="从这里分支"]').trigger('click')
    await user.get('[aria-label="编辑并重新提交"]').trigger('click')
    expect(user.emitted('branch')).toEqual([['fork'], ['edit']])

    const assistant = mount(MessageActions, {
      props: {
        content: 'answer',
        role: 'assistant',
        sourceEventId: 'event-assistant',
      },
      global,
    })
    expect(assistant.find('[aria-label="编辑并重新提交"]').exists()).toBe(false)
    await assistant.get('[aria-label="重新生成回复"]').trigger('click')
    expect(assistant.emitted('branch')).toEqual([['regenerate']])
  })

  it('keeps branch actions disabled without a persisted event or while running', () => {
    const wrapper = mount(MessageActions, {
      props: {
        content: 'pending',
        role: 'user',
        branchDisabled: true,
        branchDisabledReason: '任务执行中',
      },
      global,
    })

    expect(wrapper.get('[aria-label="从这里分支"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[aria-label="编辑并重新提交"]').attributes('disabled')).toBeDefined()
  })
})
