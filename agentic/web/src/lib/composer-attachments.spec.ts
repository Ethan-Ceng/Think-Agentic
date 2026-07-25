import { describe, expect, it } from 'vitest'
import type { FileInfo, ManagedFile } from '@/lib/api/types'
import {
  completeComposerUpload,
  createLocalComposerAttachment,
  createLibraryComposerAttachment,
  isPreviewableComposerImage,
  mergeLibraryComposerAttachments,
  toComposerAttachmentMetadata,
  toFilePickerSelection,
} from './composer-attachments'

function managedFile(overrides: Partial<ManagedFile> = {}): ManagedFile {
  return {
    id: 'file-1',
    parent_id: null,
    type: 'file',
    name: 'diagram.PNG',
    filename: 'diagram.PNG',
    extension: '.PNG',
    mime_type: 'image/png',
    storage_provider: 'local',
    source_type: 'user_upload',
    status: 'available',
    size: 128,
    preview_url: '/api/files/file-1/preview?token=secret',
    download_url: '/api/files/file-1/download?token=secret',
    created_at: 1,
    updated_at: 2,
    ...overrides,
  }
}

describe('composer attachments', () => {
  it('normalizes a local file into a narrow uploading view model', () => {
    const file = new File(['image'], ' Photo.PNG ', { type: 'image/png' })

    expect(createLocalComposerAttachment(file, 'local-1')).toEqual({
      id: 'local-1',
      filename: 'Photo.PNG',
      extension: 'png',
      size: 5,
      contentType: 'image/png',
      origin: 'upload',
      uploadStatus: 'uploading',
      progress: 20,
    })
  })

  it('completes an upload without exposing storage fields', () => {
    const local = createLocalComposerAttachment(
      new File(['report'], 'draft.txt', { type: 'text/plain' }),
      'local-2',
    )
    const uploaded = {
      id: 'persisted-2',
      filename: 'report.txt',
      filepath: '/private/user/report.txt',
      key: 'user/secret/report.txt',
      extension: '.TXT',
      content_type: 'text/plain',
      size: 6,
      preview_url: 'https://signed.example/preview',
      download_url: 'https://signed.example/download',
    } as FileInfo

    expect(completeComposerUpload(local, uploaded)).toEqual({
      id: 'persisted-2',
      filename: 'report.txt',
      extension: 'txt',
      size: 6,
      contentType: 'text/plain',
      origin: 'upload',
      uploadStatus: 'uploaded',
      progress: 100,
    })
    expect(toComposerAttachmentMetadata(uploaded)).toEqual({
      id: 'persisted-2',
      filename: 'report.txt',
      extension: 'txt',
      size: 6,
      contentType: 'text/plain',
    })
  })

  it('projects an available file into an exact picker whitelist', () => {
    const selection = toFilePickerSelection(managedFile())

    expect(selection).toEqual({
      id: 'file-1',
      filename: 'diagram.PNG',
      extension: 'png',
      size: 128,
      mimeType: 'image/png',
      sourceType: 'user_upload',
    })
    expect(JSON.stringify(selection)).not.toContain('secret')
    expect(toFilePickerSelection(managedFile({ type: 'folder' }))).toBeNull()
    expect(toFilePickerSelection(managedFile({ status: 'deleted' }))).toBeNull()
  })

  it('creates uploaded library items and deduplicates persistent ids in stable order', () => {
    const first = createLibraryComposerAttachment(
      toFilePickerSelection(managedFile())!,
    )
    const secondSelection = toFilePickerSelection(
      managedFile({
        id: 'file-2',
        name: 'notes.md',
        filename: 'notes.md',
        extension: 'md',
        mime_type: 'text/markdown',
        size: 64,
      }),
    )!

    expect(first).toEqual({
      id: 'file-1',
      filename: 'diagram.PNG',
      extension: 'png',
      size: 128,
      contentType: 'image/png',
      origin: 'library',
      uploadStatus: 'uploaded',
      progress: 100,
    })
    expect(
      mergeLibraryComposerAttachments(
        [
          first,
          {
            ...first,
            id: 'local-1',
            origin: 'upload',
          },
        ],
        [toFilePickerSelection(managedFile())!, secondSelection, secondSelection],
      ).map((item) => item.id),
    ).toEqual(['file-1', 'local-1', 'file-2'])
  })

  it('only treats matching browser-safe raster mime and extension pairs as previewable', () => {
    const image = createLibraryComposerAttachment(
      toFilePickerSelection(managedFile())!,
    )

    expect(isPreviewableComposerImage(image)).toBe(true)
    expect(isPreviewableComposerImage({ ...image, extension: 'txt' })).toBe(false)
    expect(isPreviewableComposerImage({ ...image, contentType: 'text/plain' })).toBe(false)
    expect(
      isPreviewableComposerImage({
        ...image,
        filename: 'unsafe.svg',
        extension: 'svg',
        contentType: 'image/svg+xml',
      }),
    ).toBe(false)
    expect(
      isPreviewableComposerImage({
        ...image,
        filename: 'photo.avif',
        extension: 'avif',
        contentType: 'image/avif',
      }),
    ).toBe(true)
  })
})
