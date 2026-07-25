<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Braces, Copy, Download, FileCode2, X } from 'lucide-vue-next'
import MarkdownContent from '@/components/MarkdownContent.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import { useToast } from '@/composables/useToast'
import {
  copyArtifactText,
  downloadInlineArtifact,
  type ArtifactView,
  type InlineChatArtifact,
} from '@/lib/chat-artifacts'
import SafeHtmlPreview from './SafeHtmlPreview.vue'

const props = defineProps<{
  artifact: InlineChatArtifact
}>()

const emit = defineEmits<{
  close: []
}>()

const toast = useToast()
const panelRef = ref<HTMLElement | null>(null)

function defaultView(artifact: InlineChatArtifact): ArtifactView {
  return artifact.availableViews.includes('preview') ? 'preview' : 'source'
}

const activeView = ref<ArtifactView>(defaultView(props.artifact))
const showTabs = computed(() => props.artifact.availableViews.length > 1)

watch(
  () => props.artifact.id,
  () => {
    activeView.value = defaultView(props.artifact)
  },
)

function selectView(view: ArtifactView) {
  if (!props.artifact.availableViews.includes(view)) return
  activeView.value = view
}

async function handleTabKeydown(event: KeyboardEvent, currentIndex: number) {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()

  const options = props.artifact.availableViews
  const direction = event.key === 'ArrowRight' ? 1 : -1
  const nextIndex = (currentIndex + direction + options.length) % options.length
  selectView(options[nextIndex])
  await nextTick()
  panelRef.value
    ?.querySelector<HTMLButtonElement>(`[role="tab"][data-view="${options[nextIndex]}"]`)
    ?.focus()
}

async function handleCopy() {
  try {
    await copyArtifactText(props.artifact.content)
    toast.success('代码已复制')
  } catch {
    toast.error('复制失败')
  }
}

function handleDownload() {
  try {
    downloadInlineArtifact(props.artifact)
    toast.success(`已下载 ${props.artifact.title}`)
  } catch {
    toast.error('下载失败')
  }
}
</script>

<template>
  <aside
    ref="panelRef"
    class="preview-panel artifact-preview-panel"
    role="dialog"
    aria-modal="true"
    aria-label="Artifact 预览"
  >
    <header class="preview-header artifact-preview-header">
      <div class="preview-title">
        <span class="artifact-preview-icon"><FileCode2 :size="17" /></span>
        <div>
          <p :title="artifact.title">{{ artifact.title }}</p>
          <span>{{ artifact.language }}</span>
        </div>
      </div>
      <div class="preview-actions">
        <UiIconButton label="复制 Artifact" variant="subtle" @click="handleCopy">
          <Copy :size="16" />
        </UiIconButton>
        <UiIconButton label="下载 Artifact" variant="subtle" @click="handleDownload">
          <Download :size="16" />
        </UiIconButton>
        <UiIconButton
          label="关闭 Artifact 预览"
          title="关闭"
          variant="subtle"
          @click="emit('close')"
        >
          <X :size="16" />
        </UiIconButton>
      </div>
    </header>

    <div
      v-if="showTabs"
      class="artifact-preview-tabs"
      role="tablist"
      aria-label="Artifact 视图"
    >
      <button
        v-for="(view, index) in artifact.availableViews"
        :key="view"
        type="button"
        role="tab"
        :data-view="view"
        :aria-selected="activeView === view"
        :tabindex="activeView === view ? 0 : -1"
        @click="selectView(view)"
        @keydown="handleTabKeydown($event, index)"
      >
        <Braces v-if="view === 'source'" :size="14" />
        <FileCode2 v-else :size="14" />
        {{ view === 'source' ? '源码' : '预览' }}
      </button>
    </div>

    <div class="preview-body artifact-preview-body">
      <pre v-if="activeView === 'source'" class="artifact-source-code"><code>{{ artifact.content }}</code></pre>
      <div v-else-if="artifact.kind === 'markdown'" class="artifact-markdown-preview">
        <MarkdownContent :content="artifact.content" />
      </div>
      <SafeHtmlPreview
        v-else-if="artifact.kind === 'html'"
        :content="artifact.content"
        :title="artifact.title"
      />
    </div>
  </aside>
</template>
