import type { SendMessageInput, SkillRef } from '@/types/skill'

export type InitialSessionMessage = {
  message?: string
  attachments: string[]
  skills: SkillRef[]
  hasInitialMessage: boolean
}

export function encodeInitialSessionMessage(input: SendMessageInput): string {
  const payload = JSON.stringify({
    message: input.message,
    attachments: input.attachmentIds,
    skills: input.skills,
  })
  return btoa(encodeURIComponent(payload))
}

export function decodeInitialSessionMessage(value: string): InitialSessionMessage {
  if (!value) return { attachments: [], skills: [], hasInitialMessage: false }
  const parsed = JSON.parse(decodeURIComponent(atob(value))) as {
    message?: string
    attachments?: string[]
    skills?: SkillRef[]
  }
  return {
    message: parsed.message,
    attachments: Array.isArray(parsed.attachments) ? parsed.attachments : [],
    skills: Array.isArray(parsed.skills) ? parsed.skills : [],
    hasInitialMessage: Boolean(parsed.message),
  }
}
