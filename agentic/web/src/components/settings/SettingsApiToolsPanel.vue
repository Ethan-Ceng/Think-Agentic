<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Loader2, Pencil, Play, Plus, RotateCcw, Trash } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { toolsApi } from '@/lib/api/tools'
import type {
  RuntimeToolPolicy,
  ToolDescriptor,
  ToolListData,
  ToolRegistration,
  ToolRegistrationTestData,
  ToolRiskLevel,
} from '@/lib/api/types'
import type { SettingsPanelEmits } from './types'

const emit = defineEmits<SettingsPanelEmits>()
const toast = useToast()
const tools = ref<ToolDescriptor[]>([])
const registrations = ref<ToolRegistration[]>([])
const runtimePolicy = ref<RuntimeToolPolicy>({ allowed_executor_types: ['builtin', 'mcp', 'a2a', 'api'], max_tool_iterations: 100 })
const initialSnapshot = ref('')
const loading = ref(true)
const loadError = ref('')

const registrationDialogOpen = ref(false)
const addingRegistration = ref(false)
const editingRegistrationId = ref<string | null>(null)
const registrationForm = ref(defaultRegistrationForm())
const registrationInitialSnapshot = ref('')
const testDialogOpen = ref(false)
const testingRegistration = ref<ToolRegistration | null>(null)
const testingToolName = ref('')
const testArgumentsText = ref('{}')
const testingTool = ref(false)
const testResult = ref<ToolRegistrationTestData | null>(null)

function defaultRegistrationForm() {
  return {
    provider_id: '', provider_label: '', group: 'custom', category: '自定义', description: '', enabled: true,
    base_url: '', timeout: 60, headers_text: '', openapi_schema_text: '', allow_private_network: false,
  }
}

const apiRegistrations = computed(() => registrations.value.filter((item) => !item.builtin && item.source_type === 'api'))
const providerIds = computed(() => new Set(apiRegistrations.value.map((item) => item.provider_id)))
const apiTools = computed(() => tools.value.filter((tool) => tool.executor_type === 'api' && providerIds.value.has(tool.provider_id)))
const toolGroups = computed(() => apiRegistrations.value.map((registration) => ({
  key: registration.provider_id,
  title: registration.provider_label,
  tools: apiTools.value.filter((tool) => tool.provider_id === registration.provider_id),
})).filter((group) => group.tools.length > 0))

const summary = computed(() => {
  const enabled = apiTools.value.filter((tool) => tool.enabled)
  return {
    enabled: enabled.length,
    total: apiTools.value.length,
    highRisk: enabled.filter((tool) => tool.risk_level === 'high').length,
    credentials: enabled.filter((tool) => tool.requires_credentials).length,
  }
})

function bindingsSnapshot() {
  return JSON.stringify(apiTools.value.map((tool) => ({ id: tool.tool_id, enabled: tool.enabled })).sort((a, b) => a.id.localeCompare(b.id)))
}

const dirty = computed(() => Boolean(initialSnapshot.value) && bindingsSnapshot() !== initialSnapshot.value)
watch(dirty, (value) => emit('dirty-change', value), { immediate: true })

const registrationDialogTitle = computed(() => editingRegistrationId.value ? '编辑 API Tool' : '新增 API Tool')
const registrationSubmitText = computed(() => editingRegistrationId.value ? '保存' : '新增')
const registrationDirty = computed(() => JSON.stringify(registrationForm.value) !== registrationInitialSnapshot.value)
const testingTools = computed(() => testingRegistration.value ? apiTools.value.filter((tool) => tool.provider_id === testingRegistration.value?.provider_id) : [])

function applyData(data: ToolListData | null | undefined) {
  tools.value = data?.tools ?? []
  registrations.value = data?.registrations ?? []
  runtimePolicy.value = data?.runtime_policy ?? runtimePolicy.value
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    applyData(await toolsApi.listTools())
    initialSnapshot.value = bindingsSnapshot()
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : 'API Tools 加载失败'
  } finally { loading.value = false }
}

onMounted(load)

function buildBindings() {
  return Object.fromEntries(apiTools.value.map((tool) => [tool.tool_id, { enabled: tool.enabled, risk_level: tool.risk_level, params: {} }]))
}

async function save() {
  try {
    applyData(await toolsApi.updateBindings({ bindings: buildBindings(), runtime_policy: runtimePolicy.value }))
    initialSnapshot.value = bindingsSnapshot()
    toast.success('API Tools 配置保存成功')
    return true
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'API Tools 配置保存失败')
    return false
  }
}

function isDirty() { return dirty.value }

function handleToolSwitch(toolId: string, value: string | number | boolean) {
  tools.value = tools.value.map((tool) => tool.tool_id === toolId ? { ...tool, enabled: Boolean(value) } : tool)
}

function registrationToolCount(providerId: string) { return apiTools.value.filter((tool) => tool.provider_id === providerId).length }
function stringifyConfigValue(value: unknown) { return value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value, null, 2) }

function openRegistrationDialog() {
  editingRegistrationId.value = null
  registrationForm.value = defaultRegistrationForm()
  registrationInitialSnapshot.value = JSON.stringify(registrationForm.value)
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
  registrationInitialSnapshot.value = JSON.stringify(registrationForm.value)
  registrationDialogOpen.value = true
}

function parseJsonObject(text: string, label: string) {
  const content = text.trim()
  if (!content) return {}
  const parsed: unknown = JSON.parse(content)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error(`${label} 必须是 JSON 对象`)
  return parsed as Record<string, unknown>
}

function buildRegistrationConfig() {
  const schema = registrationForm.value.openapi_schema_text.trim()
  if (!schema) throw new Error('请填写 OpenAPI Schema')
  const config: Record<string, unknown> = {
    openapi_schema: schema,
    timeout: registrationForm.value.timeout,
    allow_private_network: registrationForm.value.allow_private_network,
  }
  const baseUrl = registrationForm.value.base_url.trim()
  if (baseUrl) config.base_url = baseUrl
  const headers = parseJsonObject(registrationForm.value.headers_text, 'Headers')
  if (Object.keys(headers).length) config.headers = headers
  return config
}

async function submitRegistration() {
  const providerId = registrationForm.value.provider_id.trim()
  const providerLabel = registrationForm.value.provider_label.trim()
  if (!providerId || !providerLabel) { toast.error('请填写工具源 ID 和名称'); return }
  let config: Record<string, unknown>
  try { config = buildRegistrationConfig() }
  catch (error) { toast.error(error instanceof Error ? error.message : '工具源配置格式错误'); return }

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
    const editing = editingRegistrationId.value
    if (editing) await toolsApi.updateRegistration(editing, payload)
    else await toolsApi.createRegistration(payload)
    registrationDialogOpen.value = false
    applyData(await toolsApi.listTools())
    initialSnapshot.value = bindingsSnapshot()
    toast.success(editing ? 'API Tool 已保存' : 'API Tool 注册成功')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'API Tool 保存失败')
  } finally { addingRegistration.value = false }
}

async function requestRegistrationClose(done?: () => void) {
  if (addingRegistration.value) return
  if (!registrationDirty.value) {
    if (done) done(); else registrationDialogOpen.value = false
    return
  }
  try {
    await ElMessageBox.confirm('关闭后，本次尚未保存的 Provider 修改将丢失。', '放弃修改？', { confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning' })
    if (done) done(); else registrationDialogOpen.value = false
  } catch { /* keep editing */ }
}

async function toggleRegistration(registration: ToolRegistration, enabled: boolean) {
  const previous = registrations.value
  registrations.value = registrations.value.map((item) => item.registration_id === registration.registration_id ? { ...item, enabled } : item)
  try {
    await toolsApi.updateRegistration(registration.registration_id, { enabled })
    applyData(await toolsApi.listTools())
    initialSnapshot.value = bindingsSnapshot()
    toast.success(`API Tool 已${enabled ? '启用' : '禁用'}`)
  } catch {
    registrations.value = previous
    toast.error('API Tool 状态更新失败')
  }
}

async function deleteRegistration(registration: ToolRegistration) {
  try {
    await ElMessageBox.confirm(
      `删除后将移除「${registration.provider_label}」及其已解析 Operations，历史运行记录不会被删除。`,
      '删除 API Provider？',
      { confirmButtonText: '删除 Provider', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' },
    )
  } catch { return }
  try {
    await toolsApi.deleteRegistration(registration.registration_id)
    applyData(await toolsApi.listTools())
    initialSnapshot.value = bindingsSnapshot()
    toast.success('工具源已删除')
  } catch { toast.error('工具源删除失败') }
}

function openTestDialog(registration: ToolRegistration) {
  testingRegistration.value = registration
  testResult.value = null
  testingToolName.value = apiTools.value.find((tool) => tool.provider_id === registration.provider_id)?.function_name ?? ''
  testArgumentsText.value = '{}'
  testDialogOpen.value = true
}

async function runTest() {
  if (!testingRegistration.value) return
  let args: Record<string, unknown> = {}
  if (testingToolName.value) {
    try { args = parseJsonObject(testArgumentsText.value, 'Arguments') }
    catch (error) { toast.error(error instanceof Error ? error.message : '测试参数格式错误'); return }
  }
  testingTool.value = true
  try {
    testResult.value = await toolsApi.testRegistration(testingRegistration.value.registration_id, { function_name: testingToolName.value || null, arguments: args })
    applyData(await toolsApi.listTools())
    initialSnapshot.value = bindingsSnapshot()
    const result = testResult.value.result
    if (result?.success === false) toast.error(result.message || '工具测试失败')
    else toast.success(result ? '工具测试完成' : '工具源解析完成')
  } catch (error) { toast.error(error instanceof Error ? error.message : '工具源测试失败') }
  finally { testingTool.value = false }
}

function riskTagType(risk: ToolRiskLevel) { return risk === 'high' ? 'danger' : risk === 'medium' ? 'warning' : 'success' }
function riskLabel(risk: ToolRiskLevel) { return risk === 'high' ? '高危' : risk === 'medium' ? '中等' : '低风险' }

defineExpose({ isDirty, save })
</script>

<template>
  <section class="settings-list tools-settings">
    <header class="settings-section-heading">
      <div><span>Tools</span><h3>API Tools</h3></div>
      <p>注册和管理通过 OpenAPI/HTTP 接入的外部工具。Provider 启停立即生效，Operation 启停需保存。</p>
      <ElButton type="primary" size="small" @click="openRegistrationDialog"><Plus :size="14" />新增 API Tool</ElButton>
    </header>

    <div v-if="loading" class="center-state" aria-live="polite"><Loader2 :size="22" class="spin" /><span>正在加载 API Tools</span></div>
    <div v-else-if="loadError" class="settings-error-state" role="alert"><p>{{ loadError }}</p><ElButton @click="load"><RotateCcw :size="15" />重试</ElButton></div>
    <template v-else>
      <div class="tool-summary-grid">
        <div class="tool-summary-item"><span>Provider</span><strong>{{ apiRegistrations.length }}</strong></div>
        <div class="tool-summary-item"><span>已启用工具</span><strong>{{ summary.enabled }} / {{ summary.total }}</strong></div>
        <div class="tool-summary-item"><span>高风险工具</span><strong>{{ summary.highRisk }}</strong></div>
        <div class="tool-summary-item"><span>需要凭证</span><strong>{{ summary.credentials }}</strong></div>
      </div>

      <section class="settings-card tool-registration-card">
        <div class="settings-card-title"><strong>API Providers</strong></div>
        <ElEmpty v-if="apiRegistrations.length === 0" description="暂无 API Tool，请先新增 Provider" />
        <div v-else class="tool-registration-list">
          <article v-for="registration in apiRegistrations" :key="registration.registration_id" class="tool-registration-row">
            <div class="tool-registration-main">
              <div class="tool-row-heading"><strong>{{ registration.provider_label }}</strong><code>{{ registration.provider_id }}</code></div>
              <p>{{ registration.description || '未配置描述' }}</p>
              <div class="badge-row"><ElTag size="small" effect="plain">API</ElTag><ElTag size="small" effect="plain">{{ registrationToolCount(registration.provider_id) }} 工具</ElTag><ElTag v-if="registration.requires_credentials" size="small" effect="plain">凭证</ElTag></div>
            </div>
            <div class="tool-registration-controls">
              <ElButton text size="small" :aria-label="`测试 ${registration.provider_label}`" @click="openTestDialog(registration)"><Play :size="14" /></ElButton>
              <ElButton text size="small" :aria-label="`编辑 ${registration.provider_label}`" @click="openEditRegistrationDialog(registration)"><Pencil :size="14" /></ElButton>
              <ElButton text type="danger" size="small" :aria-label="`删除 ${registration.provider_label}`" @click="deleteRegistration(registration)"><Trash :size="14" /></ElButton>
              <ElSwitch :model-value="registration.enabled" inline-prompt active-text="开" inactive-text="关" :aria-label="`${registration.provider_label} 启用状态`" @change="toggleRegistration(registration, Boolean($event))" />
            </div>
          </article>
        </div>
      </section>

      <ElEmpty v-if="toolGroups.length === 0" description="暂无已解析的 API operations" />
      <section v-for="group in toolGroups" v-else :key="group.key" class="tool-group">
        <h4>{{ group.title }} · Operations</h4>
        <article v-for="tool in group.tools" :key="tool.tool_id" class="tool-row">
          <div class="tool-row-main"><div class="tool-row-heading"><strong>{{ tool.label }}</strong><code>{{ tool.function_name }}</code></div><p>{{ tool.description }}</p><div class="badge-row"><ElTag size="small" effect="plain" :type="riskTagType(tool.risk_level)">{{ riskLabel(tool.risk_level) }}</ElTag><ElTag size="small" effect="plain">API</ElTag><ElTag v-if="tool.requires_credentials" size="small" effect="plain">凭证</ElTag></div></div>
          <div class="tool-row-controls"><ElSwitch :model-value="tool.enabled" inline-prompt active-text="开" inactive-text="关" :aria-label="`${tool.label} 启用状态`" @change="handleToolSwitch(tool.tool_id, $event)" /></div>
        </article>
      </section>
    </template>
  </section>

  <ElDialog v-model="registrationDialogOpen" width="min(720px, calc(100vw - 24px))" append-to-body align-center class="settings-sub-dialog" :show-close="!addingRegistration" :close-on-click-modal="false" :close-on-press-escape="false" :before-close="requestRegistrationClose" :title="registrationDialogTitle">
    <ElForm label-position="top" class="settings-form compact">
      <div class="settings-field-grid"><ElFormItem label="Provider ID"><ElInput v-model="registrationForm.provider_id" placeholder="api.weather" clearable :disabled="Boolean(editingRegistrationId)" /></ElFormItem><ElFormItem label="Provider 名称"><ElInput v-model="registrationForm.provider_label" placeholder="天气 API" clearable /></ElFormItem></div>
      <ElFormItem label="Base URL"><ElInput v-model="registrationForm.base_url" placeholder="https://api.example.com" clearable /></ElFormItem>
      <ElFormItem label="超时时间"><ElInputNumber v-model="registrationForm.timeout" :min="1" :max="600" :step="1" controls-position="right" /></ElFormItem>
      <ElFormItem label="Headers JSON"><ElInput v-model="registrationForm.headers_text" type="textarea" resize="vertical" :autosize="{ minRows: 2, maxRows: 5 }" placeholder='{"Authorization": "env:MY_API_TOKEN"}' /></ElFormItem>
      <ElFormItem label="OpenAPI Schema"><ElInput v-model="registrationForm.openapi_schema_text" type="textarea" resize="vertical" :autosize="{ minRows: 8, maxRows: 16 }" placeholder='{"openapi":"3.0.0","paths":{}}' /></ElFormItem>
      <ElFormItem label="描述"><ElInput v-model="registrationForm.description" type="textarea" resize="vertical" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="描述这个工具源提供的能力" /></ElFormItem>
      <div class="tool-registration-flags"><ElCheckbox v-model="registrationForm.enabled">启用 Provider</ElCheckbox><ElCheckbox v-model="registrationForm.allow_private_network">允许内网地址</ElCheckbox></div>
    </ElForm>
    <template #footer><ElButton :disabled="addingRegistration" @click="requestRegistrationClose()">取消</ElButton><ElButton type="primary" :loading="addingRegistration" @click="submitRegistration">{{ registrationSubmitText }}</ElButton></template>
  </ElDialog>

  <ElDialog v-model="testDialogOpen" width="min(680px, calc(100vw - 24px))" append-to-body align-center class="settings-sub-dialog" :show-close="!testingTool" :close-on-click-modal="!testingTool" :close-on-press-escape="!testingTool" title="测试工具源">
    <ElForm label-position="top" class="settings-form compact">
      <ElFormItem label="工具函数"><ElSelect v-model="testingToolName" clearable placeholder="只解析 OpenAPI Schema"><ElOption v-for="tool in testingTools" :key="tool.function_name" :label="`${tool.label} (${tool.function_name})`" :value="tool.function_name" /></ElSelect></ElFormItem>
      <ElFormItem v-if="testingToolName" label="测试参数 JSON"><ElInput v-model="testArgumentsText" type="textarea" resize="vertical" :autosize="{ minRows: 4, maxRows: 10 }" placeholder='{"city": "Hong Kong"}' /></ElFormItem>
      <div v-if="testResult" class="tool-test-result"><div class="badge-row"><ElTag size="small" effect="plain">{{ testResult.tools.length }} 工具</ElTag><ElTag v-if="testResult.result" size="small" effect="plain" :type="testResult.result.success === false ? 'danger' : 'success'">{{ testResult.result.success === false ? '失败' : '成功' }}</ElTag></div><pre>{{ JSON.stringify(testResult.result ?? testResult.tools.map((tool) => tool.function_name), null, 2) }}</pre></div>
    </ElForm>
    <template #footer><ElButton :disabled="testingTool" @click="testDialogOpen = false">取消</ElButton><ElButton type="primary" :loading="testingTool" @click="runTest">测试</ElButton></template>
  </ElDialog>
</template>
