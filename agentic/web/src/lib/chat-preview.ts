import type { ToolEvent } from '@/lib/api/types'
import type { InlineChatArtifact } from '@/lib/chat-artifacts'
import type { AttachmentFile } from '@/lib/session-events'

export type ChatPreviewSelection =
  | { kind: 'file'; source: 'user'; file: AttachmentFile }
  | { kind: 'tool'; source: 'user' | 'auto'; tool: ToolEvent }
  | { kind: 'artifact'; source: 'user'; artifact: InlineChatArtifact }
  | { kind: 'trace'; source: 'user' }

export function canAutoFollowTool(selection: ChatPreviewSelection | null): boolean {
  return selection === null || (selection.kind === 'tool' && selection.source === 'auto')
}
