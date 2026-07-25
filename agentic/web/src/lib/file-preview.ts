import type { ArtifactView } from './chat-artifacts'

export type FilePreviewKind =
  | 'markdown'
  | 'html'
  | 'svg'
  | 'image'
  | 'text'
  | 'unsupported'

export type FilePreviewDescriptor = {
  extension: string
  kind: FilePreviewKind
  availableViews: ArtifactView[]
  defaultView: ArtifactView | null
}

const MARKDOWN_EXTENSIONS = new Set(['md', 'markdown'])
const HTML_EXTENSIONS = new Set(['html', 'htm'])
const RASTER_IMAGE_EXTENSIONS = new Set([
  'jpg',
  'jpeg',
  'png',
  'gif',
  'webp',
  'bmp',
  'ico',
])
const TEXT_EXTENSIONS = new Set([
  'txt',
  'json',
  'xml',
  'css',
  'scss',
  'sass',
  'less',
  'js',
  'jsx',
  'ts',
  'tsx',
  'vue',
  'py',
  'java',
  'go',
  'rs',
  'c',
  'cpp',
  'h',
  'hpp',
  'cs',
  'php',
  'rb',
  'swift',
  'kt',
  'scala',
  'sh',
  'bash',
  'zsh',
  'yml',
  'yaml',
  'toml',
  'ini',
  'conf',
  'config',
  'log',
  'csv',
  'sql',
  'r',
  'dart',
  'lua',
  'perl',
])

function normalizeExtension(extension: string, filename: string): string {
  const explicit = extension.trim().toLowerCase().replace(/^\.+/, '')
  if (explicit) return explicit

  const separator = filename.lastIndexOf('.')
  if (separator < 0 || separator === filename.length - 1) return ''
  return filename.slice(separator + 1).trim().toLowerCase()
}

export function getFilePreviewDescriptor(
  extension: string,
  filename: string,
): FilePreviewDescriptor {
  const normalizedExtension = normalizeExtension(extension, filename)

  if (MARKDOWN_EXTENSIONS.has(normalizedExtension)) {
    return {
      extension: normalizedExtension,
      kind: 'markdown',
      availableViews: ['source', 'preview'],
      defaultView: 'preview',
    }
  }

  if (HTML_EXTENSIONS.has(normalizedExtension)) {
    return {
      extension: normalizedExtension,
      kind: 'html',
      availableViews: ['source', 'preview'],
      defaultView: 'preview',
    }
  }

  if (normalizedExtension === 'svg') {
    return {
      extension: normalizedExtension,
      kind: 'svg',
      availableViews: ['source', 'preview'],
      defaultView: 'preview',
    }
  }

  if (RASTER_IMAGE_EXTENSIONS.has(normalizedExtension)) {
    return {
      extension: normalizedExtension,
      kind: 'image',
      availableViews: ['preview'],
      defaultView: 'preview',
    }
  }

  if (TEXT_EXTENSIONS.has(normalizedExtension)) {
    return {
      extension: normalizedExtension,
      kind: 'text',
      availableViews: ['source'],
      defaultView: 'source',
    }
  }

  return {
    extension: normalizedExtension,
    kind: 'unsupported',
    availableViews: [],
    defaultView: null,
  }
}
