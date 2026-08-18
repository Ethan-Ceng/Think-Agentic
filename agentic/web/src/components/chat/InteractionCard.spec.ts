import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { InteractionEvent } from '@/lib/api/types'
import InteractionCard from './InteractionCard.vue'

const question: InteractionEvent = {
  action_id: 'action-1',
  interaction_type: 'ask_user',
  status: 'pending',
  tool_call_id: 'call-1',
  tool_name: 'message',
  function_name: 'message_ask_user',
  function_args: { text: 'Choose environment' },
  prompt: 'Choose environment',
  options: [
    { value: 'staging', label: 'Staging' },
    { value: 'production', label: 'Production' },
  ],
  allow_multiple: false,
  allow_text: false,
  selected_values: [],
}

describe('InteractionCard', () => {
  it('submits a structured option answer', async () => {
    const wrapper = mount(InteractionCard, { props: { interaction: question } })
    await wrapper.findAll('.interaction-option')[0].trigger('click')
    await wrapper.get('.interaction-button.primary').trigger('click')

    expect(wrapper.emitted('resolve')).toEqual([
      ['action-1', { decision: 'answer', selected_values: ['staging'] }],
    ])
  })

  it('renders a pending legacy approval as non-actionable retired history', () => {
    const approval: InteractionEvent = {
      ...question,
      interaction_type: 'tool_approval',
      function_name: 'deploy_release',
      function_args: { environment: 'production', api_key: 'secret-value' },
      prompt: 'Approve deployment',
      options: [],
      allow_text: false,
      risk_level: 'high',
    }
    const wrapper = mount(InteractionCard, { props: { interaction: approval } })

    expect(wrapper.text()).toContain('旧工具审批已停用')
    expect(wrapper.text()).toContain('可直接继续输入')
    expect(wrapper.text()).toContain('deploy_release')
    expect(wrapper.text()).not.toContain('production')
    expect(wrapper.text()).not.toContain('secret-value')
    expect(wrapper.find('.interaction-button').exists()).toBe(false)
    expect(wrapper.emitted('resolve')).toBeUndefined()
  })

  it('renders resolved history as read only', () => {
    const wrapper = mount(InteractionCard, {
      props: {
        interaction: {
          ...question,
          status: 'resolved',
          decision: 'answer',
          selected_values: ['production'],
        },
      },
    })

    expect(wrapper.text()).toContain('Production')
    expect(wrapper.find('.interaction-button').exists()).toBe(false)
  })
})
