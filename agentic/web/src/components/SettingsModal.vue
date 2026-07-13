<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ClipboardCheck, Languages, LayoutGrid, Loader2, Pencil, Play, Plus, Settings, ShieldAlert, Trash, Wrench } from 'lucide-vue-next'
import { useSettingsModal } from '@/composables/useSettingsModal'
import { useToast } from '@/composables/useToast'
import { configApi } from '@/lib/api/config'
import { toolsApi } from '@/lib/api/tools'
import type {
  AgentConfig,
  LLMConfig,
  ListA2AServerItem,
  ListMCPServerItem,
  RuntimeToolPolicy,
  ToolDescriptor,
  ToolExecutorType,
  ToolListData,
  ToolPreflightResponse,
  ToolRegistration,
  ToolRegistrationTestData,
  ToolRiskLevel,
} from '@/lib/api/types'

type SettingTab = 'common' | 'llm' | 'tools' | 'a2a' | 'mcp'

const toast = useToast()
const settingsModal = useSettingsModal()
const activeTab = ref<SettingTab>('common')

const agentConfig = ref<AgentConfig>({})
const llmConfig = ref<LLMConfig>({})
const mcpServers = ref<ListMCPServerItem[]>([])
const a2aServers = ref<ListA2AServerItem[]>([])
const tools = ref<ToolDescriptor[]>([])
const toolRegistrations = ref<ToolRegistration[]>([])
const runtimePolicy = ref<RuntimeToolPolicy>({
  allowed_executor_types: ['builtin', 'mcp', 'a2a', 'api'],
  max_tool_iterations: 100,
})

const loadingConfig = ref(false)
const loadingMCP = ref(false)
const loadingA2A = ref(false)
const loadingTools = ref(false)
const saving = ref(false)
const fetching = ref(false)
const checkingPreflight = ref(false)

const mcpDialogOpen = ref(false)
const mcpConfigText = ref('')
const addingMCP = ref(false)
const a2aDialogOpen = ref(false)
const a2aBaseUrl = ref('')
const addingA2A = ref(false)
const registrationDialogOpen = ref(false)
const addingRegistration = ref(false)
const editingRegistrationId = ref<string | null>(null)
const registrationForm = ref({
  provider_id: '',
  provider_label: '',
  group: 'custom',
  category: '自定义',
  description: '',
  enabled: true,
  base_url: '',
  timeout: 60,
  headers_text: '',
  openapi_schema_text: '',
  allow_private_network: false,
})
const testDialogOpen = ref(false)
const testingRegistration = ref<ToolRegistration | null>(null)
const testingToolName = ref('')
const testArgumentsText = ref('{}')
const testingTool = ref(false)
const testResult = ref<ToolRegistrationTestData | null>(null)
const preflightMessage = ref('')
const preflightResult = ref<ToolPreflightResponse | null>(null)

const tabs = [
  { key: 'common' as const, icon: Settings, title: '通用配置' },
  { key: 'llm' as const, icon: Languages, title: '模型提供商' },
  { key: 'tools' as const, icon: ShieldAlert, title: 'API Tools' },
  { key: 'a2a' as const, icon: LayoutGrid, title: 'A2A Agent' },
  { key: 'mcp' as const, icon: Wrench, title: 'MCP 服务器' },
]

const showSave = computed(() => ['common', 'llm', 'tools'].includes(activeTab.value))
const saveDisabled = computed(() =>
  loadingTools.value && ['common', 'tools'].includes(activeTab.value),
)

const executorOptions: Array<{ value: ToolExecutorType; label: string }> = [
  { value: 'mcp', label: 'MCP' },
  { value: 'a2a', label: 'A2A' },
  { value: 'api', label: 'API' },
]

const apiToolRegistrations = computed(() =>
  toolRegistrations.value.filter(
    (registration) => !registration.builtin && registration.source_type === 'api',
  ),
)

const apiProviderIds = computed(() =>
  new Set(apiToolRegistrations.value.map((registration) => registration.provider_id)),
)

const apiTools = computed(() =>
  tools.value.filter(
    (tool) => tool.executor_type === 'api' && apiProviderIds.value.has(tool.provider_id),
  ),
)

const apiToolGroups = computed(() =>
  apiToolRegistrations.value
    .map((registration) => ({
      key: registration.provider_id,
      title: registration.provider_label,
      tools: apiTools.value.filter((tool) => tool.provider_id === registration.provider_id),
    }))
    .filter((group) => group.tools.length > 0),
)

function summarizeTools(items: ToolDescriptor[]) {
  const enabled = items.filter((tool) => tool.enabled)
  return {
    enabledCount: enabled.length,
    totalCount: items.length,
    highRiskCount: enabled.filter((tool) => tool.risk_level === 'high').length,
    credentialsCount: enabled.filter((tool) => tool.requires_credentials).length,
  }
}

const apiToolSummary = computed(() => summarizeTools(apiTools.value))

const visiblePreflightChecks = computed(() => {
  return preflightResult.value?.checks.filter((check) => !check.passed || check.user_message !== '未检测到该能力需求。') ?? []
})

function registrationToolCount(registrationId: string) {
  return apiTools.value.filter((tool) => tool.provider_id === registrationId).length
}

const registrationDialogTitle = computed(() =>
  editingRegistrationId.value ? '编辑 API Tool' : '新增 API Tool',
)

const registrationSubmitText = computed(() =>
  editingRegistrationId.value ? '保存' : '新增',
)

const testingTools = computed(() => {
  if (!testingRegistration.value) return []
  return apiTools.value.filter((tool) => tool.provider_id === testingRegistration.value?.provider_id)
})

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

function applyToolListData(data: ToolListData | null | undefined) {
  tools.value = data?.tools ?? []
  toolRegistrations.value = data?.registrations ?? []
  const nextPolicy = data?.runtime_policy ?? runtimePolicy.value
  runtimePolicy.value = {
    ...nextPolicy,
    allowed_executor_types: Array.from(
      new Set<ToolExecutorType>(['builtin', ...nextPolicy.allowed_executor_types]),
    ),
  }
}

async function refreshToolList() {
  applyToolListData(await toolsApi.listTools())
}

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

  loadingTools.value = true
  const toolsTask = toolsApi
    .listTools()
    .then((data) => {
      applyToolListData(data)
    })
    .catch((err) => console.error('[Settings] 获取工具列表失败:', err))
    .finally(() => {
      loadingTools.value = false
    })

  void Promise.allSettled([configTask, mcpTask, a2aTask, toolsTask]).finally(() => {
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
      await Promise.all([
        configApi.updateAgentConfig(agentConfig.value),
        saveToolConfig(),
      ])
      toast.success('通用配置保存成功')
    } else if (activeTab.value === 'llm') {
      await configApi.updateLLMConfig(llmConfig.value)
      toast.success('模型提供商配置保存成功')
    } else if (activeTab.value === 'tools') {
      await saveToolConfig()
      toast.success('API Tools 配置保存成功')
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    saving.value = false
  }
}

function buildToolBindings() {
  return Object.fromEntries(
    apiTools.value.map((tool) => [
      tool.tool_id,
      {
        enabled: tool.enabled,
        risk_level: tool.risk_level,
        params: {},
      },
    ]),
  )
}

async function saveToolConfig() {
  const data = await toolsApi.updateBindings({
    bindings: buildToolBindings(),
    runtime_policy: runtimePolicy.value,
  })
  applyToolListData(data)
}

function handleToolSwitch(toolId: string, value: string | number | boolean) {
  const enabled = Boolean(value)
  tools.value = tools.value.map((tool) => (tool.tool_id === toolId ? { ...tool, enabled } : tool))
}

function handleExecutorSwitch(executorType: ToolExecutorType, value: string | number | boolean) {
  const enabled = Boolean(value)
  const next = new Set(runtimePolicy.value.allowed_executor_types)
  if (enabled) {
    next.add(executorType)
  } else {
    next.delete(executorType)
  }
  runtimePolicy.value = {
    ...runtimePolicy.value,
    allowed_executor_types: Array.from(next),
  }
}

function resetRegistrationForm() {
  registrationForm.value = {
    provider_id: '',
    provider_label: '',
    group: 'custom',
    category: '自定义',
    description: '',
    enabled: true,
    base_url: '',
    timeout: 60,
    headers_text: '',
    openapi_schema_text: '',
    allow_private_network: false,
  }
}

function stringifyConfigValue(value: unknown) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

function openRegistrationDialog() {
  resetRegistrationForm()
  editingRegistrationId.value = null
  registrationDialogOpen.value = true
}

function openEditRegistrationDialog(registration: ToolRegistration) {
  const config = registration.config ?? {}
  registrationForm.value = {
    provider_id: registration.provider_id,
    provider_label: registration.provider_label,
    group: registration.group,
    category: registration.category,
    description: registration.description,
    enabled: registration.enabled,
    base_url: typeof config.base_url === 'string' ? config.base_url : '',
    timeout: typeof config.timeout === 'number' ? config.timeout : 60,
    headers_text: stringifyConfigValue(config.headers),
    openapi_schema_text: stringifyConfigValue(config.openapi_schema ?? config.schema),
    allow_private_network: Boolean(config.allow_private_network),
  }
  editingRegistrationId.value = registration.registration_id
  registrationDialogOpen.value = true
}

function parseJsonObject(text: string, label: string) {
  const content = text.trim()
  if (!content) return {}
  const parsed = JSON.parse(content)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error(`${label} 必须是 JSON 对象`)
  }
  return parsed as Record<string, unknown>
}

function buildRegistrationConfig() {
  const openapiSchema = registrationForm.value.openapi_schema_text.trim()
  if (!openapiSchema) {
    throw new Error('请填写 OpenAPI Schema')
  }

  const config: Record<string, unknown> = {
    openapi_schema: openapiSchema,
    timeout: registrationForm.value.timeout,
    allow_private_network: registrationForm.value.allow_private_network,
  }
  const baseUrl = registrationForm.value.base_url.trim()
  if (baseUrl) {
    config.base_url = baseUrl
  }
  const headers = parseJsonObject(registrationForm.value.headers_text, 'Headers')
  if (Object.keys(headers).length > 0) {
    config.headers = headers
  }
  return config
}

async function addToolRegistration() {
  const providerId = registrationForm.value.provider_id.trim()
  const providerLabel = registrationForm.value.provider_label.trim()
  if (!providerId || !providerLabel) {
    toast.error('请填写工具源 ID 和名称')
    return
  }

  let config: Record<string, unknown>
  try {
    config = buildRegistrationConfig()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '工具源配置格式错误')
    return
  }

  addingRegistration.value = true
  try {
    const payload = {
      provider_id: providerId,
      provider_label: providerLabel,
      source_type: 'api' as const,
      executor_type: 'api' as const,
      group: registrationForm.value.group.trim() || 'custom',
      category: registrationForm.value.category.trim() || '自定义',
      description: registrationForm.value.description.trim(),
      enabled: registrationForm.value.enabled,
      requires_sandbox: false,
      requires_browser: false,
      requires_credentials: Boolean(config.headers),
      config,
    }
    const wasEditing = Boolean(editingRegistrationId.value)
    if (editingRegistrationId.value) {
      await toolsApi.updateRegistration(editingRegistrationId.value, payload)
    } else {
      await toolsApi.createRegistration(payload)
    }
    await refreshToolList()
    registrationDialogOpen.value = false
    editingRegistrationId.value = null
    toast.success(wasEditing ? 'API Tool 已保存' : 'API Tool 注册成功')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'API Tool 保存失败')
  } finally {
    addingRegistration.value = false
  }
}

async function toggleToolRegistration(registrationId: string, enabled: boolean) {
  const previous = toolRegistrations.value
  toolRegistrations.value = toolRegistrations.value.map((registration) =>
    registration.registration_id === registrationId ? { ...registration, enabled } : registration,
  )
  try {
    const data = await toolsApi.updateRegistration(registrationId, { enabled })
    toolRegistrations.value = data?.registrations ?? toolRegistrations.value
    await refreshToolList()
    toast.success(`API Tool 已${enabled ? '启用' : '禁用'}`)
  } catch {
    toolRegistrations.value = previous
    toast.error('API Tool 状态更新失败')
  }
}

function handleToolRegistrationSwitch(registrationId: string, value: string | number | boolean) {
  void toggleToolRegistration(registrationId, Boolean(value))
}

async function deleteToolRegistration(registrationId: string) {
  const previous = toolRegistrations.value
  toolRegistrations.value = toolRegistrations.value.filter(
    (registration) => registration.registration_id !== registrationId,
  )
  try {
    const data = await toolsApi.deleteRegistration(registrationId)
    toolRegistrations.value = data?.registrations ?? toolRegistrations.value
    await refreshToolList()
    toast.success('工具源已删除')
  } catch {
    toolRegistrations.value = previous
    toast.error('工具源删除失败')
  }
}

function openTestRegistrationDialog(registration: ToolRegistration) {
  testingRegistration.value = registration
  testResult.value = null
  const firstTool = tools.value.find((tool) => tool.provider_id === registration.provider_id)
  testingToolName.value = firstTool?.function_name ?? ''
  testArgumentsText.value = '{}'
  testDialogOpen.value = true
}

async function runToolRegistrationTest() {
  if (!testingRegistration.value) return

  let args: Record<string, unknown> = {}
  if (testingToolName.value) {
    try {
      args = parseJsonObject(testArgumentsText.value, 'Arguments')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '测试参数格式错误')
      return
    }
  }

  testingTool.value = true
  try {
    testResult.value = await toolsApi.testRegistration(testingRegistration.value.registration_id, {
      function_name: testingToolName.value || null,
      arguments: args,
    })
    await refreshToolList()
    const result = testResult.value.result
    if (result && result.success === false) {
      toast.error(result.message || '工具测试失败')
    } else {
      toast.success(result ? '工具测试完成' : '工具源解析完成')
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '工具源测试失败')
  } finally {
    testingTool.value = false
  }
}

async function runPreflight() {
  const message = preflightMessage.value.trim()
  if (!message) {
    toast.error('请输入任务描述')
    return
  }

  checkingPreflight.value = true
  try {
    preflightResult.value = await toolsApi.preflight({ message })
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '检测失败')
  } finally {
    checkingPreflight.value = false
  }
}

function riskTagType(risk: ToolRiskLevel) {
  if (risk === 'high') return 'danger'
  if (risk === 'medium') return 'warning'
  return 'success'
}

function riskLabel(risk: ToolRiskLevel) {
  if (risk === 'high') return '高危'
  if (risk === 'medium') return '中等'
  return '低风险'
}

function preflightStatusType(status: ToolPreflightResponse['status']) {
  if (status === 'blocked') return 'danger'
  if (status === 'warning') return 'warning'
  return 'success'
}

function preflightStatusLabel(status: ToolPreflightResponse['status']) {
  if (status === 'blocked') return '阻断'
  if (status === 'warning') return '警告'
  return '通过'
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
        <p>管理模型、API Tools 与外部连接。</p>
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

          <section class="settings-card tool-policy-card">
            <div class="settings-card-title">
              <strong>高级运行策略</strong>
            </div>
            <div class="tool-policy-grid">
              <label v-for="option in executorOptions" :key="option.value" class="tool-policy-switch">
                <span>{{ option.label }}</span>
                <ElSwitch
                  :model-value="runtimePolicy.allowed_executor_types.includes(option.value)"
                  inline-prompt
                  active-text="开"
                  inactive-text="关"
                  @change="handleExecutorSwitch(option.value, $event)"
                />
              </label>
              <label class="tool-policy-number">
                <span>最大工具迭代</span>
                <ElInputNumber v-model="runtimePolicy.max_tool_iterations" :min="1" :max="1000" :step="1" controls-position="right" />
              </label>
            </div>
          </section>

          <section class="settings-card tool-preflight-card">
            <div class="settings-card-title">
              <strong>能力预检</strong>
            </div>
            <div class="tool-preflight-input">
              <ElInput
                v-model="preflightMessage"
                type="textarea"
                resize="vertical"
                :autosize="{ minRows: 3, maxRows: 6 }"
                placeholder="输入任务描述"
              />
              <ElButton type="primary" :loading="checkingPreflight" @click="runPreflight">
                <ClipboardCheck :size="14" />
                检测
              </ElButton>
            </div>
            <div v-if="preflightResult" class="tool-preflight-result">
              <ElTag size="small" effect="light" :type="preflightStatusType(preflightResult.status)">
                {{ preflightStatusLabel(preflightResult.status) }}
              </ElTag>
              <div class="tool-preflight-checks">
                <p v-for="check in visiblePreflightChecks" :key="check.rule_id" :class="{ failed: !check.passed }">
                  {{ check.user_message }}
                </p>
              </div>
            </div>
          </section>
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

        <section v-else-if="activeTab === 'tools'" class="settings-list tools-settings">
          <header>
            <div>
              <h3>API Tools</h3>
              <p>注册和管理通过 OpenAPI/HTTP 接入的外部工具。</p>
            </div>
            <ElButton type="primary" size="small" @click="openRegistrationDialog">
              <Plus :size="14" />
              新增 API Tool
            </ElButton>
          </header>

          <div v-if="loadingTools" class="center-state">
            <Loader2 :size="22" class="spin" />
          </div>

          <template v-else>
            <div class="tool-summary-grid">
              <div class="tool-summary-item">
                <span>Provider</span>
                <strong>{{ apiToolRegistrations.length }}</strong>
              </div>
              <div class="tool-summary-item">
                <span>已启用工具</span>
                <strong>{{ apiToolSummary.enabledCount }} / {{ apiToolSummary.totalCount }}</strong>
              </div>
              <div class="tool-summary-item">
                <span>高风险工具</span>
                <strong>{{ apiToolSummary.highRiskCount }}</strong>
              </div>
              <div class="tool-summary-item">
                <span>需要凭证</span>
                <strong>{{ apiToolSummary.credentialsCount }}</strong>
              </div>
            </div>

            <section class="settings-card tool-registration-card">
              <div class="settings-card-title">
                <strong>API Providers</strong>
              </div>
              <ElEmpty v-if="apiToolRegistrations.length === 0" description="暂无 API Tool，请先新增 Provider" />
              <div v-else class="tool-registration-list">
                <article
                  v-for="registration in apiToolRegistrations"
                  :key="registration.registration_id"
                  class="tool-registration-row"
                >
                  <div class="tool-registration-main">
                    <div class="tool-row-heading">
                      <strong>{{ registration.provider_label }}</strong>
                      <code>{{ registration.provider_id }}</code>
                    </div>
                    <p>{{ registration.description || '未配置描述' }}</p>
                    <div class="badge-row">
                      <ElTag size="small" effect="plain">API</ElTag>
                      <ElTag size="small" effect="plain">{{ registrationToolCount(registration.registration_id) }} 工具</ElTag>
                      <ElTag v-if="registration.requires_credentials" size="small" effect="plain">凭证</ElTag>
                    </div>
                  </div>
                  <div class="tool-registration-controls">
                    <ElButton text size="small" title="测试" @click="openTestRegistrationDialog(registration)">
                      <Play :size="14" />
                    </ElButton>
                    <ElButton text size="small" title="编辑" @click="openEditRegistrationDialog(registration)">
                      <Pencil :size="14" />
                    </ElButton>
                    <ElButton text type="danger" size="small" title="删除" @click="deleteToolRegistration(registration.registration_id)">
                      <Trash :size="14" />
                    </ElButton>
                    <ElSwitch
                      :model-value="registration.enabled"
                      inline-prompt
                      active-text="开"
                      inactive-text="关"
                      @change="handleToolRegistrationSwitch(registration.registration_id, $event)"
                    />
                  </div>
                </article>
              </div>
            </section>

            <ElEmpty v-if="apiToolGroups.length === 0" description="暂无已解析的 API operations" />
            <template v-else>
              <section v-for="group in apiToolGroups" :key="group.key" class="tool-group">
                <h4>{{ group.title }} · Operations</h4>
                <article v-for="tool in group.tools" :key="tool.tool_id" class="tool-row">
                  <div class="tool-row-main">
                    <div class="tool-row-heading">
                      <strong>{{ tool.label }}</strong>
                      <code>{{ tool.function_name }}</code>
                    </div>
                    <p>{{ tool.description }}</p>
                    <div class="badge-row">
                      <ElTag size="small" effect="plain" :type="riskTagType(tool.risk_level)">{{ riskLabel(tool.risk_level) }}</ElTag>
                      <ElTag size="small" effect="plain">API</ElTag>
                      <ElTag v-if="tool.requires_credentials" size="small" effect="plain">凭证</ElTag>
                    </div>
                  </div>
                  <div class="tool-row-controls">
                    <ElSwitch
                      :model-value="tool.enabled"
                      inline-prompt
                      active-text="开"
                      inactive-text="关"
                      @change="handleToolSwitch(tool.tool_id, $event)"
                    />
                  </div>
                </article>
              </section>
            </template>
          </template>
        </section>

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
      <ElButton v-if="showSave" type="primary" :loading="saving" :disabled="saveDisabled" @click="handleSave">
        保存
      </ElButton>
    </template>
  </ElDialog>

  <ElDialog
    v-model="registrationDialogOpen"
    width="min(720px, calc(100vw - 24px))"
    append-to-body
    align-center
    class="settings-sub-dialog"
    :show-close="!addingRegistration"
    :close-on-click-modal="!addingRegistration"
    :close-on-press-escape="!addingRegistration"
    :title="registrationDialogTitle"
  >
    <ElForm label-position="top" class="settings-form compact">
      <ElFormItem label="Provider ID">
        <ElInput
          v-model="registrationForm.provider_id"
          placeholder="api.weather"
          clearable
          :disabled="Boolean(editingRegistrationId)"
        />
      </ElFormItem>
      <ElFormItem label="Provider 名称">
        <ElInput v-model="registrationForm.provider_label" placeholder="天气 API" clearable />
      </ElFormItem>
      <ElFormItem label="Base URL">
        <ElInput v-model="registrationForm.base_url" placeholder="https://api.example.com" clearable />
      </ElFormItem>
      <ElFormItem label="超时时间">
        <ElInputNumber v-model="registrationForm.timeout" :min="1" :max="600" :step="1" controls-position="right" />
      </ElFormItem>
      <ElFormItem label="Headers JSON">
        <ElInput
          v-model="registrationForm.headers_text"
          type="textarea"
          resize="vertical"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder='{"Authorization": "env:MY_API_TOKEN"}'
        />
      </ElFormItem>
      <ElFormItem label="OpenAPI Schema">
        <ElInput
          v-model="registrationForm.openapi_schema_text"
          type="textarea"
          resize="vertical"
          :autosize="{ minRows: 8, maxRows: 16 }"
          placeholder='{"openapi":"3.0.0","paths":{}}'
        />
      </ElFormItem>
      <ElFormItem label="描述">
        <ElInput
          v-model="registrationForm.description"
          type="textarea"
          resize="vertical"
          :autosize="{ minRows: 2, maxRows: 4 }"
          placeholder="描述这个工具源提供的能力"
        />
      </ElFormItem>
      <div class="tool-registration-flags">
        <ElCheckbox v-model="registrationForm.enabled">启用 Provider</ElCheckbox>
        <ElCheckbox v-model="registrationForm.allow_private_network">
          允许内网地址
        </ElCheckbox>
      </div>
    </ElForm>
    <template #footer>
      <ElButton :disabled="addingRegistration" @click="registrationDialogOpen = false">取消</ElButton>
      <ElButton type="primary" :loading="addingRegistration" @click="addToolRegistration">
        {{ registrationSubmitText }}
      </ElButton>
    </template>
  </ElDialog>

  <ElDialog
    v-model="testDialogOpen"
    width="min(680px, calc(100vw - 24px))"
    append-to-body
    align-center
    class="settings-sub-dialog"
    :show-close="!testingTool"
    :close-on-click-modal="!testingTool"
    :close-on-press-escape="!testingTool"
    title="测试工具源"
  >
    <ElForm label-position="top" class="settings-form compact">
      <ElFormItem label="工具函数">
        <ElSelect v-model="testingToolName" clearable placeholder="只解析 OpenAPI Schema">
          <ElOption
            v-for="tool in testingTools"
            :key="tool.function_name"
            :label="`${tool.label} (${tool.function_name})`"
            :value="tool.function_name"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem v-if="testingToolName" label="测试参数 JSON">
        <ElInput
          v-model="testArgumentsText"
          type="textarea"
          resize="vertical"
          :autosize="{ minRows: 4, maxRows: 10 }"
          placeholder='{"city": "Hong Kong"}'
        />
      </ElFormItem>
      <div v-if="testResult" class="tool-test-result">
        <div class="badge-row">
          <ElTag size="small" effect="plain">{{ testResult.tools.length }} 工具</ElTag>
          <ElTag
            v-if="testResult.result"
            size="small"
            effect="plain"
            :type="testResult.result.success === false ? 'danger' : 'success'"
          >
            {{ testResult.result.success === false ? '失败' : '成功' }}
          </ElTag>
        </div>
        <pre>{{ JSON.stringify(testResult.result ?? testResult.tools.map((tool) => tool.function_name), null, 2) }}</pre>
      </div>
    </ElForm>
    <template #footer>
      <ElButton :disabled="testingTool" @click="testDialogOpen = false">取消</ElButton>
      <ElButton type="primary" :loading="testingTool" @click="runToolRegistrationTest">测试</ElButton>
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
