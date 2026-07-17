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
})
