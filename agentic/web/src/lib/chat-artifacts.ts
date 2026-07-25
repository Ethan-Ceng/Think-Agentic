export type ArtifactView = 'source' | 'preview'
export type InlineArtifactKind = 'code' | 'markdown' | 'html'

export type InlineChatArtifact = {
  id: string
  scope: string
  index: number
  title: string
  language: string
  content: string
  kind: InlineArtifactKind
  availableViews: ArtifactView[]
}

type BuildInlineChatArtifactInput = {
  scope: string
  index: number
  info: string
  content: string
}

const LANGUAGE_ALIASES: Record<string, string> = {
  bash: 'bash',
  c: 'c',
  'c#': 'csharp',
  csharp: 'csharp',
  'c++': 'cpp',
  cpp: 'cpp',
  css: 'css',
  dart: 'dart',
  go: 'go',
  html: 'html',
  htm: 'html',
  java: 'java',
  javascript: 'javascript',
  js: 'javascript',
  json: 'json',
  jsx: 'jsx',
  kotlin: 'kotlin',
  kt: 'kotlin',
  lua: 'lua',
  markdown: 'markdown',
  md: 'markdown',
  mdown: 'markdown',
  php: 'php',
  plaintext: 'text',
  py: 'python',
  python: 'python',
  rb: 'ruby',
  ruby: 'ruby',
  rust: 'rust',
  rs: 'rust',
  sass: 'sass',
  scala: 'scala',
  scss: 'scss',
  sh: 'bash',
  shell: 'bash',
  sql: 'sql',
  swift: 'swift',
  text: 'text',
  toml: 'toml',
  ts: 'typescript',
  tsx: 'tsx',
  typescript: 'typescript',
  vue: 'vue',
  xml: 'xml',
  yaml: 'yaml',
  yml: 'yaml',
  zsh: 'bash',
}

const LANGUAGE_EXTENSIONS: Record<string, string> = {
  bash: 'sh',
  c: 'c',
  cpp: 'cpp',
  csharp: 'cs',
  css: 'css',
  dart: 'dart',
  go: 'go',
  html: 'html',
  java: 'java',
  javascript: 'js',
  json: 'json',
  jsx: 'jsx',
  kotlin: 'kt',
  lua: 'lua',
  markdown: 'md',
  php: 'php',
  python: 'py',
  ruby: 'rb',
  rust: 'rs',
  sass: 'sass',
  scala: 'scala',
  scss: 'scss',
  sql: 'sql',
  swift: 'swift',
  text: 'txt',
  toml: 'toml',
  tsx: 'tsx',
  typescript: 'ts',
  vue: 'vue',
  xml: 'xml',
  yaml: 'yaml',
}

const LANGUAGE_MIME_TYPES: Record<string, string> = {
  css: 'text/css;charset=utf-8',
  html: 'text/html;charset=utf-8',
  javascript: 'text/javascript;charset=utf-8',
  json: 'application/json;charset=utf-8',
  jsx: 'text/jsx;charset=utf-8',
  markdown: 'text/markdown;charset=utf-8',
  tsx: 'text/tsx;charset=utf-8',
  typescript: 'text/typescript;charset=utf-8',
  xml: 'application/xml;charset=utf-8',
  yaml: 'application/yaml;charset=utf-8',
}

const WINDOWS_RESERVED_NAME = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$/i

export function normalizeArtifactLanguage(info: string): string {
  const firstToken = info.trim().split(/\s+/, 1)[0]?.toLowerCase() ?? ''
  const withoutPrefix = firstToken.replace(/^language-/, '')
  return LANGUAGE_ALIASES[withoutPrefix] ?? 'text'
}

export function getArtifactFileExtension(language: string): string {
  return LANGUAGE_EXTENSIONS[language] ?? 'txt'
}

export function getArtifactMimeType(language: string): string {
  return LANGUAGE_MIME_TYPES[language] ?? 'text/plain;charset=utf-8'
}

export function sanitizeArtifactFilename(filename: string, fallback: string): string {
  const safeFallback = fallback.trim() || 'artifact.txt'
  let sanitized = filename
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '-')
    .trim()
    .replace(/[.\s]+$/g, '')

  if (!sanitized) sanitized = safeFallback
  if (WINDOWS_RESERVED_NAME.test(sanitized)) sanitized = `_${sanitized}`

  return sanitized.slice(0, 120)
}

export function buildInlineChatArtifact(
  input: BuildInlineChatArtifactInput,
): InlineChatArtifact | null {
  if (!input.content.trim()) return null

  const scope = input.scope.trim() || 'message'
  const language = normalizeArtifactLanguage(input.info)
  const extension = getArtifactFileExtension(language)
  const title = sanitizeArtifactFilename(
    `artifact-${input.index + 1}.${extension}`,
    `artifact-${input.index + 1}.txt`,
  )
  const kind: InlineArtifactKind =
    language === 'markdown' ? 'markdown' : language === 'html' ? 'html' : 'code'
  const availableViews: ArtifactView[] =
    kind === 'code' ? ['source'] : ['source', 'preview']

  return {
    id: `${scope}:fence:${input.index}`,
    scope,
    index: input.index,
    title,
    language,
    content: input.content,
    kind,
    availableViews,
  }
}

export function isClosedMarkdownFence(
  source: string,
  startLine: number,
  endLine: number,
  markup: string,
): boolean {
  if (!markup || endLine <= startLine) return false

  const lines = source.replace(/\r\n?/g, '\n').split('\n')
  const closingLine = lines[endLine - 1] ?? ''
  const marker = markup[0]
  if (marker !== '`' && marker !== '~') return false

  const escapedMarker = marker === '`' ? '\\`' : '\\~'
  const closingPattern = new RegExp(`^ {0,3}${escapedMarker}{${markup.length},}\\s*$`)
  return closingPattern.test(closingLine)
}
