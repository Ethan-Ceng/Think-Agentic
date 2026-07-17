<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ChatComposer, { type ComposerFileItem } from '@/components/chat/ChatComposer.vue'
import { useToast } from '@/composables/useToast'
import { fileApi } from '@/lib/api/file'
import type { FileInfo } from '@/lib/api/types'
import { useSkillsStore } from '@/stores/skills'
import type { SendMessageInput, SkillRef, SkillSummary } from '@/types/skill'

const props = withDefaults(defineProps<{
  disabled?: boolean
  sessionId?: string | null
  isRunning?: boolean
  onSend?: (input: SendMessageInput, files: FileInfo[]) => Promise<void>
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

const toast = useToast()
const skillsStore = useSkillsStore()
type UploadEntry = ComposerFileItem & {
  rawFile?: File
  fileInfo?: FileInfo
}

const uploadItems = ref<UploadEntry[]>([])
const uploading = computed(() => uploadItems.value.some((file) => file.uploadStatus === 'uploading'))
const sending = ref(false)
const inputValue = ref('')
const selectedSkills = ref<SkillRef[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const composerRef = ref<InstanceType<typeof ChatComposer> | null>(null)
let uploadEntryId = 0

function setInputText(text: string) {
  inputValue.value = text
  emit('inputValueChange', text)
  composerRef.value?.focus()
}

function getInputValue() {
  return inputValue.value
}

function getFiles() {
  return uploadItems.value
    .filter((file) => file.uploadStatus === 'uploaded' && file.fileInfo)
    .map((file) => file.fileInfo as FileInfo)
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
  return {
    id: `local-${Date.now()}-${uploadEntryId}`,
    filename: file.name,
    extension: file.name.split('.').pop() || 'file',
    size: file.size,
    uploadStatus: 'uploading',
    progress: 20,
    rawFile: file,
  }
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

    patchUploadEntry(entry.id, {
      filename: uploadedFile.filename,
      extension: uploadedFile.extension || entry.extension,
      size: uploadedFile.size,
      uploadStatus: 'uploaded',
      progress: 100,
      fileInfo: uploadedFile,
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

function removeFile(fileId: string) {
  uploadItems.value = uploadItems.value.filter((file) => file.id !== fileId)
}

function retryFile(fileId: string) {
  const entry = uploadItems.value.find((file) => file.id === fileId)
  if (!entry) return
  void uploadEntry(entry)
}

async function handleSend() {
  const message = inputValue.value.trim()

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
    inputValue.value = ''
    uploadItems.value = []
    selectedSkills.value = []
    emit('inputValueChange', '')
    composerRef.value?.focus()
  } catch (error) {
    console.error('发送消息失败', error)
  } finally {
    sending.value = false
  }
}

function handleStop() {
  props.onStop?.()
}

onMounted(() => {
  if (skillsStore.skills.length === 0) {
    void skillsStore.loadSkills().catch(() => undefined)
  }
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
    @remove-file="removeFile"
    @retry-file="retryFile"
    @paste-files="uploadFiles"
    @send="handleSend"
    @stop="handleStop"
    @select-skill="selectSkill"
    @remove-skill="removeSkill"
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
