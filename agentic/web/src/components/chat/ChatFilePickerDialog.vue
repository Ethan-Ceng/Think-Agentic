<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { File, Folder, Search } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiState from '@/components/ui/UiState.vue'
import UiTextField from '@/components/ui/UiTextField.vue'
import { fileApi } from '@/lib/api/file'
import type { ManagedFile } from '@/lib/api/types'
import {
  toFilePickerSelection,
  type FilePickerSelection,
} from '@/lib/composer-attachments'
import { formatFileSize } from '@/lib/utils'

type PathNode = {
  id: string | null
  name: string
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  selectedIds?: string[]
}>(), {
  selectedIds: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [files: FilePickerSelection[]]
}>()

const files = ref<ManagedFile[]>([])
const loading = ref(false)
const loadError = ref('')
const path = ref<PathNode[]>([{ id: null, name: '全部文件' }])
const searchWord = ref('')
const fileKind = ref('all')
const sourceType = ref('all')
const selectedFiles = ref<FilePickerSelection[]>([])
const paginator = ref({
  current_page: 1,
  page_size: 20,
  total_page: 0,
  total_record: 0,
})

const existingIds = computed(() => new Set(props.selectedIds))
const currentParentId = computed(() => path.value.at(-1)?.id ?? null)
const selectionCount = computed(() => selectedFiles.value.length)
const addButtonLabel = computed(() =>
  selectionCount.value > 0
    ? `添加 ${selectionCount.value} 个文件`
    : '添加文件',
)

let requestVersion = 0
let searchTimer = 0
let previouslyFocusedElement: HTMLElement | null = null

function restoreOpeningFocus(): void {
  previouslyFocusedElement?.focus()
  previouslyFocusedElement = null
}

const dialogOpen = computed({
  get: () => props.modelValue,
  set: (value: boolean) => {
    emit('update:modelValue', value)
    if (!value) void nextTick(restoreOpeningFocus)
  },
})

function resetDialogState(): void {
  requestVersion += 1
  window.clearTimeout(searchTimer)
  files.value = []
  loadError.value = ''
  path.value = [{ id: null, name: '全部文件' }]
  searchWord.value = ''
  fileKind.value = 'all'
  sourceType.value = 'all'
  selectedFiles.value = []
  paginator.value = {
    current_page: 1,
    page_size: 20,
    total_page: 0,
    total_record: 0,
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) {
      requestVersion += 1
      window.clearTimeout(searchTimer)
      return
    }

    previouslyFocusedElement =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    resetDialogState()
    void loadFiles(1)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  requestVersion += 1
  window.clearTimeout(searchTimer)
})

async function loadFiles(page = 1): Promise<void> {
  if (!props.modelValue) return

  const currentRequest = ++requestVersion
  loading.value = true
  loadError.value = ''

  try {
    const data = await fileApi.listFiles({
      parent_id: currentParentId.value || undefined,
      search_word: searchWord.value.trim() || undefined,
      file_kind: fileKind.value,
      source_type: sourceType.value,
      current_page: page,
      page_size: paginator.value.page_size,
    })
    if (currentRequest !== requestVersion) return

    files.value = data.list
    paginator.value = data.paginator
  } catch (error) {
    if (currentRequest !== requestVersion) return
    files.value = []
    loadError.value = error instanceof Error ? error.message : '文件加载失败'
  } finally {
    if (currentRequest === requestVersion) loading.value = false
  }
}

function scheduleSearch(): void {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    void loadFiles(1)
  }, 300)
}

function refreshFromFilter(): void {
  window.clearTimeout(searchTimer)
  void loadFiles(1)
}

async function openFolder(file: ManagedFile): Promise<void> {
  if (file.type !== 'folder') return
  path.value = [...path.value, { id: file.id, name: file.name }]
  await loadFiles(1)
}

async function goToPath(index: number): Promise<void> {
  if (index < 0 || index >= path.value.length) return
  path.value = path.value.slice(0, index + 1)
  await loadFiles(1)
}

function isExisting(file: ManagedFile): boolean {
  return existingIds.value.has(file.id)
}

function isSelected(file: ManagedFile): boolean {
  return isExisting(file) || selectedFiles.value.some((selected) => selected.id === file.id)
}

function toggleFile(file: ManagedFile): void {
  if (isExisting(file)) return
  const selection = toFilePickerSelection(file)
  if (!selection) return

  const selected = selectedFiles.value.some((item) => item.id === selection.id)
  selectedFiles.value = selected
    ? selectedFiles.value.filter((item) => item.id !== selection.id)
    : [...selectedFiles.value, selection]
}

function confirmSelection(): void {
  if (selectedFiles.value.length === 0) return
  emit('confirm', [...selectedFiles.value])
  dialogOpen.value = false
}

function cancelSelection(): void {
  dialogOpen.value = false
}
</script>

<template>
  <ElDialog
    v-model="dialogOpen"
    title="从我的文件选择"
    width="min(760px, calc(100vw - 24px))"
    append-to-body
    align-center
    destroy-on-close
    class="chat-file-picker-dialog"
    @closed="restoreOpeningFocus"
  >
    <div class="chat-file-picker">
      <div class="chat-file-picker-toolbar">
        <nav class="chat-file-picker-breadcrumb" aria-label="文件目录">
          <template v-for="(node, index) in path" :key="node.id || 'root'">
            <button
              type="button"
              :aria-current="index === path.length - 1 ? 'page' : undefined"
              @click="goToPath(index)"
            >
              {{ node.name }}
            </button>
            <span v-if="index < path.length - 1" aria-hidden="true">/</span>
          </template>
        </nav>

        <UiTextField
          v-model="searchWord"
          label="搜索当前目录"
          type="search"
          placeholder="搜索当前目录"
          compact
          class="chat-file-picker-search"
          @input="scheduleSearch"
        >
          <template #leading><Search :size="15" /></template>
        </UiTextField>
      </div>

      <div class="chat-file-picker-filters">
        <label>
          <span>类型</span>
          <select v-model="fileKind" aria-label="文件类型" @change="refreshFromFilter">
            <option value="all">全部类型</option>
            <option value="image">图片</option>
            <option value="video">视频</option>
            <option value="audio">音频</option>
            <option value="document">文档</option>
            <option value="other">其他</option>
          </select>
        </label>
        <label>
          <span>来源</span>
          <select v-model="sourceType" aria-label="文件来源" @change="refreshFromFilter">
            <option value="all">全部来源</option>
            <option value="user_upload">用户上传</option>
            <option value="agent_generated">AI 生成</option>
          </select>
        </label>
        <span class="chat-file-picker-selection" aria-live="polite">
          已选 {{ selectionCount }} 个
        </span>
      </div>

      <div class="chat-file-picker-content" :aria-busy="loading">
        <UiState
          v-if="loading"
          kind="loading"
          title="正在加载文件"
          description="正在读取当前目录内容。"
          compact
        />
        <UiState
          v-else-if="loadError"
          kind="error"
          title="文件加载失败"
          :description="loadError"
          compact
        >
          <template #actions>
            <UiButton
              size="small"
              aria-label="重试加载文件"
              @click="loadFiles(paginator.current_page)"
            >
              重试
            </UiButton>
          </template>
        </UiState>
        <UiState
          v-else-if="files.length === 0"
          title="当前目录暂无文件"
          description="请切换目录或调整筛选条件。"
          compact
        />

        <div v-else class="chat-file-picker-list" aria-live="polite">
          <article
            v-for="file in files"
            :key="file.id"
            class="chat-file-picker-row"
            :class="{ selected: isSelected(file), folder: file.type === 'folder' }"
          >
            <button
              v-if="file.type === 'folder'"
              type="button"
              class="chat-file-picker-file"
              :aria-label="`打开文件夹：${file.name}`"
              @click="openFolder(file)"
            >
              <span class="chat-file-picker-icon"><Folder :size="20" /></span>
              <span class="chat-file-picker-copy">
                <strong>{{ file.name }}</strong>
                <small>文件夹</small>
              </span>
            </button>

            <label v-else class="chat-file-picker-file">
              <input
                type="checkbox"
                :checked="isSelected(file)"
                :disabled="isExisting(file)"
                :aria-label="`选择文件：${file.name}`"
                @change="toggleFile(file)"
              >
              <span class="chat-file-picker-icon"><File :size="20" /></span>
              <span class="chat-file-picker-copy">
                <strong>{{ file.name }}</strong>
                <small>
                  {{ file.extension || 'file' }} · {{ formatFileSize(file.size) }}
                  · {{ file.source_type === 'agent_generated' ? 'AI 生成' : '用户上传' }}
                </small>
              </span>
              <span v-if="isExisting(file)" class="chat-file-picker-added">已添加</span>
            </label>
          </article>
        </div>
      </div>

      <ElPagination
        v-if="!loading && !loadError && paginator.total_record > paginator.page_size"
        v-model:current-page="paginator.current_page"
        :page-size="paginator.page_size"
        :total="paginator.total_record"
        layout="total, prev, pager, next"
        class="chat-file-picker-pagination"
        @current-change="loadFiles"
      />
    </div>

    <template #footer>
      <div class="chat-file-picker-footer">
        <UiButton aria-label="取消选择文件" @click="cancelSelection">取消</UiButton>
        <UiButton
          variant="primary"
          :disabled="selectionCount === 0"
          :aria-label="addButtonLabel"
          @click="confirmSelection"
        >
          {{ addButtonLabel }}
        </UiButton>
      </div>
    </template>
  </ElDialog>
</template>
