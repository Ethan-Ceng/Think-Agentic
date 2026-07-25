import { describe, expect, it } from 'vitest'
import {
  buildInlineChatArtifact,
  isClosedMarkdownFence,
  normalizeArtifactLanguage,
  sanitizeArtifactFilename,
} from './chat-artifacts'

describe('chat artifacts', () => {
  it('normalizes supported language aliases conservatively', () => {
    expect(normalizeArtifactLanguage('MD preview')).toBe('markdown')
    expect(normalizeArtifactLanguage('language-HTM')).toBe('html')
    expect(normalizeArtifactLanguage('js title=demo')).toBe('javascript')
    expect(normalizeArtifactLanguage('C++')).toBe('cpp')
    expect(normalizeArtifactLanguage('unknown/runtime')).toBe('text')
    expect(normalizeArtifactLanguage('')).toBe('text')
  })

  it('builds stable read-only artifacts with constrained views and filenames', () => {
    const markdown = buildInlineChatArtifact({
      scope: 'message-42',
      index: 1,
      info: 'md',
      content: '# Report\n',
    })
    const code = buildInlineChatArtifact({
      scope: 'message-42',
      index: 2,
      info: 'ts',
      content: 'const value = 1\n',
    })

    expect(markdown).toEqual({
      id: 'message-42:fence:1',
      scope: 'message-42',
      index: 1,
      title: 'artifact-2.md',
      language: 'markdown',
      content: '# Report\n',
      kind: 'markdown',
      availableViews: ['source', 'preview'],
    })
    expect(code).toMatchObject({
      id: 'message-42:fence:2',
      title: 'artifact-3.ts',
      language: 'typescript',
      kind: 'code',
      availableViews: ['source'],
    })
    expect(buildInlineChatArtifact({
      scope: 'message-42',
      index: 3,
      info: 'html',
      content: '   \n',
    })).toBeNull()
  })

  it('sanitizes unsafe and reserved filenames without accepting path segments', () => {
    expect(sanitizeArtifactFilename('../CON?.html', 'artifact.html')).toBe('..-CON-.html')
    expect(sanitizeArtifactFilename('LPT1', 'artifact.txt')).toBe('_LPT1')
    expect(sanitizeArtifactFilename('  report\u0000 / final.md.  ', 'artifact.md')).toBe(
      'report- - final.md',
    )
    expect(sanitizeArtifactFilename('', 'artifact.txt')).toBe('artifact.txt')
  })

  it('distinguishes closed fences from streaming partial fences', () => {
    expect(isClosedMarkdownFence('```ts\nconst value = 1\n```\n', 0, 3, '```')).toBe(true)
    expect(isClosedMarkdownFence('~~~md\n# Title\n~~~~\n', 0, 3, '~~~')).toBe(true)
    expect(isClosedMarkdownFence('```ts\nconst value = 1\n', 0, 2, '```')).toBe(false)
    expect(isClosedMarkdownFence('```ts\nconst value = 1\n    ```\n', 0, 3, '```')).toBe(false)
  })
})
