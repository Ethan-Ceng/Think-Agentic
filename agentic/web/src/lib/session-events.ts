import type {
  ChatMessage,
  PlanEvent,
  PlanStep,
  SSEEventData,
  SSEEventType,
  SessionFile,
  StepEvent,
  ToolEvent,
} from '@/lib/api/types'

type RawEvent = { event?: string; type?: string; data?: unknown }

export type UserMessageStatus = 'sending' | 'sent' | 'failed' | 'stopped'

type TimelineSource = { sourceEventId?: string }

export type TimelineItem = (
  | {
      kind: 'user'
      id: string
      data: ChatMessage
      status?: UserMessageStatus
      statusText?: string
      errorText?: string
      canRetry?: boolean
      timeLabel?: string
      createdAt?: number
    }
  | { kind: 'attachments'; id: string; role: 'user' | 'assistant'; files: AttachmentFile[] }
  | { kind: 'assistant'; id: string; data: ChatMessage; timeLabel?: string; createdAt?: number }
  | { kind: 'tool'; id: string; data: ToolEvent; timeLabel?: string }
  | { kind: 'step'; id: string; data: StepEvent; tools: ToolEvent[] }
  | { kind: 'error'; id: string; error: string; timestamp?: number; timeLabel?: string }
) & TimelineSource

export type AttachmentFile = {
  id: string
  filename: string
  extension: string
  size: number
  sizeLabel?: string
}

export function normalizeEvent(raw: RawEvent): SSEEventData | null {
  const type = (raw.type ?? raw.event) as SSEEventType | undefined
  const data = raw.data
  if (!type || data === undefined) return null
  return { type, data } as SSEEventData
}

export function normalizeEvents(rawList: unknown): SSEEventData[] {
  if (!Array.isArray(rawList)) return []
  const out: SSEEventData[] = []
  for (const raw of rawList) {
    const normalized = normalizeEvent(raw as RawEvent)
    if (normalized) out.push(normalized)
  }
  return out
}

export function sessionFileToAttachment(file: SessionFile): AttachmentFile {
  return {
    id: file.id,
    filename: file.filename,
    extension: file.extension,
    size: file.size,
  }
}

export function chatAttachmentToDisplay(
  attachment: {
    file_id?: string
    id?: string
    filename: string
    size?: number
    [key: string]: unknown
  },
): AttachmentFile {
  const ext = (attachment.filename || '').split('.').pop() || ''
  return {
    id: attachment.file_id || attachment.id || '',
    filename: attachment.filename || '',
    extension: ext,
    size: typeof attachment.size === 'number' ? attachment.size : 0,
  }
}

function stableId(prefix: string, index: number, suffix: string): string {
  return `${prefix}-${index}-${suffix}`
}

function formatTimeLabel(ts: number | string | undefined): string | undefined {
  if (ts === undefined || ts === null) return undefined
  let t = typeof ts === 'string' ? Number.parseInt(ts, 10) : ts
  if (Number.isNaN(t)) return undefined

  if (t < 10000000000) {
    t *= 1000
  }

  const diff = Date.now() - t
  if (diff < 0 || diff < 60 * 1000) return '刚刚'
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / (60 * 1000))} 分钟前`
  if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / (60 * 60 * 1000))} 小时前`
  if (diff < 2 * 24 * 60 * 60 * 1000) return '昨天'
  if (diff < 7 * 24 * 60 * 60 * 1000) return `${Math.floor(diff / (24 * 60 * 60 * 1000))} 天前`
  if (diff < 30 * 24 * 60 * 60 * 1000) return `${Math.floor(diff / (7 * 24 * 60 * 60 * 1000))} 周前`
  return undefined
}

function normalizeTimestamp(ts: number | string | undefined): number | undefined {
  if (ts === undefined || ts === null) return undefined

  let t = typeof ts === 'string' ? Number.parseInt(ts, 10) : ts
  if (Number.isNaN(t)) return undefined

  if (t < 10000000000) {
    t *= 1000
  }

  return t
}

export function formatMessageTimeLabel(ts: number | string | undefined): string | undefined {
  const normalized = normalizeTimestamp(ts)
  if (normalized === undefined) return undefined

  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return undefined

  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()

  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  if (sameDay) return `${hour}:${minute}`

  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${month}/${day} ${hour}:${minute}`
}

export function getToolTimeLabel(tool: ToolEvent): string | undefined {
  const ts =
    (tool as { timestamp?: number }).timestamp ??
    (tool as { created_at?: number }).created_at ??
    (tool as { ts?: number }).ts
  return formatTimeLabel(ts)
}

function getEventCreatedAt(data: unknown): number | string | undefined {
  return (data as { created_at?: number | string })?.created_at
}

export function eventsToTimeline(events: SSEEventData[]): TimelineItem[] {
  const list: TimelineItem[] = []
  let lastStepId: string | null = null
  let messageIndex = 0
  let toolIndex = 0
  let stepIndex = 0
  let errorIndex = 0

  for (const ev of events) {
    switch (ev.type) {
      case 'message': {
        const msg = ev.data as ChatMessage
        const sourceEventId = (msg as { event_id?: string }).event_id
        const createdAt = normalizeTimestamp(getEventCreatedAt(msg))
        if (msg.role === 'user') {
          lastStepId = null
          list.push({
            kind: 'user',
            id: stableId('user', messageIndex++, String(list.length)),
            data: msg,
            status: 'sent',
            statusText: '已发送',
            timeLabel: formatMessageTimeLabel(getEventCreatedAt(msg)),
            createdAt,
            sourceEventId,
          })
          if (msg.attachments?.length) {
            list.push({
              kind: 'attachments',
              id: stableId('att', messageIndex, 'user'),
              role: 'user',
              files: msg.attachments.map(chatAttachmentToDisplay),
            })
          }
        } else if (msg.role === 'assistant') {
          list.push({
            kind: 'assistant',
            id: stableId('assistant', messageIndex++, String(list.length)),
            data: msg,
            timeLabel: formatMessageTimeLabel(getEventCreatedAt(msg)),
            createdAt,
            sourceEventId,
          })
          if (msg.attachments?.length) {
            list.push({
              kind: 'attachments',
              id: stableId('att', messageIndex, 'assistant'),
              role: 'assistant',
              files: msg.attachments.map(chatAttachmentToDisplay),
            })
          }
        }
        break
      }
      case 'step': {
        const step = ev.data as StepEvent
        const sourceEventId = (step as { event_id?: string }).event_id

        if (lastStepId !== null && lastStepId === step.id) {
          let existingIdx = -1
          for (let i = list.length - 1; i >= 0; i--) {
            const item = list[i]
            if (item.kind === 'step' && item.data.id === step.id) {
              existingIdx = i
              break
            }
          }

          if (existingIdx >= 0) {
            const existing = list[existingIdx]
            if (existing.kind === 'step') {
              list[existingIdx] = {
                kind: 'step',
                id: existing.id,
                data: step,
                tools: existing.tools,
                sourceEventId: sourceEventId || existing.sourceEventId,
              }
            }
          }
        } else {
          list.push({
            kind: 'step',
            id: stableId('step', stepIndex++, `${step.id}_${String(list.length)}`),
            data: step,
            tools: [],
            sourceEventId,
          })
        }

        lastStepId = step.status === 'completed' || step.status === 'failed' ? null : step.id
        break
      }
      case 'tool': {
        const tool = ev.data as ToolEvent
        const toolCallId = (tool as { tool_call_id?: string }).tool_call_id

        if (lastStepId !== null) {
          let stepIdx = -1
          for (let i = list.length - 1; i >= 0; i--) {
            const item = list[i]
            if (item.kind === 'step' && item.data.id === lastStepId) {
              stepIdx = i
              break
            }
          }

          if (stepIdx >= 0) {
            const step = list[stepIdx]
            if (step.kind === 'step') {
              if (toolCallId != null) {
                const existingToolIdx = step.tools.findIndex(
                  (t) => (t as { tool_call_id?: string }).tool_call_id === toolCallId,
                )
                if (existingToolIdx >= 0) {
                  const newTools = [...step.tools]
                  newTools[existingToolIdx] = tool
                  list[stepIdx] = { ...step, tools: newTools }
                  break
                }
              }
              list[stepIdx] = { ...step, tools: [...step.tools, tool] }
            }
          }
        } else {
          if (toolCallId != null) {
            const last = list[list.length - 1]
            if (
              last?.kind === 'tool' &&
              (last.data as { tool_call_id?: string }).tool_call_id === toolCallId
            ) {
              list[list.length - 1] = { ...last, data: tool }
              break
            }
          }

          list.push({
            kind: 'tool',
            id: stableId('tool', toolIndex++, `${tool.name || ''}${tool.function || ''}`),
            data: tool,
            timeLabel: getToolTimeLabel(tool),
            sourceEventId: (tool as { event_id?: string }).event_id,
          })
        }
        break
      }
      case 'error': {
        const errorData = ev.data as {
          error?: string
          created_at?: number
          [key: string]: unknown
        }
        if (errorData.error) {
          list.push({
            kind: 'error',
            id: stableId('error', errorIndex++, String(list.length)),
            error: errorData.error,
            timestamp: errorData.created_at,
            timeLabel: formatMessageTimeLabel(errorData.created_at),
            sourceEventId: (errorData as { event_id?: string }).event_id,
          })
        }
        break
      }
      case 'title':
      case 'plan':
      case 'wait':
      case 'done':
        break
      default:
        break
    }
  }

  return list
}

export function getLatestPlanFromEvents(events: SSEEventData[]): PlanStep[] {
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i]
    if (ev.type === 'plan') {
      const plan = ev.data as PlanEvent
      if (Array.isArray(plan.steps)) {
        return plan.steps
      }
      break
    }
  }
  return []
}
