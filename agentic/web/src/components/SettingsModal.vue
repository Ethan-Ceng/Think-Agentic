<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Languages, LayoutGrid, Loader2, Plus, Settings, Trash, Wrench } from 'lucide-vue-next'
import { useSettingsModal } from '@/composables/useSettingsModal'
import { useToast } from '@/composables/useToast'
import { configApi } from '@/lib/api/config'
import type { AgentConfig, LLMConfig, ListA2AServerItem, ListMCPServerItem } from '@/lib/api/types'

type SettingTab = 'common' | 'llm' | 'a2a' | 'mcp'

const toast = useToast()
const settingsModal = useSettingsModal()
const activeTab = ref<SettingTab>('common')

const agentConfig = ref<AgentConfig>({})
const llmConfig = ref<LLMConfig>({})
const mcpServers = ref<ListMCPServerItem[]>([])
const a2aServers = ref<ListA2AServerItem[]>([])

const loadingConfig = ref(false)
const loadingMCP = ref(false)
const loadingA2A = ref(false)
const saving = ref(false)
const fetching = ref(false)

const mcpDialogOpen = ref(false)
const mcpConfigText = ref('')
const addingMCP = ref(false)
const a2aDialogOpen = ref(false)
const a2aBaseUrl = ref('')
const addingA2A = ref(false)

const tabs = [
  { key: 'common' as const, icon: Settings, title: '通用配置' },
  { key: 'llm' as const, icon: Languages, title: '模型提供商' },
  { key: 'a2a' as const, icon: LayoutGrid, title: 'A2A Agent' },
  { key: 'mcp' as const, icon: Wrench, title: 'MCP 服务器' },
]

const showSave = computed(() => activeTab.value === 'common' || activeTab.value === 'llm')

const mcpPlaceholder = `{
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

function fetchAllConfigs() {
  if (fetching.value) return
  fetching.value = true

  loadingConfig.value = true
  const configTask = Promise.all([configApi.getAgentConfig(), configApi.getLLMConfig()])
    .then(([agent, llm]) => {
      agentConfig.value = agent || {}
      llmConfig.value = llm || {}
    })
    .catch((err) => console.error('[Settings] 获取基础配置失败:', err))
    .finally(() => {
      loadingConfig.value = false
    })

  loadingMCP.value = true
  const mcpTask = configApi
    .getMCPServers()
    .then((data) => {
      mcpServers.value = data?.mcp_servers ?? []
    })
    .catch((err) => console.error('[Settings] 获取 MCP 服务器列表失败:', err))
    .finally(() => {
      loadingMCP.value = false
    })

  loadingA2A.value = true
  const a2aTask = configApi
    .getA2AServers()
    .then((data) => {
      a2aServers.value = data?.a2a_servers ?? []
    })
    .catch((err) => console.error('[Settings] 获取 A2A 服务器列表失败:', err))
    .finally(() => {
      loadingA2A.value = false
    })

  void Promise.allSettled([configTask, mcpTask, a2aTask]).finally(() => {
    fetching.value = false
  })
}

onMounted(() => {
  fetchAllConfigs()
})

function handleDialogUpdate(open: boolean) {
  if (!open) {
    settingsModal.closeSettings()
  }
}

async function handleSave() {
  saving.value = true
  try {
    if (activeTab.value === 'common') {
      await configApi.updateAgentConfig(agentConfig.value)
      toast.success('通用配置保存成功')
    } else if (activeTab.value === 'llm') {
      await configApi.updateLLMConfig(llmConfig.value)
      toast.success('模型提供商配置保存成功')
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function toggleMCP(serverName: string, enabled: boolean) {
  const previous = mcpServers.value
  mcpServers.value = mcpServers.value.map((server) =>
    server.server_name === serverName ? { ...server, enabled } : server,
  )
  try {
    await configApi.updateMCPServerEnabled(serverName, enabled)
    toast.success(`${serverName} 已${enabled ? '启用' : '禁用'}`)
  } catch {
    mcpServers.value = previous
    toast.error('操作失败，请重试')
  }
}

function handleMCPSwitch(serverName: string, value: string | number | boolean) {
  void toggleMCP(serverName, Boolean(value))
}

async function deleteMCP(serverName: string) {
  const previous = mcpServers.value
  mcpServers.value = mcpServers.value.filter((server) => server.server_name !== serverName)
  try {
    await configApi.deleteMCPServer(serverName)
    toast.success(`已删除 MCP 服务器「${serverName}」`)
  } catch {
    mcpServers.value = previous
    toast.error('删除失败，请重试')
  }
}

async function addMCP() {
  if (!mcpConfigText.value.trim()) {
    toast.error('请输入 MCP 服务器配置')
    return
  }

  addingMCP.value = true
  try {
    const parsed = JSON.parse(mcpConfigText.value)
    await configApi.addMCPServer(parsed)
    const data = await configApi.getMCPServers()
    mcpServers.value = data?.mcp_servers ?? []
    mcpConfigText.value = ''
    mcpDialogOpen.value = false
    toast.success('MCP 服务器添加成功')
  } catch (err) {
    toast.error(err instanceof SyntaxError ? 'JSON 格式错误，请检查配置' : err instanceof Error ? err.message : '添加失败')
  } finally {
    addingMCP.value = false
  }
}

async function toggleA2A(id: string, enabled: boolean) {
  const previous = a2aServers.value
  a2aServers.value = a2aServers.value.map((server) =>
    server.id === id ? { ...server, enabled } : server,
  )
  try {
    await configApi.updateA2AServerEnabled(id, enabled)
    const server = previous.find((item) => item.id === id)
    toast.success(`${server?.name ?? 'Agent'} 已${enabled ? '启用' : '禁用'}`)
  } catch {
    a2aServers.value = previous
    toast.error('操作失败，请重试')
  }
}

function handleA2ASwitch(id: string, value: string | number | boolean) {
  void toggleA2A(id, Boolean(value))
}

async function deleteA2A(id: string) {
  const previous = a2aServers.value
  const target = previous.find((server) => server.id === id)
  a2aServers.value = a2aServers.value.filter((server) => server.id !== id)
  try {
    await configApi.deleteA2AServer(id)
    toast.success(`已删除 A2A Agent「${target?.name ?? id}」`)
  } catch {
    a2aServers.value = previous
    toast.error('删除失败，请重试')
  }
}

async function addA2A() {
  const baseUrl = a2aBaseUrl.value.trim()
  if (!baseUrl) {
    toast.error('请输入远程 Agent 地址')
    return
  }

  addingA2A.value = true
  try {
    await configApi.addA2AServer({ base_url: baseUrl })
    const data = await configApi.getA2AServers()
    a2aServers.value = data?.a2a_servers ?? []
    a2aBaseUrl.value = ''
    a2aDialogOpen.value = false
    toast.success('远程 Agent 添加成功')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '添加失败')
  } finally {
    addingA2A.value = false
  }
}
</script>

<template>
  <ElDialog
    :model-value="settingsModal.open.value"
    width="min(920px, calc(100vw - 24px))"
    append-to-body
    align-center
    class="settings-dialog"
    @update:model-value="handleDialogUpdate"
  >
    <template #header>
      <div class="settings-dialog-header">
        <h2>MoocManus 设置</h2>
        <p>管理模型、Agent、A2A 与 MCP 工具连接。</p>
      </div>
    </template>

    <div class="settings-layout">
      <nav class="settings-nav" aria-label="设置分类">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="settings-nav-button"
          :class="{ active: activeTab === tab.key }"
          type="button"
          :aria-current="activeTab === tab.key ? 'page' : undefined"
          @click="activeTab = tab.key"
        >
          <span class="settings-tab-label">
            <component :is="tab.icon" :size="16" />
            <span>{{ tab.title }}</span>
          </span>
        </button>
      </nav>

      <main class="settings-main">
        <div v-if="loadingConfig && (activeTab === 'common' || activeTab === 'llm')" class="center-state">
          <Loader2 :size="22" class="spin" />
        </div>

        <ElForm v-else-if="activeTab === 'common'" label-position="top" class="settings-form">
          <h3>通用配置</h3>
          <ElFormItem label="最大计划迭代次数">
            <ElInputNumber v-model="agentConfig.max_iterations" :min="0" :max="200" :step="1" controls-position="right" />
            <p class="settings-field-hint">Agent 在一次任务中最多可循环调用工具的次数，默认 100。</p>
          </ElFormItem>
          <ElFormItem label="最大重试次数">
            <ElInputNumber v-model="agentConfig.max_retries" :min="0" :max="10" :step="1" controls-position="right" />
            <p class="settings-field-hint">工具或模型调用失败后的最大重试次数，默认 3。</p>
          </ElFormItem>
          <ElFormItem label="最大搜索结果">
            <ElInputNumber v-model="agentConfig.max_search_results" :min="0" :max="30" :step="1" controls-position="right" />
            <p class="settings-field-hint">每个搜索步骤返回的结果数量，默认 10。</p>
          </ElFormItem>
        </ElForm>

        <ElForm v-else-if="activeTab === 'llm'" label-position="top" class="settings-form">
          <h3>模型提供商</h3>
          <ElFormItem label="提供商基础地址 base_url">
            <ElInput v-model="llmConfig.base_url" placeholder="https://api.openai.com/v1" clearable />
            <p class="settings-field-hint">需要兼容 OpenAI API 格式。</p>
          </ElFormItem>
          <ElFormItem label="提供商密钥">
            <ElInput v-model="llmConfig.api_key" type="password" placeholder="请输入 API Key" show-password clearable />
          </ElFormItem>
          <ElFormItem label="模型名称">
            <ElInput v-model="llmConfig.model_name" placeholder="请输入模型名称" clearable />
          </ElFormItem>
          <ElFormItem label="温度 temperature">
            <ElInputNumber v-model="llmConfig.temperature" :min="0" :max="2" :step="0.1" controls-position="right" />
          </ElFormItem>
          <ElFormItem label="最大输出 Token 数 max_tokens">
            <ElInputNumber v-model="llmConfig.max_tokens" :min="1" :max="128000" :step="1024" controls-position="right" />
          </ElFormItem>
        </ElForm>

        <section v-else-if="activeTab === 'a2a'" class="settings-list">
          <header>
            <div>
              <h3>A2A Agent 配置</h3>
              <p>连接标准 A2A 协议的远程 Agent。</p>
            </div>
            <ElButton type="primary" size="small" @click="a2aDialogOpen = true">
              <Plus :size="14" />
              添加远程 Agent
            </ElButton>
          </header>

          <div v-if="loadingA2A" class="center-state">
            <Loader2 :size="22" class="spin" />
          </div>
          <ElEmpty v-else-if="a2aServers.length === 0" description="暂无 A2A Agent" />
          <article v-for="server in a2aServers" v-else :key="server.id" class="settings-card">
            <div class="settings-card-title">
              <strong>{{ server.name }}</strong>
              <ElTag v-if="!server.enabled" size="small" type="info" effect="plain">禁用</ElTag>
              <ElButton text type="danger" size="small" @click="deleteA2A(server.id)">
                <Trash :size="14" />
              </ElButton>
              <ElSwitch
                :model-value="server.enabled"
                inline-prompt
                active-text="开"
                inactive-text="关"
                @change="handleA2ASwitch(server.id, $event)"
              />
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

        <section v-else class="settings-list">
          <header>
            <div>
              <h3>MCP 服务器</h3>
              <p>通过外部工具增强 MoocManus 的任务执行能力。</p>
            </div>
            <ElButton type="primary" size="small" @click="mcpDialogOpen = true">
              <Plus :size="14" />
              添加服务器
            </ElButton>
          </header>

          <div v-if="loadingMCP" class="center-state">
            <Loader2 :size="22" class="spin" />
          </div>
          <ElEmpty v-else-if="mcpServers.length === 0" description="暂无 MCP 服务器" />
          <article v-for="server in mcpServers" v-else :key="server.server_name" class="settings-card">
            <div class="settings-card-title">
              <strong>{{ server.server_name }}</strong>
              <ElTag size="small" effect="plain">{{ server.transport }}</ElTag>
              <ElTag v-if="!server.enabled" size="small" type="info" effect="plain">禁用</ElTag>
              <ElButton text type="danger" size="small" @click="deleteMCP(server.server_name)">
                <Trash :size="14" />
              </ElButton>
              <ElSwitch
                :model-value="server.enabled"
                inline-prompt
                active-text="开"
                inactive-text="关"
                @change="handleMCPSwitch(server.server_name, $event)"
              />
            </div>
            <div v-if="server.tools?.length" class="badge-row">
              <ElTag v-for="tool in server.tools" :key="tool" size="small" effect="plain">
                <Wrench :size="12" />
                {{ tool }}
              </ElTag>
            </div>
          </article>
        </section>
      </main>
    </div>

    <template #footer>
      <ElButton @click="settingsModal.closeSettings">取消</ElButton>
      <ElButton v-if="showSave" type="primary" :loading="saving" @click="handleSave">
        保存
      </ElButton>
    </template>
  </ElDialog>

  <ElDialog
    v-model="mcpDialogOpen"
    width="min(620px, calc(100vw - 24px))"
    append-to-body
    align-center
    class="settings-sub-dialog"
    :show-close="!addingMCP"
    :close-on-click-modal="!addingMCP"
    :close-on-press-escape="!addingMCP"
    title="添加新的 MCP 服务器"
  >
    <ElInput
      v-model="mcpConfigText"
      type="textarea"
      resize="vertical"
      :autosize="{ minRows: 10, maxRows: 18 }"
      :placeholder="mcpPlaceholder"
      class="settings-code-input"
    />
    <template #footer>
      <ElButton :disabled="addingMCP" @click="mcpDialogOpen = false">取消</ElButton>
      <ElButton type="primary" :loading="addingMCP" @click="addMCP">添加</ElButton>
    </template>
  </ElDialog>

  <ElDialog
    v-model="a2aDialogOpen"
    width="min(560px, calc(100vw - 24px))"
    append-to-body
    align-center
    class="settings-sub-dialog"
    :show-close="!addingA2A"
    :close-on-click-modal="!addingA2A"
    :close-on-press-escape="!addingA2A"
    title="添加远程 Agent"
  >
    <ElForm label-position="top" class="settings-form compact">
      <ElFormItem label="远程 Agent 地址">
        <ElInput v-model="a2aBaseUrl" placeholder="https://mooc-manus.com/weather-agent" clearable />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton :disabled="addingA2A" @click="a2aDialogOpen = false">取消</ElButton>
      <ElButton type="primary" :loading="addingA2A" @click="addA2A">添加</ElButton>
    </template>
  </ElDialog>
</template>
