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

  it('builds one assistant draft from ordered message deltas', () => {
    const events = [
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 0,
          operation: 'append',
          delta: '你好，',
        },
      },
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 1,
          operation: 'append',
          delta: '**世界**',
        },
      },
    ] as unknown as SSEEventData[]

    const assistants = eventsToTimeline(events).filter(
      (item) => item.kind === 'assistant',
    )

    expect(assistants).toHaveLength(1)
    expect(assistants[0]).toMatchObject({
      kind: 'assistant',
      id: 'assistant-stream-stream-1',
      streaming: true,
      streamId: 'stream-1',
      data: { role: 'assistant', message: '你好，**世界**' },
    })
  })

  it('applies reset and abort operations to the existing draft in place', () => {
    const resetEvents = [
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 0,
          operation: 'append',
          delta: 'discard me',
        },
      },
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 1,
          operation: 'reset',
          delta: '',
        },
      },
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 2,
          operation: 'append',
          delta: 'replacement',
        },
      },
    ] as unknown as SSEEventData[]

    const resetTimeline = eventsToTimeline(resetEvents)
    expect(resetTimeline).toHaveLength(1)
    expect(
      resetTimeline[0].kind === 'assistant' && resetTimeline[0].data.message,
    ).toBe('replacement')

    const aborted = eventsToTimeline([
      ...resetEvents,
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 3,
          operation: 'abort',
          delta: '',
        },
      },
    ] as unknown as SSEEventData[])
    expect(aborted.filter((item) => item.kind === 'assistant')).toHaveLength(0)
  })

  it('replaces a matching draft with the authoritative final message', () => {
    const events = [
      {
        type: 'message',
        data: { role: 'user', message: 'question', event_id: 'user-1' },
      },
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 0,
          operation: 'append',
          delta: 'partial',
        },
      },
      {
        type: 'tool',
        data: { name: 'search', function: 'search', args: {} },
      },
      {
        type: 'message',
        data: {
          role: 'assistant',
          message: 'final answer',
          stream_id: 'stream-1',
          event_id: 'assistant-final-1',
        },
      },
    ] as unknown as SSEEventData[]

    const timeline = eventsToTimeline(events)
    const assistants = timeline.filter((item) => item.kind === 'assistant')

    expect(assistants).toHaveLength(1)
    expect(assistants[0]).toMatchObject({
      kind: 'assistant',
      id: 'assistant-stream-stream-1',
      streaming: false,
      streamId: 'stream-1',
      sourceEventId: 'assistant-final-1',
      data: { message: 'final answer' },
    })
    expect(timeline.map((item) => item.kind)).toEqual(['user', 'assistant', 'tool'])
  })

  it('ignores duplicate and out-of-order delta sequences', () => {
    const events = [
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 0,
          operation: 'append',
          delta: 'A',
        },
      },
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 0,
          operation: 'append',
          delta: 'duplicate',
        },
      },
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 2,
          operation: 'append',
          delta: 'C',
        },
      },
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-1',
          sequence: 1,
          operation: 'append',
          delta: 'late',
        },
      },
    ] as unknown as SSEEventData[]

    const assistant = eventsToTimeline(events).find(
      (item) => item.kind === 'assistant',
    )
    expect(assistant?.kind === 'assistant' && assistant.data.message).toBe('AC')
  })

  it('keeps final-only assistant messages compatible without a draft', () => {
    const timeline = eventsToTimeline([
      {
        type: 'message',
        data: {
          role: 'assistant',
          message: 'fallback answer',
          stream_id: 'stream-1',
          event_id: 'assistant-final-1',
        },
      },
    ] as SSEEventData[])

    expect(timeline).toHaveLength(1)
    expect(timeline[0]).toMatchObject({
      kind: 'assistant',
      streaming: false,
      streamId: 'stream-1',
      sourceEventId: 'assistant-final-1',
      data: { message: 'fallback answer' },
    })
  })

  it('treats final and abort as terminal for later deltas of the same stream', () => {
    const finalized = eventsToTimeline([
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-final',
          sequence: 0,
          operation: 'append',
          delta: 'draft',
        },
      },
      {
        type: 'message',
        data: {
          role: 'assistant',
          message: 'authoritative',
          stream_id: 'stream-final',
        },
      },
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-final',
          sequence: 1,
          operation: 'append',
          delta: 'must be ignored',
        },
      },
    ] as unknown as SSEEventData[])
    const finalAssistant = finalized.find((item) => item.kind === 'assistant')
    expect(finalAssistant).toMatchObject({
      kind: 'assistant',
      streaming: false,
      data: { message: 'authoritative' },
    })

    const aborted = eventsToTimeline([
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-abort',
          sequence: 0,
          operation: 'append',
          delta: 'draft',
        },
      },
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-abort',
          sequence: 1,
          operation: 'abort',
          delta: '',
        },
      },
      {
        type: 'message_delta',
        data: {
          role: 'assistant',
          stream_id: 'stream-abort',
          sequence: 2,
          operation: 'append',
          delta: 'must not revive',
        },
      },
    ] as unknown as SSEEventData[])
    expect(aborted.filter((item) => item.kind === 'assistant')).toHaveLength(0)
  })
})
