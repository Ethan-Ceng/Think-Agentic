<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Loader2, Plus, RotateCcw, Trash, Wrench } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { configApi } from '@/lib/api/config'
import type { ListMCPServerItem, MCPConfig } from '@/lib/api/types'

const toast = useToast()
const servers = ref<ListMCPServerItem[]>([])
const loading = ref(true)
const loadError = ref('')
const dialogOpen = ref(false)
const configText = ref('')
const adding = ref(false)

const placeholder = `{
  "mcpServers": {
    "qiniu": {
      "command": "uvx",
      "args": ["qiniu-mcp-server"],
      "env": {
        "QINIU_ACCESS_KEY": "YOUR_ACCESS_KEY",
        "QINIU_SECRET_KEY": "YOUR_SECRET_KEY"
      }
    }
  }
}`

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const data = await configApi.getMCPServers()
    servers.value = data?.mcp_servers ?? []
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : 'MCP 服务器加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function toggle(serverName: string, enabled: boolean) {
  const previous = servers.value
  servers.value = servers.value.map((server) => server.server_name === serverName ? { ...server, enabled } : server)
  try {
    await configApi.updateMCPServerEnabled(serverName, enabled)
    toast.success(`${serverName} 已${enabled ? '启用' : '禁用'}`)
  } catch {
    servers.value = previous
    toast.error('操作失败，请重试')
  }
}

async function deleteServer(serverName: string) {
  try {
    await ElMessageBox.confirm(
      `删除后，依赖「${serverName}」的任务将无法再调用其工具。此操作不会删除历史运行记录。`,
      '删除 MCP 服务器？',
      { confirmButtonText: '删除服务器', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' },
    )
  } catch { return }

  const previous = servers.value
  servers.value = servers.value.filter((server) => server.server_name !== serverName)
  try {
    await configApi.deleteMCPServer(serverName)
    toast.success(`已删除 MCP 服务器「${serverName}」`)
  } catch {
    servers.value = previous
    toast.error('删除失败，请重试')
  }
}

async function addServer() {
  if (!configText.value.trim()) {
    toast.error('请输入 MCP 服务器配置')
    return
  }
  adding.value = true
  try {
    const parsed = JSON.parse(configText.value) as MCPConfig
    await configApi.addMCPServer(parsed)
    await load()
    configText.value = ''
    dialogOpen.value = false
    toast.success('MCP 服务器添加成功')
  } catch (error) {
    toast.error(error instanceof SyntaxError ? 'JSON 格式错误，请检查配置' : error instanceof Error ? error.message : '添加失败')
  } finally {
    adding.value = false
  }
}

function isDirty() { return false }
async function save() { return true }
defineExpose({ isDirty, save })
</script>

<template>
  <section class="settings-list">
    <header class="settings-section-heading">
      <div><span>外部连接</span><h3>MCP 服务器</h3></div>
      <p>通过 MCP 服务扩展工具能力；启停操作会立即生效。</p>
      <ElButton type="primary" size="small" @click="dialogOpen = true"><Plus :size="14" />添加服务器</ElButton>
    </header>
    <div v-if="loading" class="center-state" aria-live="polite"><Loader2 :size="22" class="spin" /><span>正在加载 MCP 服务器</span></div>
    <div v-else-if="loadError" class="settings-error-state" role="alert"><p>{{ loadError }}</p><ElButton @click="load"><RotateCcw :size="15" />重试</ElButton></div>
    <ElEmpty v-else-if="servers.length === 0" description="暂无 MCP 服务器" />
    <article v-for="server in servers" v-else :key="server.server_name" class="settings-card settings-connection-card">
      <div class="settings-card-title">
        <strong>{{ server.server_name }}</strong>
        <ElTag size="small" effect="plain">{{ server.transport }}</ElTag>
        <ElTag v-if="!server.enabled" size="small" type="info" effect="plain">禁用</ElTag>
        <div class="settings-card-actions">
          <ElButton text type="danger" size="small" :aria-label="`删除 ${server.server_name}`" @click="deleteServer(server.server_name)"><Trash :size="14" /></ElButton>
          <ElSwitch :model-value="server.enabled" inline-prompt active-text="开" inactive-text="关" :aria-label="`${server.server_name} 启用状态`" @change="toggle(server.server_name, Boolean($event))" />
        </div>
      </div>
      <div v-if="server.tools?.length" class="badge-row">
        <ElTag v-for="tool in server.tools" :key="tool" size="small" effect="plain"><Wrench :size="12" />{{ tool }}</ElTag>
      </div>
    </article>
  </section>

  <ElDialog v-model="dialogOpen" width="min(620px, calc(100vw - 24px))" append-to-body align-center class="settings-sub-dialog" :show-close="!adding" :close-on-click-modal="!adding" :close-on-press-escape="!adding" title="添加新的 MCP 服务器">
    <ElInput v-model="configText" type="textarea" resize="vertical" :autosize="{ minRows: 10, maxRows: 18 }" :placeholder="placeholder" class="settings-code-input" />
    <template #footer><ElButton :disabled="adding" @click="dialogOpen = false">取消</ElButton><ElButton type="primary" :loading="adding" @click="addServer">添加</ElButton></template>
  </ElDialog>
</template>
