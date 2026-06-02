<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { UploadRequestOptions } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FileItem } from '@/models/file'
import { createFolder, deleteFile, getFiles, updateFile, uploadManagedFile } from '@/services/file'

type ViewMode = 'table' | 'grid'
type FileKind = 'folder' | 'image' | 'video' | 'audio' | 'document' | 'other'
type FileKindFilter = 'all' | 'image' | 'video' | 'audio' | 'document' | 'other'
type SourceFilter = 'all' | 'upload' | 'generated'
type PathNode = { id: string | null; name: string }
type MoveTarget = { id: string; name: string; depth: number }

const props = defineProps<{ createType?: string }>()
const emit = defineEmits(['update:createType'])

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const files = ref<FileItem[]>([])
const pathStack = ref<PathNode[]>([{ id: null, name: '全部文件' }])
const viewMode = ref<ViewMode>('table')
const kindFilter = ref<FileKindFilter>('all')
const sourceFilter = ref<SourceFilter>('all')
const selectedIds = ref<string[]>([])

const renameDialogVisible = ref(false)
const editingFile = ref<FileItem | null>(null)
const editingName = ref('')

const moveDialogVisible = ref(false)
const moveTargetLoading = ref(false)
const moveTargets = ref<MoveTarget[]>([])
const moveTargetId = ref('')

const kindFilters: Array<{ value: FileKindFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频' },
  { value: 'audio', label: '音频' },
  { value: 'document', label: '文档' },
  { value: 'other', label: '其他' },
]

const sourceFilters: Array<{ value: SourceFilter; label: string }> = [
  { value: 'all', label: '全部来源' },
  { value: 'upload', label: '用户上传' },
  { value: 'generated', label: '生成文件' },
]

const imageExts = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'])
const videoExts = new Set(['mp4', 'webm', 'mov', 'm4v', 'avi'])
const audioExts = new Set(['mp3', 'wav', 'ogg', 'm4a', 'flac'])
const documentExts = new Set(['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'md', 'csv', 'json'])

const currentParentId = computed(() => pathStack.value[pathStack.value.length - 1]?.id ?? null)
const currentDirectoryName = computed(() => pathStack.value[pathStack.value.length - 1]?.name ?? '全部文件')
const searchWord = computed(() => String(route.query?.search_word ?? '').trim())

const filteredFiles = computed(() =>
  files.value.filter((file) => matchesKind(file, kindFilter.value) && matchesSource(file, sourceFilter.value)),
)
const selectedFiles = computed(() => files.value.filter((file) => selectedIds.value.includes(file.id)))
const allVisibleSelected = computed(
  () => filteredFiles.value.length > 0 && filteredFiles.value.every((file) => selectedIds.value.includes(file.id)),
)
const isIndeterminate = computed(() => selectedIds.value.length > 0 && !allVisibleSelected.value)
const fileCount = computed(() => files.value.filter((file) => file.type === 'file').length)
const folderCount = computed(() => files.value.filter((file) => file.type === 'folder').length)
const generatedCount = computed(() => files.value.filter((file) => file.type === 'file' && file.source !== 'upload').length)
const totalSize = computed(() => files.value.reduce((sum, file) => sum + (file.type === 'file' ? file.size : 0), 0))

const loadFiles = async () => {
  loading.value = true
  try {
    const res = await getFiles({
      parent_id: currentParentId.value || undefined,
      search_word: searchWord.value || undefined,
    })
    files.value = res.data
    pruneSelection()
  } finally {
    loading.value = false
  }
}

const openCreateFolder = async () => {
  const { value } = await ElMessageBox.prompt('目录名称', '新建目录', {
    inputPlaceholder: '请输入目录名称',
  })
  await createFolder({ name: String(value || ''), parent_id: currentParentId.value })
  ElMessage.success('目录已创建')
  await loadFiles()
}

const openRename = (file: FileItem) => {
  editingFile.value = file
  editingName.value = file.name
  renameDialogVisible.value = true
}

const saveRename = async () => {
  if (!editingFile.value) return
  await updateFile(editingFile.value.id, { name: editingName.value })
  renameDialogVisible.value = false
  ElMessage.success('名称已更新')
  await loadFiles()
}

const openMoveDialog = async (file?: FileItem) => {
  if (file) selectedIds.value = [file.id]
  if (!selectedIds.value.length) return
  moveDialogVisible.value = true
  await loadMoveTargets()
}

const loadMoveTargets = async () => {
  moveTargetLoading.value = true
  try {
    const selectedSet = new Set(selectedIds.value)
    const targets: MoveTarget[] = [{ id: '', name: '全部文件', depth: 0 }]
    const walk = async (parentId: string | null, depth: number) => {
      const res = await getFiles({ parent_id: parentId || undefined })
      for (const file of res.data) {
        if (file.type !== 'folder' || selectedSet.has(file.id)) continue
        targets.push({ id: file.id, name: file.name, depth })
        await walk(file.id, depth + 1)
      }
    }
    await walk(null, 1)
    moveTargets.value = targets
    moveTargetId.value = currentParentId.value || ''
  } finally {
    moveTargetLoading.value = false
  }
}

const saveMove = async () => {
  if (!selectedFiles.value.length) return
  await Promise.all(selectedFiles.value.map((file) => updateFile(file.id, { parent_id: moveTargetId.value || null })))
  moveDialogVisible.value = false
  ElMessage.success('文件已移动')
  await loadFiles()
}

const removeFile = async (file: FileItem) => {
  await removeFiles([file])
}

const removeSelectedFiles = async () => {
  await removeFiles(selectedFiles.value)
}

const removeFiles = async (targets: FileItem[]) => {
  if (!targets.length) return
  const name = targets.length === 1 ? targets[0].name : `${targets.length} 个文件或目录`
  await ElMessageBox.confirm(`删除 ${name}？目录中的文件也会被删除。`, '确认删除', { type: 'warning' })
  await Promise.all(targets.map((file) => deleteFile(file.id)))
  selectedIds.value = []
  ElMessage.success('文件已删除')
  await loadFiles()
}

const openFolder = async (file: FileItem) => {
  if (file.type !== 'folder') return
  pathStack.value = [...pathStack.value, { id: file.id, name: file.name }]
  await loadFiles()
}

const goToPath = async (index: number) => {
  pathStack.value = pathStack.value.slice(0, index + 1)
  await loadFiles()
}

const goParent = async () => {
  if (pathStack.value.length <= 1) return
  pathStack.value = pathStack.value.slice(0, -1)
  await loadFiles()
}

const handleUpload = (option: UploadRequestOptions) => {
  const { file, onSuccess, onError } = option
  const run = async () => {
    try {
      const res = await uploadManagedFile(file as File, currentParentId.value)
      onSuccess(res.data)
      ElMessage.success('文件已上传')
      await loadFiles()
    } catch (error) {
      onError(error as any)
    }
  }
  run()
  return { abort: () => {} }
}

const previewFile = async (file: FileItem) => {
  if (file.type === 'folder') {
    await openFolder(file)
    return
  }
  const url = file.preview_url || file.url || file.download_url
  if (!url) {
    ElMessage.warning('该文件暂无预览地址')
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

const downloadFile = (file: FileItem) => {
  const url = file.download_url || file.url
  if (!url) {
    ElMessage.warning('该文件暂无下载地址')
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

const toggleSelect = (file: FileItem, checked?: string | number | boolean) => {
  const nextChecked = typeof checked === 'boolean' ? checked : !selectedIds.value.includes(file.id)
  selectedIds.value = nextChecked
    ? Array.from(new Set([...selectedIds.value, file.id]))
    : selectedIds.value.filter((id) => id !== file.id)
}

const toggleSelectAll = (checked: string | number | boolean) => {
  selectedIds.value = checked ? filteredFiles.value.map((file) => file.id) : []
}

const isSelected = (file: FileItem) => selectedIds.value.includes(file.id)

const clearSearch = () => {
  const query = { ...route.query }
  delete query.search_word
  router.push({ path: route.path, query })
}

const pruneSelection = () => {
  const visibleIds = new Set(filteredFiles.value.map((file) => file.id))
  selectedIds.value = selectedIds.value.filter((id) => visibleIds.has(id))
}

function getExtension(file: FileItem) {
  const extension = file.extension || file.name.split('.').pop() || ''
  return extension.toLowerCase()
}

function getKind(file: FileItem): FileKind {
  if (file.type === 'folder') return 'folder'
  const extension = getExtension(file)
  const mimeType = String(file.mime_type || '').toLowerCase()
  if (mimeType.startsWith('image/') || imageExts.has(extension)) return 'image'
  if (mimeType.startsWith('video/') || videoExts.has(extension)) return 'video'
  if (mimeType.startsWith('audio/') || audioExts.has(extension)) return 'audio'
  if (documentExts.has(extension)) return 'document'
  return 'other'
}

function matchesKind(file: FileItem, filter: FileKindFilter) {
  return filter === 'all' || getKind(file) === filter
}

function matchesSource(file: FileItem, filter: SourceFilter) {
  if (filter === 'all') return true
  if (filter === 'upload') return file.source === 'upload'
  return file.type === 'file' && file.source !== 'upload'
}

function kindCount(filter: FileKindFilter) {
  return files.value.filter((file) => matchesKind(file, filter)).length
}

function sourceCount(filter: SourceFilter) {
  return files.value.filter((file) => matchesSource(file, filter)).length
}

function fileKindLabel(file: FileItem) {
  const labels: Record<FileKind, string> = {
    folder: '目录',
    image: '图片',
    video: '视频',
    audio: '音频',
    document: '文档',
    other: '文件',
  }
  return labels[getKind(file)]
}

function sourceLabel(source: string) {
  if (source === 'upload') return '用户上传'
  if (source === 'generated') return '生成文件'
  if (source === 'agent') return 'Agent 产物'
  if (source === 'workflow') return '工作流产物'
  return source || '-'
}

function storageLabel(provider: string) {
  if (provider === 'local') return '本地'
  if (provider === 'qcloud_cos') return '腾讯 COS'
  if (provider === 'aliyun_oss') return '阿里 OSS'
  return provider || '-'
}

function formatFileSize(size: number) {
  if (!size) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = size
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value >= 10 || unitIndex === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`
}

function formatDate(timestamp: number) {
  if (!timestamp) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp * 1000))
}

watch(
  () => props.createType,
  (value) => {
    if (value === 'file-folder') {
      emit('update:createType', '')
      openCreateFolder()
    }
  },
)

watch(
  () => route.query?.search_word,
  () => loadFiles(),
)

watch([kindFilter, sourceFilter], pruneSelection)

onMounted(loadFiles)
</script>

<template>
  <div v-loading="loading" class="h-full min-h-0 overflow-auto pb-6">
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[220px_minmax(0,1fr)]">
      <aside class="bg-white p-4 ring-1 ring-slate-200">
        <div class="text-xs font-medium uppercase text-gray-400">类型</div>
        <div class="mt-2 space-y-1">
          <button
            v-for="item in kindFilters"
            :key="item.value"
            :class="[
              'flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm transition-colors',
              kindFilter === item.value ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-slate-50',
            ]"
            @click="kindFilter = item.value"
          >
            <span>{{ item.label }}</span>
            <span class="text-xs text-gray-400">{{ kindCount(item.value) }}</span>
          </button>
        </div>

        <div class="mt-6 text-xs font-medium uppercase text-gray-400">来源</div>
        <div class="mt-2 space-y-1">
          <button
            v-for="item in sourceFilters"
            :key="item.value"
            :class="[
              'flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm transition-colors',
              sourceFilter === item.value ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-slate-50',
            ]"
            @click="sourceFilter = item.value"
          >
            <span>{{ item.label }}</span>
            <span class="text-xs text-gray-400">{{ sourceCount(item.value) }}</span>
          </button>
        </div>

        <div class="mt-6 space-y-2 border-t border-slate-100 pt-4 text-sm">
          <div class="flex items-center justify-between text-gray-500">
            <span>文件</span>
            <span class="font-medium text-gray-900">{{ fileCount }}</span>
          </div>
          <div class="flex items-center justify-between text-gray-500">
            <span>目录</span>
            <span class="font-medium text-gray-900">{{ folderCount }}</span>
          </div>
          <div class="flex items-center justify-between text-gray-500">
            <span>生成文件</span>
            <span class="font-medium text-gray-900">{{ generatedCount }}</span>
          </div>
          <div class="flex items-center justify-between text-gray-500">
            <span>容量</span>
            <span class="font-medium text-gray-900">{{ formatFileSize(totalSize) }}</span>
          </div>
        </div>
      </aside>

      <main class="min-w-0 bg-white p-4 ring-1 ring-slate-200">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <el-breadcrumb separator="/">
              <el-breadcrumb-item v-for="(item, index) in pathStack" :key="item.id || 'root'">
                <button
                  class="max-w-[180px] truncate align-bottom text-sm text-gray-600 hover:text-blue-700"
                  @click="goToPath(index)"
                >
                  {{ item.name }}
                </button>
              </el-breadcrumb-item>
            </el-breadcrumb>
            <div class="mt-2 flex flex-wrap items-center gap-2">
              <h2 class="truncate text-base font-semibold text-gray-900">{{ currentDirectoryName }}</h2>
              <el-tag v-if="searchWord" closable size="small" @close="clearSearch">搜索：{{ searchWord }}</el-tag>
            </div>
          </div>

          <div class="flex shrink-0 flex-wrap items-center gap-2">
            <el-button :disabled="pathStack.length <= 1" @click="goParent">返回上级</el-button>
            <el-button @click="openCreateFolder">
              <template #icon><icon-plus /></template>
              新建目录
            </el-button>
            <el-upload :show-file-list="false" :http-request="handleUpload">
              <el-button type="primary">
                <template #icon><icon-plus /></template>
                上传文件
              </el-button>
            </el-upload>
          </div>
        </div>

        <div class="mt-4 flex flex-wrap items-center justify-between gap-3 border-y border-slate-100 bg-slate-50 px-3 py-2">
          <div class="flex flex-wrap items-center gap-3">
            <el-checkbox
              :model-value="allVisibleSelected"
              :indeterminate="isIndeterminate"
              :disabled="!filteredFiles.length"
              @change="toggleSelectAll"
            >
              本页全选
            </el-checkbox>
            <span class="text-xs text-gray-500">已选 {{ selectedIds.length }} / {{ filteredFiles.length }}</span>
            <el-button size="small" :disabled="!selectedIds.length" @click="openMoveDialog()">移动</el-button>
            <el-button size="small" type="danger" plain :disabled="!selectedIds.length" @click="removeSelectedFiles">
              删除
            </el-button>
          </div>

          <div class="flex items-center gap-1">
            <el-tooltip content="列表视图" placement="top">
              <el-button :type="viewMode === 'table' ? 'primary' : 'default'" size="small" @click="viewMode = 'table'">
                <template #icon><icon-list /></template>
              </el-button>
            </el-tooltip>
            <el-tooltip content="平铺视图" placement="top">
              <el-button :type="viewMode === 'grid' ? 'primary' : 'default'" size="small" @click="viewMode = 'grid'">
                <template #icon><icon-apps /></template>
              </el-button>
            </el-tooltip>
            <el-tooltip content="刷新" placement="top">
              <el-button size="small" @click="loadFiles">
                <template #icon><icon-sync /></template>
              </el-button>
            </el-tooltip>
          </div>
        </div>

        <el-table v-if="viewMode === 'table' && filteredFiles.length" :data="filteredFiles" stripe class="w-full">
          <el-table-column width="48">
            <template #default="{ row }">
              <el-checkbox :model-value="isSelected(row)" @change="toggleSelect(row, $event)" />
            </template>
          </el-table-column>
          <el-table-column label="名称" min-width="280">
            <template #default="{ row }">
              <button class="flex min-w-0 items-center gap-2 text-left" @click="previewFile(row)">
                <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-slate-100 text-lg">
                  <icon-storage v-if="row.type === 'folder'" class="text-blue-600" />
                  <icon-empty v-else-if="getKind(row) === 'image'" class="text-emerald-600" />
                  <icon-play-circle v-else-if="getKind(row) === 'video'" class="text-rose-600" />
                  <icon-voice v-else-if="getKind(row) === 'audio'" class="text-violet-600" />
                  <icon-file v-else class="text-gray-500" />
                </span>
                <span class="min-w-0">
                  <span class="block truncate text-sm font-medium text-gray-900">{{ row.name }}</span>
                  <span class="block truncate text-xs text-gray-500">{{ row.file_path || row.mime_type || '-' }}</span>
                </span>
              </button>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag size="small" type="info">{{ fileKindLabel(row) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="120">
            <template #default="{ row }">{{ sourceLabel(row.source) }}</template>
          </el-table-column>
          <el-table-column label="Storage" width="120">
            <template #default="{ row }">{{ row.type === 'folder' ? '-' : storageLabel(row.storage_provider) }}</template>
          </el-table-column>
          <el-table-column label="大小" width="110">
            <template #default="{ row }">{{ row.type === 'folder' ? '-' : formatFileSize(row.size) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link @click="previewFile(row)">{{ row.type === 'folder' ? '打开' : '预览' }}</el-button>
              <el-button v-if="row.type === 'file'" type="primary" link @click="downloadFile(row)">下载</el-button>
              <el-button type="primary" link @click="openMoveDialog(row)">移动</el-button>
              <el-button type="primary" link @click="openRename(row)">重命名</el-button>
              <el-button type="danger" link @click="removeFile(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-else-if="viewMode === 'grid' && filteredFiles.length" class="mt-4 grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
          <article
            v-for="file in filteredFiles"
            :key="file.id"
            :class="[
              'rounded-md border bg-white p-3 transition-colors',
              isSelected(file) ? 'border-blue-300 bg-blue-50' : 'border-slate-200 hover:border-blue-200',
            ]"
          >
            <div class="flex items-center justify-between gap-2">
              <el-checkbox :model-value="isSelected(file)" @change="toggleSelect(file, $event)" />
              <el-tag size="small" type="info">{{ fileKindLabel(file) }}</el-tag>
            </div>

            <button class="mt-2 block w-full text-left" @click="previewFile(file)">
              <span class="flex aspect-[4/3] w-full items-center justify-center overflow-hidden rounded-md bg-slate-50 ring-1 ring-slate-200">
                <el-image
                  v-if="getKind(file) === 'image' && file.preview_url"
                  class="h-full w-full"
                  fit="cover"
                  :src="file.preview_url"
                />
                <icon-storage v-else-if="file.type === 'folder'" class="text-4xl text-blue-600" />
                <icon-play-circle v-else-if="getKind(file) === 'video'" class="text-4xl text-rose-600" />
                <icon-voice v-else-if="getKind(file) === 'audio'" class="text-4xl text-violet-600" />
                <icon-file v-else class="text-4xl text-gray-500" />
              </span>
              <span class="mt-2 block truncate text-sm font-medium text-gray-900">{{ file.name }}</span>
              <span class="mt-1 block truncate text-xs text-gray-500">
                {{ sourceLabel(file.source) }} · {{ file.type === 'folder' ? '目录' : formatFileSize(file.size) }}
              </span>
            </button>

            <div class="mt-3 flex flex-wrap items-center gap-1">
              <el-button size="small" link type="primary" @click="previewFile(file)">
                {{ file.type === 'folder' ? '打开' : '预览' }}
              </el-button>
              <el-button v-if="file.type === 'file'" size="small" link type="primary" @click="downloadFile(file)">下载</el-button>
              <el-button size="small" link type="primary" @click="openMoveDialog(file)">移动</el-button>
              <el-button size="small" link type="primary" @click="openRename(file)">重命名</el-button>
              <el-button size="small" link type="danger" @click="removeFile(file)">删除</el-button>
            </div>
          </article>
        </div>

        <el-empty v-else class="py-16" :description="searchWord ? '没有匹配的文件' : '当前目录暂无文件'">
          <el-upload :show-file-list="false" :http-request="handleUpload">
            <el-button type="primary">
              <template #icon><icon-plus /></template>
              上传文件
            </el-button>
          </el-upload>
        </el-empty>
      </main>
    </div>

    <el-dialog v-model="renameDialogVisible" width="420px" title="重命名">
      <el-input v-model="editingName" />
      <template #footer>
        <el-button @click="renameDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRename">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="moveDialogVisible" width="480px" title="移动到目录">
      <el-form label-position="top">
        <el-form-item label="目标目录">
          <el-select v-model="moveTargetId" class="w-full" :loading="moveTargetLoading">
            <el-option v-for="target in moveTargets" :key="target.id || 'root'" :label="target.name" :value="target.id">
              <div :style="{ paddingLeft: `${target.depth * 14}px` }">{{ target.name }}</div>
            </el-option>
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="moveDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="moveTargetLoading" @click="saveMove">移动</el-button>
      </template>
    </el-dialog>
  </div>
</template>
