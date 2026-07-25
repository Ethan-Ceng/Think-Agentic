<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'
import { useToast } from '@/composables/useToast'
import {
  buildInlineChatArtifact,
  getArtifactMimeType,
  isClosedMarkdownFence,
  type InlineChatArtifact,
} from '@/lib/chat-artifacts'
import { downloadBlob } from '@/lib/utils'

const props = withDefaults(defineProps<{
  content: string
  artifactScope?: string
  enableArtifacts?: boolean
}>(), {
  artifactScope: 'message',
  enableArtifacts: false,
})

const emit = defineEmits<{
  artifactOpen: [artifact: InlineChatArtifact]
}>()

const toast = useToast()

const CJK_RANGES = '\\u3000-\\u303F\\u4E00-\\u9FFF\\uFF01-\\uFF60'
const URL_FOLLOWED_BY_CJK = new RegExp(
  `(https?:\\/\\/[^\\s${CJK_RANGES}]+)([${CJK_RANGES}])`,
  'g',
)

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

type ArtifactRenderEnvironment = {
  artifacts: Map<string, InlineChatArtifact>
  enableArtifacts: boolean
  nextFenceIndex: number
  scope: string
  source: string
}

const defaultFenceRenderer = md.renderer.rules.fence
let renderedArtifacts = new Map<string, InlineChatArtifact>()

md.renderer.rules.fence = (tokens, index, options, env, self) => {
  const renderEnvironment = env as ArtifactRenderEnvironment | undefined
  const token = tokens[index]
  const renderDefault = () => {
    if (defaultFenceRenderer) {
      return defaultFenceRenderer(tokens, index, options, env, self)
    }
    return self.renderToken(tokens, index, options)
  }

  if (!renderEnvironment?.enableArtifacts || token.type !== 'fence' || !token.map) {
    return renderDefault()
  }

  const fenceIndex = renderEnvironment.nextFenceIndex
  renderEnvironment.nextFenceIndex += 1
  const [startLine, endLine] = token.map
  if (
    !isClosedMarkdownFence(
      renderEnvironment.source,
      startLine,
      endLine,
      token.markup,
    )
  ) {
    return renderDefault()
  }

  const artifact = buildInlineChatArtifact({
    scope: renderEnvironment.scope,
    index: fenceIndex,
    info: token.info,
    content: token.content,
  })
  if (!artifact) return renderDefault()

  renderEnvironment.artifacts.set(artifact.id, artifact)
  const artifactId = md.utils.escapeHtml(artifact.id)
  const title = md.utils.escapeHtml(artifact.title)
  const language = md.utils.escapeHtml(artifact.language)
  const content = md.utils.escapeHtml(artifact.content)

  return [
    `<section class="markdown-artifact" data-artifact-id="${artifactId}">`,
    '<header class="markdown-artifact-header">',
    `<span class="markdown-artifact-language">${language}</span>`,
    '<span class="markdown-artifact-actions">',
    `<button type="button" data-artifact-action="copy" data-artifact-id="${artifactId}" aria-label="复制 ${title}">复制</button>`,
    `<button type="button" data-artifact-action="download" data-artifact-id="${artifactId}" aria-label="下载 ${title}">下载</button>`,
    `<button type="button" data-artifact-action="open" data-artifact-id="${artifactId}" aria-label="在侧栏打开 ${title}">打开</button>`,
    '</span>',
    '</header>',
    `<pre><code class="language-${language}">${content}</code></pre>`,
    '</section>',
  ].join('')
}

function normalizeAutolinks(text: string): string {
  let activeFence: { marker: string; length: number } | null = null

  return text
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((line) => {
      const fenceMatch = line.match(/^ {0,3}(`{3,}|~{3,})/)

      if (activeFence) {
        if (
          fenceMatch &&
          fenceMatch[1][0] === activeFence.marker &&
          fenceMatch[1].length >= activeFence.length &&
          new RegExp(`^ {0,3}\\${activeFence.marker}{${activeFence.length},}\\s*$`).test(line)
        ) {
          activeFence = null
        }
        return line
      }

      if (fenceMatch) {
        activeFence = {
          marker: fenceMatch[1][0],
          length: fenceMatch[1].length,
        }
        return line
      }

      return line.replace(URL_FOLLOWED_BY_CJK, '$1 $2')
    })
    .join('\n')
}

const html = computed(() => {
  const source = normalizeAutolinks(props.content || '')
  const environment: ArtifactRenderEnvironment = {
    artifacts: new Map(),
    enableArtifacts: props.enableArtifacts,
    nextFenceIndex: 0,
    scope: props.artifactScope,
    source,
  }
  const output = md.render(source, environment)
  renderedArtifacts = environment.artifacts
  return output
})

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Fall through when clipboard permissions are denied.
    }
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()

  try {
    if (typeof document.execCommand !== 'function' || !document.execCommand('copy')) {
      throw new Error('Clipboard is unavailable')
    }
  } finally {
    document.body.removeChild(textarea)
  }
}

async function handleArtifactAction(event: MouseEvent) {
  const target = event.target
  if (!(target instanceof Element)) return

  const button = target.closest<HTMLButtonElement>('button[data-artifact-action]')
  if (!button || !(event.currentTarget instanceof Element)) return
  if (!event.currentTarget.contains(button)) return

  const artifactId = button.dataset.artifactId
  const action = button.dataset.artifactAction
  if (!artifactId || !action) return

  const artifact = renderedArtifacts.get(artifactId)
  if (!artifact) return

  if (action === 'open') {
    emit('artifactOpen', artifact)
    return
  }

  if (action === 'copy') {
    try {
      await copyText(artifact.content)
      toast.success('代码已复制')
    } catch {
      toast.error('复制失败')
    }
    return
  }

  if (action === 'download') {
    try {
      downloadBlob(
        new Blob([artifact.content], { type: getArtifactMimeType(artifact.language) }),
        artifact.title,
      )
      toast.success(`已下载 ${artifact.title}`)
    } catch {
      toast.error('下载失败')
    }
  }
}
</script>

<template>
  <div class="markdown-content" @click="handleArtifactAction" v-html="html" />
</template>
