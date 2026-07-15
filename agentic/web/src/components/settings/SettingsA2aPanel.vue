<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Loader2, Plus, RotateCcw, Trash } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { configApi } from '@/lib/api/config'
import type { ListA2AServerItem } from '@/lib/api/types'

const toast = useToast()
const servers = ref<ListA2AServerItem[]>([])
const loading = ref(true)
const loadError = ref('')
const dialogOpen = ref(false)
const baseUrl = ref('')
const adding = ref(false)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const data = await configApi.getA2AServers()
    servers.value = data?.a2a_servers ?? []
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : 'A2A Agent 加载失败'
  } finally { loading.value = false }
}

onMounted(load)

async function toggle(id: string, enabled: boolean) {
  const previous = servers.value
  const target = previous.find((server) => server.id === id)
  servers.value = servers.value.map((server) => server.id === id ? { ...server, enabled } : server)
  try {
    await configApi.updateA2AServerEnabled(id, enabled)
    toast.success(`${target?.name ?? 'Agent'} 已${enabled ? '启用' : '禁用'}`)
  } catch {
    servers.value = previous
    toast.error('操作失败，请重试')
  }
}

async function deleteServer(server: ListA2AServerItem) {
  try {
    await ElMessageBox.confirm(
      `删除后将不能再把任务委派给「${server.name}」，历史运行记录不会被删除。`,
      '删除 A2A Agent？',
      { confirmButtonText: '删除 Agent', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' },
    )
  } catch { return }

  const previous = servers.value
  servers.value = servers.value.filter((item) => item.id !== server.id)
  try {
    await configApi.deleteA2AServer(server.id)
    toast.success(`已删除 A2A Agent「${server.name}」`)
  } catch {
    servers.value = previous
    toast.error('删除失败，请重试')
  }
}

async function addServer() {
  const url = baseUrl.value.trim()
  if (!url) { toast.error('请输入远程 Agent 地址'); return }
  adding.value = true
  try {
    await configApi.addA2AServer({ base_url: url })
    await load()
    baseUrl.value = ''
    dialogOpen.value = false
    toast.success('远程 Agent 添加成功')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '添加失败')
  } finally { adding.value = false }
}

function isDirty() { return false }
async function save() { return true }
defineExpose({ isDirty, save })
</script>

<template>
  <section class="settings-list">
    <header class="settings-section-heading">
      <div><span>外部连接</span><h3>A2A Agent</h3></div>
      <p>连接标准 A2A 协议的远程 Agent；启停操作会立即生效。</p>
      <ElButton type="primary" size="small" @click="dialogOpen = true"><Plus :size="14" />添加远程 Agent</ElButton>
    </header>
    <div v-if="loading" class="center-state" aria-live="polite"><Loader2 :size="22" class="spin" /><span>正在加载 A2A Agent</span></div>
    <div v-else-if="loadError" class="settings-error-state" role="alert"><p>{{ loadError }}</p><ElButton @click="load"><RotateCcw :size="15" />重试</ElButton></div>
    <ElEmpty v-else-if="servers.length === 0" description="暂无 A2A Agent" />
    <article v-for="server in servers" v-else :key="server.id" class="settings-card settings-connection-card">
      <div class="settings-card-title">
        <strong>{{ server.name }}</strong>
        <ElTag v-if="!server.enabled" size="small" type="info" effect="plain">禁用</ElTag>
        <div class="settings-card-actions">
          <ElButton text type="danger" size="small" :aria-label="`删除 ${server.name}`" @click="deleteServer(server)"><Trash :size="14" /></ElButton>
          <ElSwitch :model-value="server.enabled" inline-prompt active-text="开" inactive-text="关" :aria-label="`${server.name} 启用状态`" @change="toggle(server.id, Boolean($event))" />
        </div>
      </div>
      <p v-if="server.description">{{ server.description }}</p>
      <div class="badge-row">
        <ElTag v-for="mode in server.input_modes || []" :key="`in-${mode}`" size="small" effect="plain">输入: {{ mode }}</ElTag>
        <ElTag v-for="mode in server.output_modes || []" :key="`out-${mode}`" size="small" effect="plain">输出: {{ mode }}</ElTag>
        <ElTag size="small" effect="plain">流式输出: {{ server.streaming ? '开启' : '关闭' }}</ElTag>
        <ElTag size="small" effect="plain">推送通知: {{ server.push_notifications ? '开启' : '关闭' }}</ElTag>
      </div>
    </article>
  </section>

  <ElDialog v-model="dialogOpen" width="min(560px, calc(100vw - 24px))" append-to-body align-center class="settings-sub-dialog" :show-close="!adding" :close-on-click-modal="!adding" :close-on-press-escape="!adding" title="添加远程 Agent">
    <ElForm label-position="top" class="settings-form compact"><ElFormItem label="远程 Agent 地址"><ElInput v-model="baseUrl" placeholder="https://example.com/weather-agent" clearable /></ElFormItem></ElForm>
    <template #footer><ElButton :disabled="adding" @click="dialogOpen = false">取消</ElButton><ElButton type="primary" :loading="adding" @click="addServer">添加</ElButton></template>
  </ElDialog>
</template>
