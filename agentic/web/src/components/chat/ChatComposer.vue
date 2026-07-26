<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AlertCircle,
  ArrowUp,
  CheckCircle2,
  FileText,
  FolderOpen,
  Loader2,
  Paperclip,
  Pause,
  RotateCcw,
  Upload,
  XCircle,
} from 'lucide-vue-next'
import { formatFileSize } from '@/lib/utils'
import SkillChip from '@/components/skills/SkillChip.vue'
import SkillPicker from '@/components/skills/SkillPicker.vue'
import {
  isPreviewableComposerImage,
  type ComposerAttachmentFile,
} from '@/lib/composer-attachments'
import type { SkillRef, SkillSummary } from '@/types/skill'

export type ComposerFileItem = ComposerAttachmentFile

const props = withDefaults(defineProps<{
  modelValue: string
  files?: ComposerFileItem[]
  disabled?: boolean
  uploading?: boolean
  sending?: boolean
  isRunning?: boolean
  placeholder?: string
  skills?: SkillSummary[]
  selectedSkills?: SkillRef[]
}>(), {
  files: () => [],
  disabled: false,
  uploading: false,
  sending: false,
  isRunning: false,
  skills: () => [],
  selectedSkills: () => [],
  placeholder: '分配一个任务或提问任何问题...',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  attach: []
  removeFile: [fileId: string]
  retryFile: [fileId: string]
  pasteFiles: [files: File[]]
  openFileLibrary: []
  send: []
  stop: []
  selectSkill: [skill: SkillSummary]
  removeSkill: [skillKey: string]
}>()

const inputRef = ref<{ focus: () => void } | null>(null)
const pickerRef = ref<InstanceType<typeof SkillPicker> | null>(null)
const attachmentMenuRef = ref<HTMLElement | null>(null)
const attachmentTriggerRef = ref<HTMLButtonElement | null>(null)
const firstAttachmentActionRef = ref<HTMLButtonElement | null>(null)
const dismissedFor = ref<string | null>(null)
const attachmentMenuOpen = ref(false)
const dragActive = ref(false)
const previewFailures = ref<Set<string>>(new Set())
let dragDepth = 0
const skillTrigger = computed(() => props.modelValue.match(/(?:^|\s)\$([a-z0-9-]*)$/i))
const pickerOpen = computed(() => Boolean(skillTrigger.value) && dismissedFor.value !== props.modelValue)
const pickerQuery = computed(() => skillTrigger.value?.[1] ?? '')
const hasFailedUpload = computed(() => props.files.some((file) => file.uploadStatus === 'failed'))
const canAcceptAttachments = computed(
  () => !props.disabled && !props.sending && !props.uploading,
)
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

  if (pickerOpen.value && pickerRef.value?.handleKeydown(event)) return

  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    if (canSend.value) {
      emit('send')
    }
  }
}

function selectSkill(skill: SkillSummary) {
  emit('selectSkill', skill)
  const next = props.modelValue.replace(/\$[a-z0-9-]*$/i, '').replace(/\s+$/, ' ')
  emit('update:modelValue', next)
}

function skillKey(skill: SkillRef): string {
  return `${skill.source}:${skill.skill_id ?? skill.name}`
}

watch(() => props.modelValue, () => { dismissedFor.value = null })
watch(canAcceptAttachments, (allowed) => {
  if (allowed) return
  closeAttachmentMenu()
  resetDragState()
})
watch(
  () => props.files.map((file) => file.id),
  (ids) => {
    const activeIds = new Set(ids)
    previewFailures.value = new Set(
      [...previewFailures.value].filter((id) => activeIds.has(id)),
    )
  },
)

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
})

function handleDocumentPointerDown(event: PointerEvent): void {
  if (!attachmentMenuOpen.value) return
  const target = event.target
  if (target instanceof Node && attachmentMenuRef.value?.contains(target)) return
  closeAttachmentMenu()
}

async function toggleAttachmentMenu(): Promise<void> {
  if (!canAcceptAttachments.value) return
  attachmentMenuOpen.value = !attachmentMenuOpen.value
  if (attachmentMenuOpen.value) {
    await nextTick()
    firstAttachmentActionRef.value?.focus()
  }
}

function closeAttachmentMenu(restoreFocus = false): void {
  attachmentMenuOpen.value = false
  if (restoreFocus) attachmentTriggerRef.value?.focus()
}

function chooseAttachmentSource(source: 'upload' | 'library'): void {
  closeAttachmentMenu(true)
  if (source === 'upload') emit('attach')
  else emit('openFileLibrary')
}

function hasFileTransfer(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files')
}

function resetDragState(): void {
  dragDepth = 0
  dragActive.value = false
}

function handleDragEnter(event: DragEvent): void {
  if (!canAcceptAttachments.value || !hasFileTransfer(event)) return
  event.preventDefault()
  dragDepth += 1
  dragActive.value = true
}

function handleDragOver(event: DragEvent): void {
  if (!canAcceptAttachments.value || !hasFileTransfer(event)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function handleDragLeave(event: DragEvent): void {
  if (!dragActive.value) return
  event.preventDefault()
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragActive.value = false
}

function handleDrop(event: DragEvent): void {
  if (!canAcceptAttachments.value || !hasFileTransfer(event)) return
  const droppedFiles = Array.from(event.dataTransfer?.files ?? [])
  resetDragState()
  if (droppedFiles.length === 0) return
  event.preventDefault()
  emit('pasteFiles', droppedFiles)
}

function handlePaste(event: ClipboardEvent) {
  if (!canAcceptAttachments.value) return
  const pastedFiles = Array.from(event.clipboardData?.files || [])
  if (pastedFiles.length === 0) return

  event.preventDefault()
  emit('pasteFiles', pastedFiles)
}

function canShowPreview(file: ComposerAttachmentFile): boolean {
  return Boolean(
    file.previewUrl &&
    !previewFailures.value.has(file.id) &&
    isPreviewableComposerImage(file),
  )
}

function markPreviewFailed(fileId: string): void {
  previewFailures.value = new Set([...previewFailures.value, fileId])
}

defineExpose({ focus })
</script>

<template>
  <section
    class="chat-composer"
    :class="{ 'is-disabled': disabled }"
    @keydown.capture="handleKeydown"
    @paste.capture="handlePaste"
    @dragenter="handleDragEnter"
    @dragover="handleDragOver"
    @dragleave="handleDragLeave"
    @drop="handleDrop"
  >
    <div
      v-if="dragActive"
      class="composer-drop-overlay"
      data-testid="composer-drop-overlay"
      role="status"
      aria-live="polite"
    >
      <span class="composer-drop-icon"><Upload :size="24" /></span>
      <strong>释放以上传文件</strong>
      <small>文件会加入当前消息的附件列表</small>
    </div>

    <div v-if="files.length > 0" class="upload-list composer-upload-list">
      <article
        v-for="file in files"
        :key="file.id"
        class="upload-card composer-upload-card"
        :class="{ 'has-preview': canShowPreview(file) }"
      >
        <div class="item-avatar">
          <img
            v-if="canShowPreview(file)"
            :src="file.previewUrl"
            :alt="file.filename"
            class="composer-attachment-preview"
            @error="markPreviewFailed(file.id)"
          >
          <template v-else>
            <Loader2 v-if="file.uploadStatus === 'uploading'" :size="16" class="spin" />
            <AlertCircle v-else-if="file.uploadStatus === 'failed'" :size="16" />
            <CheckCircle2 v-else-if="file.uploadStatus === 'uploaded'" :size="16" />
            <FileText v-else :size="16" />
          </template>
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

    <div v-if="selectedSkills.length" class="composer-skill-chips">
      <SkillChip
        v-for="skill in selectedSkills"
        :key="skillKey(skill)"
        :skill="skill"
        removable
        @remove="emit('removeSkill', skillKey(skill))"
      />
    </div>

    <SkillPicker
      v-if="pickerOpen"
      ref="pickerRef"
      :skills="skills"
      :query="pickerQuery"
      :selected="selectedSkills"
      @select="selectSkill"
      @close="dismissedFor = modelValue"
    />

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
        <div ref="attachmentMenuRef" class="composer-attachment-menu">
          <ElTooltip content="添加附件" placement="top">
            <button
              ref="attachmentTriggerRef"
              class="icon-button round"
              type="button"
              :disabled="!canAcceptAttachments"
              aria-label="添加附件"
              aria-haspopup="menu"
              :aria-expanded="attachmentMenuOpen"
              @click="toggleAttachmentMenu"
            >
              <Loader2 v-if="uploading" :size="16" class="spin" />
              <Paperclip v-else :size="16" />
            </button>
          </ElTooltip>

          <div
            v-if="attachmentMenuOpen"
            class="composer-attachment-menu-popup"
            role="menu"
            aria-label="附件来源"
            @keydown.esc.stop.prevent="closeAttachmentMenu(true)"
          >
            <button
              ref="firstAttachmentActionRef"
              type="button"
              role="menuitem"
              aria-label="上传本地文件"
              @click="chooseAttachmentSource('upload')"
            >
              <Upload :size="17" />
              <span><strong>上传本地文件</strong><small>从当前设备选择</small></span>
            </button>
            <button
              type="button"
              role="menuitem"
              aria-label="从我的文件选择"
              @click="chooseAttachmentSource('library')"
            >
              <FolderOpen :size="17" />
              <span><strong>从我的文件选择</strong><small>复用已上传或生成的文件</small></span>
            </button>
          </div>
        </div>
      </div>

      <div class="composer-actions-right">
        <span class="composer-hint">
          {{ isRunning ? 'Enter 加入下一条 · Shift + Enter 换行' : 'Enter 发送 · Shift + Enter 换行' }}
        </span>
        <ElTooltip v-if="isRunning" content="停止任务" placement="top">
          <button
            class="icon-button round composer-stop-button"
            type="button"
            :disabled="disabled"
            aria-label="停止任务"
            @click="emit('stop')"
          >
            <Pause :size="16" />
          </button>
        </ElTooltip>
        <ElTooltip :content="isRunning ? '加入下一条' : '发送消息'" placement="top">
          <button
            class="icon-button round composer-send-button"
            type="button"
            :disabled="!canSend"
            :aria-label="isRunning ? '加入下一条' : '发送消息'"
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
