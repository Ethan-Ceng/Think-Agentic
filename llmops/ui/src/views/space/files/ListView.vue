<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { UploadRequestOptions } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FileItem } from '@/models/file'
import { createFolder, deleteFile, getFiles, updateFile, uploadManagedFile } from '@/services/file'

const props = defineProps<{ createType?: string }>()
const emit = defineEmits(['update:createType'])

const loading = ref(false)
const files = ref<FileItem[]>([])
const currentParentId = ref<string | null>(null)
const renameDialogVisible = ref(false)
const editingFile = ref<FileItem | null>(null)
const editingName = ref('')

const loadFiles = async () => {
  loading.value = true
  try {
    const res = await getFiles({ parent_id: currentParentId.value || undefined })
    files.value = res.data
  } finally {
    loading.value = false
  }
}

const openCreateFolder = async () => {
  const { value } = await ElMessageBox.prompt('目录名称', '新建目录', {
    inputPlaceholder: '请输入目录名称',
  })
  await createFolder({ name: String(value || ''), parent_id: currentParentId.value })
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
  await loadFiles()
}

const removeFile = async (file: FileItem) => {
  await ElMessageBox.confirm(`删除 ${file.name}？`, '确认删除', { type: 'warning' })
  await deleteFile(file.id)
  await loadFiles()
}

const openFolder = async (file: FileItem) => {
  if (file.type !== 'folder') return
  currentParentId.value = file.id
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

watch(
  () => props.createType,
  (value) => {
    if (value === 'file-folder') {
      emit('update:createType', '')
      openCreateFolder()
    }
  },
)

onMounted(loadFiles)
</script>

<template>
  <div v-loading="loading" class="h-full overflow-auto px-1 pb-6">
    <div class="mb-3 flex items-center justify-between">
      <div class="text-sm text-gray-500">
        当前目录：{{ currentParentId ? currentParentId : '根目录' }}
      </div>
      <div class="flex gap-2">
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

    <el-table :data="files" stripe class="w-full">
      <el-table-column label="名称" min-width="260">
        <template #default="{ row }">
          <button
            class="flex min-w-0 items-center gap-2 text-left"
            @click="openFolder(row)"
          >
            <icon-storage v-if="row.type === 'folder'" class="text-blue-600" />
            <icon-file v-else class="text-gray-500" />
            <span class="truncate text-sm text-gray-900">{{ row.name }}</span>
          </button>
        </template>
      </el-table-column>
      <el-table-column prop="storage_provider" label="Storage" width="130" />
      <el-table-column label="大小" width="120">
        <template #default="{ row }">
          {{ row.type === 'folder' ? '-' : `${(row.size / 1024).toFixed(1)} KB` }}
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="120" />
      <el-table-column label="操作" width="210" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openRename(row)">重命名</el-button>
          <a v-if="row.type === 'file' && row.download_url" :href="row.download_url" target="_blank">
            <el-button type="primary" link>下载</el-button>
          </a>
          <el-button type="danger" link @click="removeFile(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="currentParentId" class="mt-4">
      <el-button @click="currentParentId = null; loadFiles()">返回根目录</el-button>
    </div>

    <el-dialog v-model="renameDialogVisible" width="420px" title="重命名">
      <el-input v-model="editingName" />
      <template #footer>
        <el-button @click="renameDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRename">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
