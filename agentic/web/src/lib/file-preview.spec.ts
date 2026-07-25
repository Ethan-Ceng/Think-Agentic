import { describe, expect, it } from 'vitest'
import { getFilePreviewDescriptor } from './file-preview'

describe('file preview descriptors', () => {
  it('classifies safe dual-view documents', () => {
    expect(getFilePreviewDescriptor('.MD', 'report.MD')).toEqual({
      extension: 'md',
      kind: 'markdown',
      availableViews: ['source', 'preview'],
      defaultView: 'preview',
    })
    expect(getFilePreviewDescriptor('', 'page.HTM')).toMatchObject({
      extension: 'htm',
      kind: 'html',
      availableViews: ['source', 'preview'],
    })
    expect(getFilePreviewDescriptor('svg', 'diagram.svg')).toMatchObject({
      kind: 'svg',
      availableViews: ['source', 'preview'],
    })
  })

  it('keeps raster images preview-only and code or text source-only', () => {
    expect(getFilePreviewDescriptor('PNG', 'image.png')).toMatchObject({
      kind: 'image',
      availableViews: ['preview'],
      defaultView: 'preview',
    })
    expect(getFilePreviewDescriptor('ts', 'source.ts')).toMatchObject({
      kind: 'text',
      availableViews: ['source'],
      defaultView: 'source',
    })
    expect(getFilePreviewDescriptor('txt', 'notes.txt')).toMatchObject({
      kind: 'text',
      availableViews: ['source'],
    })
  })

  it('falls back conservatively for unknown or missing extensions', () => {
    expect(getFilePreviewDescriptor('exe', 'tool.exe')).toMatchObject({
      kind: 'unsupported',
      availableViews: [],
      defaultView: null,
    })
    expect(getFilePreviewDescriptor('', 'README')).toMatchObject({
      extension: '',
      kind: 'unsupported',
    })
  })
})
