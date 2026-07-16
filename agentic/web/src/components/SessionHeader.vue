<script setup lang="ts">
import { computed, ref } from 'vue'
import { Activity, CheckCircle2, Circle, Clock3, Download, FileSearch, FileText, Loader2, PanelLeftOpen, X } from 'lucide-vue-next'
import { useSidebar } from '@/composables/useSidebar'
import { useToast } from '@/composables/useToast'
import { fileApi } from '@/lib/api/file'
import type { SessionFile, SessionStatus } from '@/lib/api/types'
import type { AttachmentFile } from '@/lib/session-events'
import { sessionFileToAttachment } from '@/lib/session-events'
import { downloadBlob, formatFileSize } from '@/lib/utils'

const props = withDefaults(defineProps<{
  title?: string
  files?: SessionFile[]
  fileListOpen?: boolean
  onFetchFiles?: () => void | Promise<void>
  status?: SessionStatus
}>(), {
  title: '',
  files: () => [],
  fileListOpen: undefined,
  onFetchFiles: undefined,
  status: 'pending',
})

const emit = defineEmits<{
  'update:fileListOpen': [open: boolean]
  fileClick: [file: AttachmentFile]
  openTrace: []
}>()

const sidebar = useSidebar()
const toast = useToast()
const internalOpen = ref(false)
const downloadingId = ref<string | null>(null)
const statusMeta = computed(() => {
  switch (props.status) {
    case 'running':
      return { label: '执行中', icon: Loader2 }
    case 'waiting':
      return { label: '等待回复', icon: Clock3 }
    case 'completed':
      return { label: '已完成', icon: CheckCircle2 }
    default:
      return { label: '准备中', icon: Circle }
  }
})

const openState = computed({
  get() {
    return props.fileListOpen ?? internalOpen.value
  },
  set(value: boolean) {
    if (props.fileListOpen === undefined) {
      internalOpen.value = value
    }
    emit('update:fileListOpen', value)
    if (value) {
      void props.onFetchFiles?.()
    }
  },
})

const uniqueFileList = computed(() => {
  const result: SessionFile[] = []
  for (const file of props.files || []) {
    const key = file.filepath || file.filename
    const existingIndex = result.findIndex((item) => (item.filepath || item.filename) === key)
    if (existingIndex >= 0) {
      result[existingIndex] = file
    } else {
      result.push(file)
    }
  }
  return result
})

async function handleDownload(file: SessionFile, event: Event) {
  event.stopPropagation()
  if (downloadingId.value) return

  downloadingId.value = file.id
  try {
    const blob = await fileApi.downloadFile(file.id)
    downloadBlob(blob, file.filename || `file-${file.id}`)
    toast.success(`已下载「${file.filename}」`)
  } catch (err) {
    const message = err instanceof Error ? err.message : '下载失败'
    toast.error(`下载「${file.filename}」失败：${message}`)
  } finally {
    downloadingId.value = null
  }
}

function handleFileClick(file: SessionFile) {
  emit('fileClick', sessionFileToAttachment(file))
  openState.value = false
}
</script>

<template>
  <header class="session-header">
    <button
      v-if="sidebar.mobile.value && !sidebar.open.value"
      class="icon-button"
      type="button"
      title="打开侧边栏"
      @click="sidebar.openSidebar()"
    >
      <PanelLeftOpen :size="18" />
    </button>
    <h1>{{ title || '未命名任务' }}</h1>
    <div class="session-header-actions">
      <span class="session-status-pill" :class="`status-${status}`" role="status">
        <component :is="statusMeta.icon" :size="13" :class="{ spin: status === 'running' }" />
        {{ statusMeta.label }}
      </span>
      <button class="icon-button subtle" type="button" title="查看运行 Trace" @click="emit('openTrace')">
        <Activity :size="18" />
      </button>
      <button class="icon-button subtle" type="button" title="查看任务文件" @click="openState = true">
        <FileSearch :size="18" />
      </button>
    </div>
  </header>

  <Teleport to="body">
    <div v-if="openState" class="modal-backdrop" @click.self="openState = false">
      <section class="modal-panel file-list-modal" role="dialog" aria-modal="true">
        <header class="modal-title-row">
          <h2>此任务中的所有文件</h2>
          <button class="icon-button subtle" type="button" @click="openState = false">
            <X :size="16" />
          </button>
        </header>

        <div class="file-list-body">
          <p v-if="uniqueFileList.length === 0" class="empty-state">暂无文件</p>
          <article
            v-for="file in uniqueFileList"
            v-else
            :key="file.id"
            class="file-list-item"
            role="button"
            tabindex="0"
            @click="handleFileClick(file)"
            @keydown.enter.prevent="handleFileClick(file)"
            @keydown.space.prevent="handleFileClick(file)"
          >
            <div class="item-avatar">
              <FileText :size="16" />
            </div>
            <div class="file-list-info">
              <p>{{ file.filename }}</p>
              <span>{{ file.extension.replace(/^\./, '') }} · {{ formatFileSize(file.size) }}</span>
            </div>
            <button
              class="icon-button subtle tiny"
              type="button"
              :disabled="downloadingId === file.id"
              :title="`下载 ${file.filename}`"
              @click="handleDownload(file, $event)"
            >
              <Download :size="16" />
            </button>
          </article>
        </div>
      </section>
    </div>
  </Teleport>
</template>
