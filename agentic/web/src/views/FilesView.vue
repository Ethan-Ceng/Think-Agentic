<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { ArrowLeft, Download, File, FilePlus2, Folder, FolderPlus, Grid2X2, List, PanelLeftOpen, RefreshCw, Search, Trash2 } from 'lucide-vue-next'
import SettingsButton from '@/components/SettingsButton.vue'
import UserMenu from '@/components/UserMenu.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import UiState from '@/components/ui/UiState.vue'
import UiTextField from '@/components/ui/UiTextField.vue'
import { useSidebar } from '@/composables/useSidebar'
import { useToast } from '@/composables/useToast'
import { fileApi } from '@/lib/api/file'
import type { FolderTreeItem, ManagedFile } from '@/lib/api/types'
import { downloadBlob, formatFileSize } from '@/lib/utils'

type PathNode = { id: string | null; name: string }
const sidebar = useSidebar()
const toast = useToast()
const loading = ref(false)
const loadError = ref('')
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
  loadError.value = ''
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
    loadError.value = error instanceof Error ? error.message : '文件加载失败'
    toast.error(loadError.value)
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
        <UiIconButton v-if="sidebar.mobile.value && !sidebar.open.value" label="打开侧边栏" @click="sidebar.openSidebar"><PanelLeftOpen :size="18" /></UiIconButton>
        <div><h1>文件</h1><p>统一管理用户上传与 AI 生成的交付文件</p></div>
      </div>
      <div class="header-actions"><SettingsButton /><UserMenu /></div>
    </header>

    <main class="files-main">
      <aside class="files-filter-panel ui-card">
        <h3>文件类型</h3>
        <button v-for="item in [{v:'all',l:'全部'},{v:'image',l:'图片'},{v:'video',l:'视频'},{v:'audio',l:'音频'},{v:'document',l:'文档'},{v:'other',l:'其他'}]" :key="item.v" :class="{ active: fileKind === item.v }" @click="fileKind = item.v">{{ item.l }}</button>
        <h3>来源</h3>
        <button v-for="item in [{v:'all',l:'全部来源'},{v:'user_upload',l:'用户上传'},{v:'agent_generated',l:'AI 生成'}]" :key="item.v" :class="{ active: sourceType === item.v }" @click="sourceType = item.v">{{ item.l }}</button>
      </aside>

      <section class="files-content ui-card" :aria-busy="loading">
        <div class="files-toolbar">
          <div class="files-breadcrumb">
            <UiIconButton v-if="path.length > 1" label="返回上级目录" variant="subtle" @click="goPath(path.length - 2)"><ArrowLeft :size="17" /></UiIconButton>
            <template v-for="(node, index) in path" :key="node.id || 'root'"><button @click="goPath(index)">{{ node.name }}</button><span v-if="index < path.length - 1">/</span></template>
          </div>
          <div class="files-actions">
            <UiButton @click="createFolder"><template #icon><FolderPlus :size="16" /></template>新建目录</UiButton>
            <UiButton variant="primary" @click="uploadInput?.click()"><template #icon><FilePlus2 :size="16" /></template>上传文件</UiButton>
            <input ref="uploadInput" hidden multiple type="file" @change="uploadFiles">
          </div>
        </div>

        <div class="files-subtoolbar">
          <UiTextField v-model="searchWord" label="搜索当前目录" placeholder="搜索当前目录" compact class="files-search"><template #leading><Search :size="15" /></template></UiTextField>
          <div class="files-selection"><span>已选 {{ selectedIds.length }} 项</span><UiButton variant="ghost" size="small" :disabled="!selectedIds.length" @click="openMove()">移动</UiButton><UiButton variant="ghost" size="small" :disabled="!selectedIds.length" @click="remove(selectedFiles)">删除</UiButton></div>
          <div class="files-view-actions"><UiIconButton label="表格视图" variant="subtle" :active="viewMode === 'table'" @click="viewMode = 'table'"><List :size="17" /></UiIconButton><UiIconButton label="网格视图" variant="subtle" :active="viewMode === 'grid'" @click="viewMode = 'grid'"><Grid2X2 :size="17" /></UiIconButton><UiIconButton label="刷新文件" variant="subtle" @click="loadFiles(paginator.current_page)"><RefreshCw :size="17" /></UiIconButton></div>
        </div>

        <UiState v-if="loading && !files.length" kind="loading" title="正在加载文件" description="正在读取当前目录内容。" />
        <UiState v-else-if="loadError && !files.length" kind="error" title="文件加载失败" :description="loadError"><template #actions><UiButton @click="loadFiles(paginator.current_page)">重新加载</UiButton></template></UiState>
        <UiState v-else-if="!files.length" title="当前目录暂无文件" description="上传文件或新建目录开始使用。"><template #icon><Folder :size="28" /></template></UiState>

        <div v-else-if="viewMode === 'table'" class="files-table-wrap">
          <table class="files-table"><thead><tr><th></th><th>名称</th><th>来源</th><th>存储</th><th>大小</th><th>更新时间</th><th>操作</th></tr></thead><tbody>
            <tr v-for="file in files" :key="file.id">
              <td><input v-model="selectedIds" type="checkbox" :value="file.id"></td>
              <td><button class="file-name" @click="preview(file)"><Folder v-if="file.type === 'folder'" :size="20" /><File v-else :size="20" /><span>{{ file.name }}</span></button></td>
              <td>{{ file.type === 'folder' ? '-' : sourceLabel(file.source_type) }}</td><td>{{ file.type === 'folder' ? '-' : providerLabel(file.storage_provider) }}</td><td>{{ file.type === 'folder' ? '-' : formatFileSize(file.size) }}</td><td>{{ formatDate(file.updated_at) }}</td>
              <td class="file-row-actions"><UiButton variant="ghost" size="small" @click="preview(file)">{{ file.type === 'folder' ? '打开' : '预览' }}</UiButton><UiIconButton v-if="file.type === 'file'" :label="`下载 ${file.name}`" variant="subtle" size="tiny" @click="download(file)"><Download :size="14" /></UiIconButton><UiButton variant="ghost" size="small" @click="openMove(file)">移动</UiButton><UiButton variant="ghost" size="small" @click="rename(file)">重命名</UiButton><UiIconButton :label="`删除 ${file.name}`" variant="danger" size="tiny" @click="remove([file])"><Trash2 :size="14" /></UiIconButton></td>
            </tr>
          </tbody></table>
        </div>

        <div v-else class="files-grid"><article v-for="file in files" :key="file.id" class="ui-card" :class="{ selected: selectedIds.includes(file.id) }"><input v-model="selectedIds" type="checkbox" :value="file.id" :aria-label="`选择 ${file.name}`"><button class="file-grid-main" @click="preview(file)"><Folder v-if="file.type === 'folder'" :size="42" /><File v-else :size="42" /><strong>{{ file.name }}</strong><small>{{ file.type === 'folder' ? '目录' : `${sourceLabel(file.source_type)} · ${formatFileSize(file.size)}` }}</small></button></article></div>

        <ElPagination v-if="paginator.total_record" v-model:current-page="paginator.current_page" v-model:page-size="paginator.page_size" class="files-pagination" :total="paginator.total_record" :page-sizes="[20,50,100]" layout="total, sizes, prev, pager, next" @current-change="loadFiles" @size-change="loadFiles(1)" />
      </section>
    </main>

    <ElDialog v-model="moveDialogOpen" title="移动到目录" width="460px"><ElSelect v-model="moveTargetId" class="w-full"><ElOption label="全部文件" value="" /><ElOption v-for="folder in moveTargets" :key="folder.id" :label="`${'　'.repeat(folder.depth - 1)}${folder.name}`" :value="folder.id" /></ElSelect><template #footer><ElButton @click="moveDialogOpen = false">取消</ElButton><ElButton type="primary" @click="saveMove">移动</ElButton></template></ElDialog>
  </div>
</template>

<style scoped>
.files-page { display: flex; height: 100%; min-width: 0; flex-direction: column; background: var(--surface-canvas); }
.files-header { display: flex; height: 64px; flex: 0 0 64px; align-items: center; justify-content: space-between; padding: 0 22px; border-bottom: 1px solid var(--border-light); background: var(--surface-primary); }
.files-header-left, .header-actions, .files-actions, .files-subtoolbar, .files-breadcrumb, .files-selection, .files-view-actions { display: flex; align-items: center; gap: 10px; }
.files-header h1 { color: var(--text-primary); font-size: 17px; }
.files-header p { color: var(--text-tertiary); font-size: var(--text-xs); }
.files-main { display: grid; min-height: 0; flex: 1; grid-template-columns: 190px minmax(0, 1fr); gap: var(--space-4); padding: var(--space-4); overflow: hidden; }
.files-filter-panel { padding: 14px; overflow: auto; box-shadow: none; }
.files-filter-panel h3 { margin: 8px 8px 6px; color: var(--text-tertiary); font-size: 11px; text-transform: uppercase; }
.files-filter-panel button { width: 100%; min-height: 36px; padding: 8px; border-radius: var(--radius-sm); background: transparent; color: var(--text-secondary); cursor: pointer; text-align: left; }
.files-filter-panel button:hover { background: var(--surface-hover); color: var(--text-primary); }
.files-filter-panel button:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.files-filter-panel button.active { background: var(--accent-soft); color: var(--accent-primary); font-weight: 650; }
.files-content { display: flex; min-width: 0; flex-direction: column; overflow: hidden; box-shadow: none; }
.files-toolbar { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: 14px; border-bottom: 1px solid var(--border-light); }
.files-breadcrumb button { padding: 3px; background: transparent; color: var(--text-secondary); cursor: pointer; }
.files-breadcrumb button:hover { color: var(--text-primary); }
.files-subtoolbar { justify-content: space-between; padding: 9px 14px; border-bottom: 1px solid var(--border-light); background: var(--surface-secondary); color: var(--text-secondary); font-size: var(--text-xs); }
.files-search { width: min(300px, 100%); }
.files-table-wrap { min-height: 0; flex: 1; overflow: auto; }
.files-table { width: 100%; border-collapse: collapse; color: var(--text-primary); font-size: var(--text-sm); }
.files-table th, .files-table td { padding: 11px 12px; border-bottom: 1px solid var(--border-light); text-align: left; white-space: nowrap; }
.files-table th { position: sticky; top: 0; z-index: 1; background: var(--surface-primary); color: var(--text-secondary); font-size: 11px; }
.file-name { display: flex; max-width: 340px; align-items: center; gap: 9px; background: transparent; color: var(--text-primary); cursor: pointer; }
.file-name:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.file-name span { overflow: hidden; text-overflow: ellipsis; }
.file-row-actions { display: flex; align-items: center; gap: 4px; }
.files-grid { display: grid; min-height: 0; flex: 1; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); align-content: start; gap: var(--space-3); padding: 14px; overflow: auto; }
.files-grid article { position: relative; padding: var(--space-3); box-shadow: none; }
.files-grid article:hover { border-color: var(--border-medium); box-shadow: var(--shadow-sm); }
.files-grid article.selected { border-color: var(--accent-primary); background: var(--accent-soft); }
.files-grid article > input { position: absolute; top: 10px; right: 10px; }
.file-grid-main { display: flex; width: 100%; min-height: 130px; flex-direction: column; align-items: center; justify-content: center; gap: var(--space-2); background: transparent; color: var(--text-primary); cursor: pointer; }
.file-grid-main strong { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-grid-main small { color: var(--text-secondary); }
.files-pagination { justify-content: flex-end; padding: 12px 14px; border-top: 1px solid var(--border-light); }
.w-full { width: 100%; }
@media (max-width: 760px) { .files-main { grid-template-columns: 1fr; overflow: auto; }.files-filter-panel { display: none; }.files-content { min-height: 600px; }.files-toolbar, .files-subtoolbar { align-items: flex-start; flex-direction: column; }.files-actions, .files-search, .files-view-actions { width: 100%; }.files-actions > * { flex: 1; }.files-view-actions { justify-content: flex-end; }.files-header p { display: none; } }
</style>
