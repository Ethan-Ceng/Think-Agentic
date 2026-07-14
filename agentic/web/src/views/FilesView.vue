<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { ArrowLeft, Download, File, FilePlus2, Folder, FolderPlus, Grid2X2, List, PanelLeftOpen, RefreshCw, Search, Trash2 } from 'lucide-vue-next'
import SettingsButton from '@/components/SettingsButton.vue'
import UserMenu from '@/components/UserMenu.vue'
import { useSidebar } from '@/composables/useSidebar'
import { useToast } from '@/composables/useToast'
import { fileApi } from '@/lib/api/file'
import type { FolderTreeItem, ManagedFile } from '@/lib/api/types'
import { downloadBlob, formatFileSize } from '@/lib/utils'

type PathNode = { id: string | null; name: string }
const sidebar = useSidebar()
const toast = useToast()
const loading = ref(false)
const files = ref<ManagedFile[]>([])
const viewMode = ref<'table' | 'grid'>('table')
const path = ref<PathNode[]>([{ id: null, name: '全部文件' }])
const searchWord = ref('')
const fileKind = ref('all')
const sourceType = ref('all')
const selectedIds = ref<string[]>([])
const uploadInput = ref<HTMLInputElement | null>(null)
const paginator = ref({ current_page: 1, page_size: 20, total_page: 0, total_record: 0 })
const moveDialogOpen = ref(false)
const moveTargets = ref<FolderTreeItem[]>([])
const moveTargetId = ref('')
const currentParentId = computed(() => path.value.at(-1)?.id ?? null)
const selectedFiles = computed(() => files.value.filter((file) => selectedIds.value.includes(file.id)))

async function loadFiles(page = 1) {
  loading.value = true
  try {
    const data = await fileApi.listFiles({
      parent_id: currentParentId.value || undefined,
      search_word: searchWord.value || undefined,
      file_kind: fileKind.value,
      source_type: sourceType.value,
      current_page: page,
      page_size: paginator.value.page_size,
    })
    files.value = data.list
    paginator.value = data.paginator
    selectedIds.value = selectedIds.value.filter((id) => files.value.some((file) => file.id === id))
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '文件加载失败')
  } finally {
    loading.value = false
  }
}

async function openFolder(file: ManagedFile) {
  if (file.type !== 'folder') return
  path.value.push({ id: file.id, name: file.name })
  selectedIds.value = []
  await loadFiles(1)
}

async function goPath(index: number) {
  path.value = path.value.slice(0, index + 1)
  await loadFiles(1)
}

async function createFolder() {
  try {
    const { value } = await ElMessageBox.prompt('请输入目录名称', '新建目录', { inputPattern: /\S+/, inputErrorMessage: '目录名称不能为空' })
    await fileApi.createFolder(String(value), currentParentId.value)
    toast.success('目录已创建')
    await loadFiles(1)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') toast.error(error instanceof Error ? error.message : '目录创建失败')
  }
}

async function uploadFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files || [])
  if (!selected.length) return
  loading.value = true
  try {
    for (const file of selected) await fileApi.uploadFile({ file, parent_id: currentParentId.value })
    toast.success(`${selected.length} 个文件已上传`)
    await loadFiles(1)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '上传失败')
  } finally {
    input.value = ''
    loading.value = false
  }
}

async function preview(file: ManagedFile) {
  if (file.type === 'folder') return openFolder(file)
  try {
    const blob = await fileApi.previewFile(file.id)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener,noreferrer')
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '预览失败')
  }
}

async function download(file: ManagedFile) {
  try {
    downloadBlob(await fileApi.downloadFile(file.id), file.name)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '下载失败')
  }
}

async function rename(file: ManagedFile) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新名称', '重命名', { inputValue: file.name, inputPattern: /\S+/, inputErrorMessage: '名称不能为空' })
    await fileApi.updateFile(file.id, { name: String(value) })
    await loadFiles(paginator.value.current_page)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') toast.error(error instanceof Error ? error.message : '重命名失败')
  }
}

async function openMove(file?: ManagedFile) {
  if (file) selectedIds.value = [file.id]
  if (!selectedIds.value.length) return
  moveTargets.value = await fileApi.listFolders()
  moveTargetId.value = currentParentId.value || ''
  moveDialogOpen.value = true
}

async function saveMove() {
  await fileApi.batchMove(selectedIds.value, moveTargetId.value || null)
  moveDialogOpen.value = false
  selectedIds.value = []
  toast.success('文件已移动')
  await loadFiles(paginator.value.current_page)
}

async function remove(targets: ManagedFile[]) {
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(`删除选中的 ${targets.length} 项？文件将立即不可访问，并在 7 天后清理物理对象。`, '确认删除', { type: 'warning' })
    await fileApi.batchDelete(targets.map((file) => file.id))
    selectedIds.value = []
    toast.success('文件已删除')
    await loadFiles(paginator.value.current_page)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') toast.error(error instanceof Error ? error.message : '删除失败')
  }
}

function sourceLabel(value: ManagedFile['source_type']) { return value === 'agent_generated' ? 'AI 生成' : '用户上传' }
function providerLabel(value: ManagedFile['storage_provider']) { return value === 'aliyun_oss' ? '阿里云 OSS' : value === 'qcloud_cos' ? '腾讯 COS' : '本地' }
function formatDate(value: number) { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value * 1000)) }

let searchTimer = 0
watch([fileKind, sourceType], () => void loadFiles(1))
watch(searchWord, () => { window.clearTimeout(searchTimer); searchTimer = window.setTimeout(() => void loadFiles(1), 300) })
onMounted(() => loadFiles(1))
</script>

<template>
  <div class="files-page">
    <header class="files-header">
      <div class="files-header-left">
        <button v-if="!sidebar.open.value" class="icon-button" type="button" @click="sidebar.openSidebar"><PanelLeftOpen :size="18" /></button>
        <div><h1>文件</h1><p>统一管理用户上传与 AI 生成的交付文件</p></div>
      </div>
      <div class="header-actions"><SettingsButton /><UserMenu /></div>
    </header>

    <main class="files-main" v-loading="loading">
      <aside class="files-filter-panel">
        <h3>文件类型</h3>
        <button v-for="item in [{v:'all',l:'全部'},{v:'image',l:'图片'},{v:'video',l:'视频'},{v:'audio',l:'音频'},{v:'document',l:'文档'},{v:'other',l:'其他'}]" :key="item.v" :class="{ active: fileKind === item.v }" @click="fileKind = item.v">{{ item.l }}</button>
        <h3>来源</h3>
        <button v-for="item in [{v:'all',l:'全部来源'},{v:'user_upload',l:'用户上传'},{v:'agent_generated',l:'AI 生成'}]" :key="item.v" :class="{ active: sourceType === item.v }" @click="sourceType = item.v">{{ item.l }}</button>
      </aside>

      <section class="files-content">
        <div class="files-toolbar">
          <div class="files-breadcrumb">
            <button v-if="path.length > 1" class="icon-button subtle" @click="goPath(path.length - 2)"><ArrowLeft :size="17" /></button>
            <template v-for="(node, index) in path" :key="node.id || 'root'"><button @click="goPath(index)">{{ node.name }}</button><span v-if="index < path.length - 1">/</span></template>
          </div>
          <div class="files-actions">
            <button class="button" @click="createFolder"><FolderPlus :size="16" />新建目录</button>
            <button class="button primary" @click="uploadInput?.click()"><FilePlus2 :size="16" />上传文件</button>
            <input ref="uploadInput" hidden multiple type="file" @change="uploadFiles">
          </div>
        </div>

        <div class="files-subtoolbar">
          <label class="files-search"><Search :size="15" /><input v-model="searchWord" placeholder="搜索当前目录"></label>
          <div class="files-selection"><span>已选 {{ selectedIds.length }} 项</span><button :disabled="!selectedIds.length" @click="openMove()">移动</button><button :disabled="!selectedIds.length" @click="remove(selectedFiles)">删除</button></div>
          <div><button class="icon-button subtle" @click="viewMode = 'table'"><List :size="17" /></button><button class="icon-button subtle" @click="viewMode = 'grid'"><Grid2X2 :size="17" /></button><button class="icon-button subtle" @click="loadFiles(paginator.current_page)"><RefreshCw :size="17" /></button></div>
        </div>

        <div v-if="!files.length" class="files-empty"><Folder :size="44" /><h3>当前目录暂无文件</h3><p>上传文件或新建目录开始使用。</p></div>

        <div v-else-if="viewMode === 'table'" class="files-table-wrap">
          <table class="files-table"><thead><tr><th></th><th>名称</th><th>来源</th><th>存储</th><th>大小</th><th>更新时间</th><th>操作</th></tr></thead><tbody>
            <tr v-for="file in files" :key="file.id">
              <td><input v-model="selectedIds" type="checkbox" :value="file.id"></td>
              <td><button class="file-name" @click="preview(file)"><Folder v-if="file.type === 'folder'" :size="20" /><File v-else :size="20" /><span>{{ file.name }}</span></button></td>
              <td>{{ file.type === 'folder' ? '-' : sourceLabel(file.source_type) }}</td><td>{{ file.type === 'folder' ? '-' : providerLabel(file.storage_provider) }}</td><td>{{ file.type === 'folder' ? '-' : formatFileSize(file.size) }}</td><td>{{ formatDate(file.updated_at) }}</td>
              <td class="file-row-actions"><button @click="preview(file)">{{ file.type === 'folder' ? '打开' : '预览' }}</button><button v-if="file.type === 'file'" @click="download(file)"><Download :size="14" /></button><button @click="openMove(file)">移动</button><button @click="rename(file)">重命名</button><button @click="remove([file])"><Trash2 :size="14" /></button></td>
            </tr>
          </tbody></table>
        </div>

        <div v-else class="files-grid"><article v-for="file in files" :key="file.id" :class="{ selected: selectedIds.includes(file.id) }"><input v-model="selectedIds" type="checkbox" :value="file.id"><button class="file-grid-main" @click="preview(file)"><Folder v-if="file.type === 'folder'" :size="42" /><File v-else :size="42" /><strong>{{ file.name }}</strong><small>{{ file.type === 'folder' ? '目录' : `${sourceLabel(file.source_type)} · ${formatFileSize(file.size)}` }}</small></button></article></div>

        <ElPagination v-if="paginator.total_record" v-model:current-page="paginator.current_page" v-model:page-size="paginator.page_size" class="files-pagination" :total="paginator.total_record" :page-sizes="[20,50,100]" layout="total, sizes, prev, pager, next" @current-change="loadFiles" @size-change="loadFiles(1)" />
      </section>
    </main>

    <ElDialog v-model="moveDialogOpen" title="移动到目录" width="460px"><ElSelect v-model="moveTargetId" class="w-full"><ElOption label="全部文件" value="" /><ElOption v-for="folder in moveTargets" :key="folder.id" :label="`${'　'.repeat(folder.depth - 1)}${folder.name}`" :value="folder.id" /></ElSelect><template #footer><ElButton @click="moveDialogOpen = false">取消</ElButton><ElButton type="primary" @click="saveMove">移动</ElButton></template></ElDialog>
  </div>
</template>

<style scoped>
.files-page { height: 100%; display: flex; flex-direction: column; min-width: 0; }
.files-header { height: 64px; flex: 0 0 64px; display: flex; align-items: center; justify-content: space-between; padding: 0 22px; border-bottom: 1px solid #e5e7eb; background: #fff; }
.files-header-left, .header-actions, .files-actions, .files-subtoolbar, .files-breadcrumb, .files-selection { display: flex; align-items: center; gap: 10px; }
.files-header h1 { font-size: 17px; }.files-header p { color: #6b7280; font-size: 12px; }
.files-main { flex: 1; min-height: 0; display: grid; grid-template-columns: 190px minmax(0,1fr); gap: 16px; padding: 16px; overflow: hidden; }
.files-filter-panel, .files-content { border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; }
.files-filter-panel { padding: 14px; overflow: auto; }.files-filter-panel h3 { margin: 8px 8px 6px; color: #9ca3af; font-size: 11px; text-transform: uppercase; }.files-filter-panel button { width: 100%; padding: 8px; border-radius: 6px; background: transparent; text-align: left; cursor: pointer; }.files-filter-panel button.active { background: #f3f4f6; color: #111827; font-weight: 600; }
.files-content { min-width: 0; display: flex; flex-direction: column; overflow: hidden; }.files-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px; border-bottom: 1px solid #e5e7eb; }.files-breadcrumb button { padding: 3px; background: transparent; cursor: pointer; color: #374151; }.files-subtoolbar { justify-content: space-between; padding: 9px 14px; background: #f9fafb; border-bottom: 1px solid #e5e7eb; font-size: 12px; }.files-search { display: flex; align-items: center; gap: 7px; width: min(300px, 100%); padding: 6px 9px; border: 1px solid #d9dde4; border-radius: 7px; background: #fff; }.files-search input { width: 100%; border: 0; outline: 0; }.files-selection button, .file-row-actions button { background: transparent; color: #4b5563; cursor: pointer; }.files-selection button:disabled { opacity: .4; cursor: default; }
.files-table-wrap { flex: 1; min-height: 0; overflow: auto; }.files-table { width: 100%; border-collapse: collapse; font-size: 13px; }.files-table th, .files-table td { padding: 11px 12px; border-bottom: 1px solid #eef0f2; text-align: left; white-space: nowrap; }.files-table th { position: sticky; top: 0; background: #fff; color: #6b7280; font-size: 11px; }.file-name { display: flex; align-items: center; gap: 9px; max-width: 340px; background: transparent; cursor: pointer; }.file-name span { overflow: hidden; text-overflow: ellipsis; }.file-row-actions { display: flex; gap: 10px; }
.files-grid { flex: 1; min-height: 0; overflow: auto; display: grid; grid-template-columns: repeat(auto-fill,minmax(170px,1fr)); align-content: start; gap: 12px; padding: 14px; }.files-grid article { position: relative; padding: 12px; border: 1px solid #e5e7eb; border-radius: 8px; }.files-grid article.selected { border-color: #111827; }.files-grid article > input { position: absolute; top: 10px; right: 10px; }.file-grid-main { width: 100%; min-height: 130px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; background: transparent; cursor: pointer; }.file-grid-main strong { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.file-grid-main small { color: #6b7280; }
.files-empty { flex: 1; display: grid; place-content: center; justify-items: center; color: #9ca3af; }.files-empty h3 { margin-top: 12px; color: #374151; }.files-empty p { margin-top: 4px; font-size: 13px; }.files-pagination { justify-content: flex-end; padding: 12px 14px; border-top: 1px solid #e5e7eb; }.w-full { width: 100%; }
@media (max-width: 760px) { .files-main { grid-template-columns: 1fr; overflow: auto; }.files-filter-panel { display: none; }.files-content { min-height: 600px; }.files-toolbar, .files-subtoolbar { align-items: flex-start; flex-direction: column; }.files-header p { display: none; } }
</style>
