<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AlertCircle,
  ArrowUp,
  CheckCircle2,
  FileText,
  Loader2,
  Paperclip,
  Pause,
  RotateCcw,
  XCircle,
} from 'lucide-vue-next'
import { formatFileSize } from '@/lib/utils'

export type ComposerFileItem = {
  id: string
  filename: string
  extension?: string
  size: number
  uploadStatus?: 'uploading' | 'uploaded' | 'failed'
  uploadError?: string
  progress?: number
}

const props = withDefaults(defineProps<{
  modelValue: string
  files?: ComposerFileItem[]
  disabled?: boolean
  uploading?: boolean
  sending?: boolean
  isRunning?: boolean
  placeholder?: string
}>(), {
  files: () => [],
  disabled: false,
  uploading: false,
  sending: false,
  isRunning: false,
  placeholder: '分配一个任务或提问任何问题...',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  attach: []
  removeFile: [fileId: string]
  retryFile: [fileId: string]
  pasteFiles: [files: File[]]
  send: []
  stop: []
}>()

const inputRef = ref<{ focus: () => void } | null>(null)
const hasFailedUpload = computed(() => props.files.some((file) => file.uploadStatus === 'failed'))
const canSend = computed(
  () =>
    props.modelValue.trim().length > 0 &&
    !props.disabled &&
    !props.sending &&
    !props.uploading &&
    !hasFailedUpload.value,
)

function focus() {
  inputRef.value?.focus()
}

function handleKeydown(event: Event | KeyboardEvent) {
  if (!(event instanceof KeyboardEvent)) return
  const target = event.target as HTMLElement | null
  if (target?.tagName !== 'TEXTAREA') return

  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    if (props.isRunning) {
      emit('stop')
    } else if (canSend.value) {
      emit('send')
    }
  }
}

function handlePaste(event: ClipboardEvent) {
  const pastedFiles = Array.from(event.clipboardData?.files || [])
  if (pastedFiles.length === 0) return

  event.preventDefault()
  emit('pasteFiles', pastedFiles)
}

defineExpose({ focus })
</script>

<template>
  <section
    class="chat-composer"
    :class="{ 'is-disabled': disabled }"
    @keydown.capture="handleKeydown"
    @paste.capture="handlePaste"
  >
    <div v-if="files.length > 0" class="upload-list composer-upload-list">
      <article v-for="file in files" :key="file.id" class="upload-card composer-upload-card">
        <div class="item-avatar">
          <Loader2 v-if="file.uploadStatus === 'uploading'" :size="16" class="spin" />
          <AlertCircle v-else-if="file.uploadStatus === 'failed'" :size="16" />
          <CheckCircle2 v-else-if="file.uploadStatus === 'uploaded'" :size="16" />
          <FileText v-else :size="16" />
        </div>
        <div class="upload-info">
          <p>{{ file.filename }}</p>
          <span>{{ file.extension || 'file' }} · {{ formatFileSize(file.size) }}</span>
          <ElProgress
            v-if="file.uploadStatus === 'uploading'"
            :percentage="file.progress || 35"
            :show-text="false"
            :indeterminate="true"
            :duration="1"
            class="upload-progress"
          />
          <span v-else-if="file.uploadStatus === 'failed'" class="upload-status failed">
            {{ file.uploadError || '上传失败' }}
          </span>
          <span v-else-if="file.uploadStatus === 'uploaded'" class="upload-status uploaded">
            已上传
          </span>
        </div>
        <ElTooltip v-if="file.uploadStatus === 'failed'" content="重试上传" placement="top">
          <button
            class="icon-button subtle tiny"
            type="button"
            aria-label="重试上传"
            @click="emit('retryFile', file.id)"
          >
            <RotateCcw :size="15" />
          </button>
        </ElTooltip>
        <ElTooltip content="移除附件" placement="top">
          <button
            class="icon-button subtle tiny"
            type="button"
            aria-label="移除附件"
            @click="emit('removeFile', file.id)"
          >
            <XCircle :size="16" />
          </button>
        </ElTooltip>
      </article>
    </div>

    <ElInput
      ref="inputRef"
      :model-value="modelValue"
      type="textarea"
      resize="none"
      :autosize="{ minRows: 2, maxRows: 8 }"
      :placeholder="placeholder"
      :disabled="sending || disabled"
      class="composer-textarea"
      @update:model-value="emit('update:modelValue', $event)"
    />

    <footer class="chat-input-footer composer-footer">
      <div class="composer-actions-left">
        <ElTooltip content="上传附件" placement="top">
          <button
            class="icon-button round"
            type="button"
            :disabled="uploading || disabled"
            aria-label="上传附件"
            @click="emit('attach')"
          >
            <Loader2 v-if="uploading" :size="16" class="spin" />
            <Paperclip v-else :size="16" />
          </button>
        </ElTooltip>
      </div>

      <div class="composer-actions-right">
        <span class="composer-hint">Enter 发送 · Shift + Enter 换行</span>
        <ElTooltip :content="isRunning ? '停止任务' : '发送消息'" placement="top">
          <button
            v-if="isRunning"
            class="icon-button round composer-stop-button"
            type="button"
            :disabled="disabled"
            aria-label="停止任务"
            @click="emit('stop')"
          >
            <Pause :size="16" />
          </button>
          <button
            v-else
            class="icon-button round composer-send-button"
            type="button"
            :disabled="!canSend"
            aria-label="发送消息"
            @click="emit('send')"
          >
            <Loader2 v-if="sending" :size="16" class="spin" />
            <ArrowUp v-else :size="16" />
          </button>
        </ElTooltip>
      </div>
    </footer>
  </section>
</template>
