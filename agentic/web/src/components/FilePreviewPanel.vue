<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Download, FileText, X } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { fileApi } from '@/lib/api/file'
import type { AttachmentFile } from '@/lib/session-events'
import { downloadBlob, formatFileSize } from '@/lib/utils'

const props = defineProps<{
  file: AttachmentFile
}>()

const emit = defineEmits<{
  close: []
}>()

const toast = useToast()
const content = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const imageUrl = ref<string | null>(null)

const textExtensions = [
  'txt',
  'md',
  'markdown',
  'json',
  'xml',
  'html',
  'htm',
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
]
const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp', 'ico']

const fileType = computed<'text' | 'image' | 'unsupported'>(() => {
  const ext = props.file.extension.toLowerCase().replace(/^\./, '')
  if (textExtensions.includes(ext)) return 'text'
  if (imageExtensions.includes(ext)) return 'image'
  return 'unsupported'
})

function revokeImageUrl() {
  if (imageUrl.value) {
    URL.revokeObjectURL(imageUrl.value)
    imageUrl.value = null
  }
}

async function loadFileContent() {
  if (fileType.value === 'unsupported') return

  loading.value = true
  error.value = null
  content.value = null
  revokeImageUrl()

  try {
    const blob = await fileApi.downloadFile(props.file.id)
    if (fileType.value === 'image') {
      imageUrl.value = URL.createObjectURL(blob)
    } else {
      content.value = await blob.text()
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : '加载文件内容失败'
    error.value = message
    toast.error(message)
  } finally {
    loading.value = false
  }
}

async function handleDownload() {
  try {
    const blob = await fileApi.downloadFile(props.file.id)
    downloadBlob(blob, props.file.filename)
    toast.success(`已下载「${props.file.filename}」`)
  } catch (err) {
    const message = err instanceof Error ? err.message : '下载失败'
    toast.error(`下载失败：${message}`)
  }
}

watch(
  () => props.file.id,
  () => {
    void loadFileContent()
  },
  { immediate: true },
)

onBeforeUnmount(revokeImageUrl)
</script>

<template>
  <aside class="preview-panel file-preview">
    <header class="preview-header">
      <div class="preview-title">
        <div class="file-icon">
          <FileText :size="16" />
        </div>
        <div>
          <p>{{ file.filename }}</p>
          <span>{{ file.extension.replace(/^\./, '') }} · {{ formatFileSize(file.size) }}</span>
        </div>
      </div>
      <div class="preview-actions">
        <button class="icon-button subtle" type="button" title="下载文件" @click="handleDownload">
          <Download :size="16" />
        </button>
        <button class="icon-button subtle" type="button" title="关闭" @click="emit('close')">
          <X :size="16" />
        </button>
      </div>
    </header>

    <div class="preview-body">
      <div v-if="loading" class="center-state">加载中...</div>
      <div v-else-if="error" class="center-state error-text">{{ error }}</div>
      <div v-else-if="fileType === 'unsupported'" class="unsupported-file">
        <div class="unsupported-icon">
          <FileText :size="32" />
        </div>
        <p>暂不支持预览此文件类型</p>
        <span>您可以下载文件后查看</span>
        <button class="button secondary" type="button" @click="handleDownload">
          <Download :size="16" />
          下载文件
        </button>
      </div>
      <div v-else-if="fileType === 'image' && imageUrl" class="image-preview">
        <img :src="imageUrl" :alt="file.filename">
      </div>
      <pre v-else-if="fileType === 'text' && content !== null" class="text-preview">{{ content }}</pre>
    </div>
  </aside>
</template>
