import type { FileInfo, ManagedFile } from '@/lib/api/types'

export type ComposerAttachmentOrigin = 'upload' | 'library'
export type ComposerAttachmentStatus = 'uploading' | 'uploaded' | 'failed'

export type ComposerAttachmentMetadata = {
  id: string
  filename: string
  extension: string
  size: number
  contentType: string
}

export type ComposerAttachmentFile = ComposerAttachmentMetadata & {
  origin: ComposerAttachmentOrigin
  uploadStatus: ComposerAttachmentStatus
  uploadError?: string
  progress?: number
  previewUrl?: string
}

export type FilePickerSelection = {
  id: string
  filename: string
  extension: string
  size: number
  mimeType: string
  sourceType: ManagedFile['source_type']
}

const PREVIEWABLE_RASTER_TYPES: Readonly<Record<string, ReadonlySet<string>>> = {
  'image/avif': new Set(['avif']),
  'image/gif': new Set(['gif']),
  'image/jpeg': new Set(['jpg', 'jpeg', 'jfif']),
  'image/png': new Set(['png']),
  'image/webp': new Set(['webp']),
}

function normalizeFilename(filename: string | undefined): string {
  return filename?.trim() || '未命名文件'
}

function normalizeSize(size: number | undefined): number {
  return typeof size === 'number' && Number.isFinite(size) && size >= 0 ? size : 0
}

function normalizeContentType(contentType: string | undefined): string {
  return contentType?.trim().toLowerCase() || ''
}

export function normalizeComposerExtension(
  extension: string | undefined,
  filename: string,
): string {
  const filenameExtension = filename.includes('.') ? filename.split('.').pop() : ''
  const value = (extension || filenameExtension || '')
    .trim()
    .replace(/^\.+/, '')
    .toLowerCase()

  return /^[a-z0-9][a-z0-9+_-]{0,15}$/.test(value) ? value : ''
}

export function createLocalComposerAttachment(
  file: File,
  localId: string,
): ComposerAttachmentFile {
  const filename = normalizeFilename(file.name)
  return {
    id: localId,
    filename,
    extension: normalizeComposerExtension(undefined, filename),
    size: normalizeSize(file.size),
    contentType: normalizeContentType(file.type),
    origin: 'upload',
    uploadStatus: 'uploading',
    progress: 20,
  }
}

export function toComposerAttachmentMetadata(file: FileInfo): ComposerAttachmentMetadata {
  const filename = normalizeFilename(file.filename || file.name)
  return {
    id: file.id,
    filename,
    extension: normalizeComposerExtension(file.extension, filename),
    size: normalizeSize(file.size),
    contentType: normalizeContentType(file.content_type || file.mime_type),
  }
}

export function completeComposerUpload(
  current: ComposerAttachmentFile,
  uploaded: FileInfo,
): ComposerAttachmentFile {
  const metadata = toComposerAttachmentMetadata(uploaded)
  return {
    ...metadata,
    origin: 'upload',
    uploadStatus: 'uploaded',
    progress: 100,
    ...(current.previewUrl ? { previewUrl: current.previewUrl } : {}),
  }
}

export function toFilePickerSelection(file: ManagedFile): FilePickerSelection | null {
  if (file.type !== 'file' || file.status !== 'available') return null

  const filename = normalizeFilename(file.filename || file.name)
  return {
    id: file.id,
    filename,
    extension: normalizeComposerExtension(file.extension, filename),
    size: normalizeSize(file.size),
    mimeType: normalizeContentType(file.mime_type),
    sourceType: file.source_type,
  }
}

export function createLibraryComposerAttachment(
  file: FilePickerSelection,
): ComposerAttachmentFile {
  const filename = normalizeFilename(file.filename)
  return {
    id: file.id,
    filename,
    extension: normalizeComposerExtension(file.extension, filename),
    size: normalizeSize(file.size),
    contentType: normalizeContentType(file.mimeType),
    origin: 'library',
    uploadStatus: 'uploaded',
    progress: 100,
  }
}

export function mergeLibraryComposerAttachments(
  current: readonly ComposerAttachmentFile[],
  selected: readonly FilePickerSelection[],
): ComposerAttachmentFile[] {
  const merged = [...current]
  const ids = new Set(current.map((file) => file.id))

  for (const selection of selected) {
    if (ids.has(selection.id)) continue
    ids.add(selection.id)
    merged.push(createLibraryComposerAttachment(selection))
  }

  return merged
}

export function isPreviewableComposerImage(file: ComposerAttachmentMetadata): boolean {
  const extensions = PREVIEWABLE_RASTER_TYPES[normalizeContentType(file.contentType)]
  if (!extensions) return false
  return extensions.has(normalizeComposerExtension(file.extension, file.filename))
}
