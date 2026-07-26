import { describe, expect, it } from 'vitest'
import {
  decodeInitialSessionMessage,
  encodeInitialSessionMessage,
} from './session-init'

describe('initial session message attachments', () => {
  it('preserves attachment IDs and skills through the home-to-session handoff', () => {
    const encoded = encodeInitialSessionMessage({
      message: 'analyze these files',
      attachmentIds: ['upload-1', 'library-1'],
      skills: [{
        source: 'personal',
        skill_id: 'skill-1',
        name: 'summarizer',
      }],
    })

    expect(decodeInitialSessionMessage(encoded)).toEqual({
      message: 'analyze these files',
      attachments: ['upload-1', 'library-1'],
      skills: [{
        source: 'personal',
        skill_id: 'skill-1',
        name: 'summarizer',
      }],
      hasInitialMessage: true,
    })
  })

  it('uses empty attachment and skill lists for an empty handoff', () => {
    expect(decodeInitialSessionMessage('')).toEqual({
      attachments: [],
      skills: [],
      hasInitialMessage: false,
    })
  })
})
