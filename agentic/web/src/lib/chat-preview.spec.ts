import { describe, expect, it } from 'vitest'
import type { ToolEvent } from '@/lib/api/types'
import type { ChatPreviewSelection } from './chat-preview'
import { canAutoFollowTool } from './chat-preview'

const tool: ToolEvent = {
  tool_call_id: 'tool-1',
  name: 'shell_execute',
  function: 'shell_execute',
  status: 'called',
  args: {},
  content: {},
}

describe('chat preview selection', () => {
  it('allows automatic following only for empty or existing auto-tool selections', () => {
    expect(canAutoFollowTool(null)).toBe(true)
    expect(canAutoFollowTool({
      kind: 'tool',
      source: 'auto',
      tool,
    } as ChatPreviewSelection)).toBe(true)

    const pinnedSelections: ChatPreviewSelection[] = [
      { kind: 'tool', source: 'user', tool },
      {
        kind: 'file',
        source: 'user',
        file: {
          id: 'file-1',
          filename: 'report.md',
          extension: 'md',
          size: 100,
        },
      },
      {
        kind: 'artifact',
        source: 'user',
        artifact: {
          id: 'message-1:fence:0',
          scope: 'message-1',
          index: 0,
          title: 'artifact-1.html',
          language: 'html',
          content: '<main />',
          kind: 'html',
          availableViews: ['source', 'preview'],
        },
      },
      { kind: 'trace', source: 'user' },
    ]

    for (const selection of pinnedSelections) {
      expect(canAutoFollowTool(selection)).toBe(false)
    }
  })
})
