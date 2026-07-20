import { describe, expect, it } from 'vitest'
import type { SSEEventData } from '@/lib/api/types'
import { eventsToTimeline } from './session-events'

describe('eventsToTimeline', () => {
  it('keeps ordinary messages visible and omits internal recovery instructions', () => {
    const events = [
      {
        type: 'message',
        data: { role: 'user', message: '最后一句用户消息' },
      },
      {
        type: 'message',
        data: {
          role: 'user',
          message: 'internal recovery instruction',
          visible: false,
        },
      },
    ] as SSEEventData[]

    const timeline = eventsToTimeline(events)
    const userMessages = timeline.filter((item) => item.kind === 'user')

    expect(userMessages).toHaveLength(1)
    expect(userMessages[0].kind === 'user' && userMessages[0].data.message).toBe('最后一句用户消息')
  })

  it('merges pending and resolved interaction events by action id', () => {
    const base = {
      action_id: 'action-1',
      interaction_type: 'ask_user' as const,
      tool_call_id: 'call-1',
      tool_name: 'message',
      function_name: 'message_ask_user',
      function_args: { text: 'Choose' },
      prompt: 'Choose',
      options: [{ value: 'staging', label: 'Staging' }],
      allow_multiple: false,
      allow_text: false,
      selected_values: [],
    }
    const events = [
      { type: 'interaction', data: { ...base, status: 'pending' } },
      {
        type: 'interaction',
        data: {
          ...base,
          status: 'resolved',
          decision: 'answer',
          selected_values: ['staging'],
        },
      },
    ] as SSEEventData[]

    const interactions = eventsToTimeline(events).filter((item) => item.kind === 'interaction')
    expect(interactions).toHaveLength(1)
    expect(interactions[0].kind === 'interaction' && interactions[0].data.status).toBe('resolved')
    expect(
      interactions[0].kind === 'interaction' && interactions[0].data.selected_values,
    ).toEqual(['staging'])
  })
})
