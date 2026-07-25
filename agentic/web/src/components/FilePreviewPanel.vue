<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Braces, Download, FileCode2, FileText, X } from 'lucide-vue-next'
import MarkdownContent from '@/components/MarkdownContent.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import UiState from '@/components/ui/UiState.vue'
import { useToast } from '@/composables/useToast'
import { fileApi } from '@/lib/api/file'
import type { ArtifactView } from '@/lib/chat-artifacts'
import { getFilePreviewDescriptor } from '@/lib/file-preview'
import type { AttachmentFile } from '@/lib/session-events'
import { downloadBlob, formatFileSize } from '@/lib/utils'
import SafeHtmlPreview from './chat/SafeHtmlPreview.vue'

const props = defineProps<{
  file: AttachmentFile
}>()

const emit = defineEmits<{
  close: []
}>()

const toast = useToast()
const panelRef = ref<HTMLElement | null>(null)
const content = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const imageUrl = ref<string | null>(null)
const loadedBlob = ref<Blob | null>(null)
let requestVersion = 0

const descriptor = computed(() =>
  getFilePreviewDescriptor(props.file.extension, props.file.filename),
)
const activeView = ref<ArtifactView | null>(descriptor.value.defaultView)
const showTabs = computed(() => descriptor.value.availableViews.length > 1)

function revokeImageUrl() {
  if (imageUrl.value) {
    URL.revokeObjectURL(imageUrl.value)
    imageUrl.value = null
  }
}

async function loadFileContent() {
  const version = ++requestVersion
  const fileId = props.file.id

  loading.value = false
  error.value = null
  content.value = null
  loadedBlob.value = null
  revokeImageUrl()

  if (descriptor.value.kind === 'unsupported') return

  loading.value = true

  try {
    const blob = await fileApi.downloadFile(fileId)
    if (version !== requestVersion || fileId !== props.file.id) return

    loadedBlob.value = blob
    if (descriptor.value.kind === 'image') {
      imageUrl.value = URL.createObjectURL(blob)
    } else {
      const nextContent = await blob.text()
      if (version !== requestVersion || fileId !== props.file.id) return
      content.value = nextContent
    }
  } catch (err) {
    if (version !== requestVersion || fileId !== props.file.id) return
    const message = err instanceof Error ? err.message : '加载文件内容失败'
    error.value = message
    toast.error(message)
  } finally {
    if (version === requestVersion && fileId === props.file.id) {
      loading.value = false
    }
  }
}

async function handleDownload() {
  const fileId = props.file.id
  const filename = props.file.filename

  try {
    const blob = loadedBlob.value ?? await fileApi.downloadFile(fileId)
    if (fileId === props.file.id) loadedBlob.value = blob
    downloadBlob(blob, filename)
    toast.success(`已下载「${filename}」`)
  } catch (err) {
    const message = err instanceof Error ? err.message : '下载失败'
    toast.error(`下载失败：${message}`)
  }
}

function selectView(view: ArtifactView) {
  if (!descriptor.value.availableViews.includes(view)) return
  activeView.value = view
}

async function handleTabKeydown(event: KeyboardEvent, currentIndex: number) {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()

  const options = descriptor.value.availableViews
  const direction = event.key === 'ArrowRight' ? 1 : -1
  const nextIndex = (currentIndex + direction + options.length) % options.length
  const nextView = options[nextIndex]
  if (!nextView) return

  selectView(nextView)
  await nextTick()
  panelRef.value
    ?.querySelector<HTMLButtonElement>(`[role="tab"][data-view="${nextView}"]`)
    ?.focus()
}

watch(
  () => [props.file.id, props.file.extension, props.file.filename] as const,
  () => {
    activeView.value = descriptor.value.defaultView
    void loadFileContent()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  requestVersion += 1
  revokeImageUrl()
})
</script>

<template>
  <aside
    ref="panelRef"
    class="preview-panel file-preview artifact-preview-panel"
    role="dialog"
    aria-modal="true"
    aria-label="文件预览"
  >
    <header class="preview-header artifact-preview-header">
      <div class="preview-title">
        <div class="file-icon">
          <FileText :size="16" />
        </div>
        <div>
          <p :title="file.filename">{{ file.filename }}</p>
          <span>{{ descriptor.extension || '未知类型' }} · {{ formatFileSize(file.size) }}</span>
        </div>
      </div>
      <div class="preview-actions">
        <UiIconButton label="下载文件" variant="subtle" @click="handleDownload">
          <Download :size="16" />
        </UiIconButton>
        <UiIconButton label="关闭文件预览" title="关闭" variant="subtle" @click="emit('close')">
          <X :size="16" />
        </UiIconButton>
      </div>
    </header>

    <div
      v-if="showTabs"
      class="artifact-preview-tabs"
      role="tablist"
      aria-label="文件视图"
    >
      <button
        v-for="(view, index) in descriptor.availableViews"
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

    <div class="preview-body artifact-preview-body file-preview-body">
      <UiState v-if="loading" kind="loading" title="正在加载文件" description="文件内容准备完成后会自动显示。" />
      <UiState v-else-if="error" kind="error" title="文件加载失败" :description="error">
        <template #actions><UiButton @click="loadFileContent">重新加载</UiButton></template>
      </UiState>
      <UiState v-else-if="descriptor.kind === 'unsupported'" title="暂不支持预览此文件类型" description="可以下载文件后使用本地应用查看。">
        <template #icon><FileText :size="28" /></template>
        <template #actions><UiButton @click="handleDownload"><template #icon><Download :size="16" /></template>下载文件</UiButton></template>
      </UiState>
      <pre
        v-else-if="activeView === 'source' && content !== null"
        class="artifact-source-code file-source-code"
      ><code>{{ content }}</code></pre>
      <div
        v-else-if="activeView === 'preview' && descriptor.kind === 'markdown' && content !== null"
        class="artifact-markdown-preview file-markdown-preview"
      >
        <MarkdownContent :content="content" />
      </div>
      <SafeHtmlPreview
        v-else-if="activeView === 'preview' && (descriptor.kind === 'html' || descriptor.kind === 'svg') && content !== null"
        :content="content"
        :title="file.filename"
      />
      <div v-else-if="activeView === 'preview' && descriptor.kind === 'image' && imageUrl" class="image-preview">
        <img :src="imageUrl" :alt="file.filename">
      </div>
    </div>
  </aside>
</template>
