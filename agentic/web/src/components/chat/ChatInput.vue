<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatFilePickerDialog from '@/components/chat/ChatFilePickerDialog.vue'
import { useToast } from '@/composables/useToast'
import { fileApi } from '@/lib/api/file'
import {
  completeComposerUpload,
  createLocalComposerAttachment,
  isPreviewableComposerImage,
  mergeLibraryComposerAttachments,
  type ComposerAttachmentFile,
  type ComposerAttachmentMetadata,
  type FilePickerSelection,
} from '@/lib/composer-attachments'
import { useSkillsStore } from '@/stores/skills'
import type { SendMessageInput, SkillRef, SkillSummary } from '@/types/skill'

const props = withDefaults(defineProps<{
  disabled?: boolean
  sessionId?: string | null
  isRunning?: boolean
  onSend?: (input: SendMessageInput, files: ComposerAttachmentMetadata[]) => Promise<void>
  onStop?: () => void
}>(), {
  disabled: false,
  sessionId: null,
  isRunning: false,
  onSend: undefined,
  onStop: undefined,
})

const emit = defineEmits<{
  inputValueChange: [value: string]
}>()

const DRAFT_STORAGE_PREFIX = 'agentic:chat-draft:'

function draftStorageKey(sessionId: string): string {
  return `${DRAFT_STORAGE_PREFIX}${sessionId}`
}

function readSessionDraft(sessionId?: string | null): string {
  if (!sessionId || typeof window === 'undefined') return ''
  try {
    return window.localStorage.getItem(draftStorageKey(sessionId)) ?? ''
  } catch {
    return ''
  }
}

function writeSessionDraft(sessionId: string | null | undefined, value: string): void {
  if (!sessionId || typeof window === 'undefined') return
  try {
    if (value.length > 0) window.localStorage.setItem(draftStorageKey(sessionId), value)
    else window.localStorage.removeItem(draftStorageKey(sessionId))
  } catch {
    // Storage may be disabled or full. Keep the in-memory draft usable.
  }
}

const toast = useToast()
const skillsStore = useSkillsStore()
type UploadEntry = ComposerAttachmentFile & {
  rawFile?: File
}

const uploadItems = ref<UploadEntry[]>([])
const uploading = computed(() => uploadItems.value.some((file) => file.uploadStatus === 'uploading'))
const selectedFileIds = computed(() =>
  uploadItems.value
    .filter((file) => file.uploadStatus === 'uploaded')
    .map((file) => file.id),
)
const sending = ref(false)
const inputValue = ref(readSessionDraft(props.sessionId))
const selectedSkills = ref<SkillRef[]>([])
const filePickerOpen = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const composerRef = ref<InstanceType<typeof ChatComposer> | null>(null)
let uploadEntryId = 0
let previewRequestVersion = 0
const previewRequests = new Map<string, number>()

function setInputText(text: string) {
  inputValue.value = text
  writeSessionDraft(props.sessionId, text)
  emit('inputValueChange', text)
  composerRef.value?.focus()
}

function getInputValue() {
  return inputValue.value
}

function getFiles() {
  return uploadItems.value
    .filter((file) => file.uploadStatus === 'uploaded')
    .map((file): ComposerAttachmentMetadata => ({
      id: file.id,
      filename: file.filename,
      extension: file.extension,
      size: file.size,
      contentType: file.contentType,
    }))
}

function skillKey(skill: SkillRef): string {
  return `${skill.source}:${skill.skill_id ?? skill.name}`
}

function selectSkill(skill: SkillSummary) {
  const ref: SkillRef = {
    source: skill.scope === 'marketplace' ? 'marketplace' : 'personal',
    skill_id: skill.id,
    name: skill.name,
  }
  if (selectedSkills.value.length >= 5) return
  if (selectedSkills.value.some((selected) => skillKey(selected) === skillKey(ref))) return
  selectedSkills.value.push(ref)
}

function removeSkill(key: string) {
  selectedSkills.value = selectedSkills.value.filter((skill) => skillKey(skill) !== key)
}

defineExpose({
  setInputText,
  getInputValue,
  getFiles,
  getSelectedSkills: () => [...selectedSkills.value],
})

function handleInputChange(value: string) {
  inputValue.value = value
  writeSessionDraft(props.sessionId, value)
  emit('inputValueChange', value)
}

async function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  const selectedFiles = target.files
  if (!selectedFiles || selectedFiles.length === 0) return

  await uploadFiles(Array.from(selectedFiles))
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function createUploadEntry(file: File): UploadEntry {
  uploadEntryId += 1
  const entry: UploadEntry = {
    ...createLocalComposerAttachment(file, `local-${Date.now()}-${uploadEntryId}`),
    rawFile: file,
  }

  if (
    isPreviewableComposerImage(entry) &&
    typeof URL.createObjectURL === 'function'
  ) {
    try {
      entry.previewUrl = URL.createObjectURL(file)
    } catch {
      // Preview is optional; upload remains usable when object URLs are unavailable.
    }
  }

  return entry
}

function patchUploadEntry(fileId: string, patch: Partial<UploadEntry>) {
  uploadItems.value = uploadItems.value.map((file) =>
    file.id === fileId ? { ...file, ...patch } : file,
  )
}

async function uploadEntry(entry: UploadEntry) {
  if (!entry.rawFile) return

  patchUploadEntry(entry.id, {
    uploadStatus: 'uploading',
    uploadError: undefined,
    progress: 35,
  })

  try {
    const uploadedFile = await fileApi.uploadFile({
      file: entry.rawFile,
      ...(props.sessionId ? { session_id: props.sessionId } : {}),
    })

    const completed = completeComposerUpload(entry, uploadedFile)
    patchUploadEntry(entry.id, {
      ...completed,
      rawFile: undefined,
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : '上传失败'
    patchUploadEntry(entry.id, {
      uploadStatus: 'failed',
      uploadError: message,
      progress: 0,
    })
    toast.error(`文件「${entry.filename}」上传失败：${message}`)
  }
}

async function uploadFiles(selectedFiles: File[]) {
  if (selectedFiles.length === 0) return
  const entries = selectedFiles.map(createUploadEntry)
  uploadItems.value = [...uploadItems.value, ...entries]
  await Promise.all(entries.map(uploadEntry))
}

function revokePreviewUrl(previewUrl?: string): void {
  if (!previewUrl || typeof URL.revokeObjectURL !== 'function') return
  URL.revokeObjectURL(previewUrl)
}

function invalidatePreviewRequest(fileId: string): void {
  previewRequests.delete(fileId)
}

function clearAttachments(): void {
  previewRequests.clear()
  previewRequestVersion += 1
  for (const file of uploadItems.value) revokePreviewUrl(file.previewUrl)
  uploadItems.value = []
}

async function loadLibraryPreview(entry: UploadEntry): Promise<void> {
  if (!isPreviewableComposerImage(entry)) return

  const request = ++previewRequestVersion
  previewRequests.set(entry.id, request)

  try {
    const blob = await fileApi.previewFile(entry.id)
    if (
      previewRequests.get(entry.id) !== request ||
      !uploadItems.value.some((file) => file.id === entry.id)
    ) {
      return
    }

    const previewUrl = URL.createObjectURL(blob)
    if (
      previewRequests.get(entry.id) !== request ||
      !uploadItems.value.some((file) => file.id === entry.id)
    ) {
      revokePreviewUrl(previewUrl)
      return
    }

    const current = uploadItems.value.find((file) => file.id === entry.id)
    if (current?.previewUrl && current.previewUrl !== previewUrl) {
      revokePreviewUrl(current.previewUrl)
    }
    patchUploadEntry(entry.id, { previewUrl })
  } catch {
    // Thumbnail loading is non-blocking; the Composer falls back to the file icon.
  } finally {
    if (previewRequests.get(entry.id) === request) {
      previewRequests.delete(entry.id)
    }
  }
}

function openFileLibrary(): void {
  filePickerOpen.value = true
}

function addLibraryFiles(selected: FilePickerSelection[]): void {
  const existingIds = new Set(uploadItems.value.map((file) => file.id))
  const merged = mergeLibraryComposerAttachments(uploadItems.value, selected) as UploadEntry[]
  const added = merged.filter(
    (file) => file.origin === 'library' && !existingIds.has(file.id),
  )

  uploadItems.value = merged
  filePickerOpen.value = false
  for (const file of added) void loadLibraryPreview(file)
}

function removeFile(fileId: string) {
  const entry = uploadItems.value.find((file) => file.id === fileId)
  invalidatePreviewRequest(fileId)
  revokePreviewUrl(entry?.previewUrl)
  uploadItems.value = uploadItems.value.filter((file) => file.id !== fileId)
}

function retryFile(fileId: string) {
  const entry = uploadItems.value.find((file) => file.id === fileId)
  if (!entry) return
  void uploadEntry(entry)
}

async function handleSend() {
  const message = inputValue.value.trim()
  const sendingSessionId = props.sessionId

  if (!message) {
    toast.error('请输入消息内容')
    composerRef.value?.focus()
    return
  }

  if (!props.onSend) return
  if (uploading.value) {
    toast.error('附件仍在上传中')
    return
  }
  if (uploadItems.value.some((file) => file.uploadStatus === 'failed')) {
    toast.error('请先重试或移除上传失败的附件')
    return
  }

  sending.value = true
  try {
    const files = getFiles()
    await props.onSend(
      {
        message,
        attachmentIds: files.map((file) => file.id),
        skills: [...selectedSkills.value],
      },
      files,
    )
    writeSessionDraft(sendingSessionId, '')
    if (props.sessionId === sendingSessionId) {
      inputValue.value = ''
      clearAttachments()
      selectedSkills.value = []
      emit('inputValueChange', '')
      composerRef.value?.focus()
    }
  } catch (error) {
    console.error('发送消息失败', error)
  } finally {
    sending.value = false
  }
}

function handleStop() {
  props.onStop?.()
}

watch(
  () => props.sessionId,
  (nextSessionId, previousSessionId) => {
    writeSessionDraft(previousSessionId, inputValue.value)
    inputValue.value = readSessionDraft(nextSessionId)
    clearAttachments()
    filePickerOpen.value = false
    selectedSkills.value = []
    emit('inputValueChange', inputValue.value)
  },
)

onMounted(() => {
  if (skillsStore.skills.length === 0) {
    void skillsStore.loadSkills().catch(() => undefined)
  }
})

onBeforeUnmount(() => {
  clearAttachments()
})
</script>

<template>
  <ChatComposer
    ref="composerRef"
    :model-value="inputValue"
    :files="uploadItems"
    :uploading="uploading"
    :sending="sending"
    :disabled="disabled"
    :is-running="isRunning"
    :skills="skillsStore.activeSkills"
    :selected-skills="selectedSkills"
    @update:model-value="handleInputChange"
    @attach="fileInputRef?.click()"
    @open-file-library="openFileLibrary"
    @remove-file="removeFile"
    @retry-file="retryFile"
    @paste-files="uploadFiles"
    @send="handleSend"
    @stop="handleStop"
    @select-skill="selectSkill"
    @remove-skill="removeSkill"
  />

  <ChatFilePickerDialog
    v-model="filePickerOpen"
    :selected-ids="selectedFileIds"
    @confirm="addLibraryFiles"
  />

  <input
    ref="fileInputRef"
    type="file"
    multiple
    class="hidden-input"
    :disabled="uploading"
    @change="handleFileSelect"
  >
</template>
