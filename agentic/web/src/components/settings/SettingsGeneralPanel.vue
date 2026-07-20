<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ClipboardCheck, Loader2, RotateCcw } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { configApi } from '@/lib/api/config'
import { toolsApi } from '@/lib/api/tools'
import type {
  AgentConfig,
  RuntimeToolPolicy,
  ToolApprovalPolicy,
  ToolApprovalSetting,
  ToolDescriptor,
  ToolExecutorType,
  ToolListData,
  ToolPreflightResponse,
} from '@/lib/api/types'
import type { SettingsPanelEmits } from './types'

const emit = defineEmits<SettingsPanelEmits>()
const toast = useToast()

const agentConfig = ref<AgentConfig>({})
const tools = ref<ToolDescriptor[]>([])
const approvalTools = ref<ToolApprovalSetting[]>([])
const initialApprovals = ref<Record<string, ToolApprovalPolicy>>({})
const runtimePolicy = ref<RuntimeToolPolicy>({
  allowed_executor_types: ['builtin', 'mcp', 'a2a', 'api'],
  max_tool_iterations: 100,
  require_approval_for_high_risk: true,
})
const initialSnapshot = ref('')
const loading = ref(true)
const loadError = ref('')
const checkingPreflight = ref(false)
const preflightMessage = ref('')
const preflightResult = ref<ToolPreflightResponse | null>(null)

const executorOptions: Array<{ value: ToolExecutorType; label: string }> = [
  { value: 'mcp', label: 'MCP' },
  { value: 'a2a', label: 'A2A' },
  { value: 'api', label: 'API' },
]

function snapshot() {
  return JSON.stringify({
    agent: agentConfig.value,
    policy: runtimePolicy.value,
    approvals: approvalTools.value.map(({ tool_id, approval }) => ({ tool_id, approval })),
  })
}

const dirty = computed(() => Boolean(initialSnapshot.value) && snapshot() !== initialSnapshot.value)
watch(dirty, (value) => emit('dirty-change', value), { immediate: true })

const visiblePreflightChecks = computed(() =>
  preflightResult.value?.checks.filter(
    (check) => !check.passed || check.user_message !== '未检测到该能力需求。',
  ) ?? [],
)

function applyToolListData(data: ToolListData | null | undefined) {
  tools.value = data?.tools ?? []
  approvalTools.value = (data?.approval_tools ?? []).map((item) => ({ ...item }))
  initialApprovals.value = Object.fromEntries(
    approvalTools.value.map(({ tool_id, approval }) => [tool_id, approval]),
  )
  const nextPolicy = data?.runtime_policy ?? runtimePolicy.value
  runtimePolicy.value = {
    ...nextPolicy,
    require_approval_for_high_risk: nextPolicy.require_approval_for_high_risk ?? true,
    allowed_executor_types: Array.from(
      new Set<ToolExecutorType>(['builtin', ...nextPolicy.allowed_executor_types]),
    ),
  }
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [agent, toolData] = await Promise.all([
      configApi.getAgentConfig(),
      toolsApi.listTools(),
    ])
    agentConfig.value = agent || {}
    applyToolListData(toolData)
    initialSnapshot.value = snapshot()
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '通用配置加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function buildToolBindings() {
  return Object.fromEntries([
    ...tools.value
      .filter((tool) => tool.executor_type === 'api')
      .map((tool) => [
        tool.tool_id,
        { enabled: tool.enabled, risk_level: tool.risk_level, params: {} },
      ]),
    ...approvalTools.value
      .filter((tool) => tool.approval !== initialApprovals.value[tool.tool_id])
      .map((tool) => [
        tool.tool_id,
        {
          enabled: true,
          risk_level: tool.risk_level,
          approval: tool.approval,
        },
      ]),
  ])
}

async function save() {
  try {
    const [, toolData] = await Promise.all([
      configApi.updateAgentConfig(agentConfig.value),
      toolsApi.updateBindings({
        bindings: buildToolBindings(),
        runtime_policy: runtimePolicy.value,
      }),
    ])
    applyToolListData(toolData)
    initialSnapshot.value = snapshot()
    toast.success('通用配置保存成功')
    return true
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '通用配置保存失败')
    return false
  }
}

function isDirty() {
  return dirty.value
}

function handleExecutorSwitch(type: ToolExecutorType, value: string | number | boolean) {
  const next = new Set(runtimePolicy.value.allowed_executor_types)
  if (Boolean(value)) next.add(type)
  else next.delete(type)
  runtimePolicy.value = { ...runtimePolicy.value, allowed_executor_types: Array.from(next) }
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
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '检测失败')
  } finally {
    checkingPreflight.value = false
  }
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

const approvalOptions: Array<{ value: ToolApprovalPolicy; label: string }> = [
  { value: 'auto', label: '按风险策略' },
  { value: 'allow', label: '始终允许' },
  { value: 'ask', label: '每次确认' },
  { value: 'deny', label: '禁止执行' },
]

function approvalHint(approval: ToolApprovalPolicy) {
  if (approval === 'allow') return '始终允许会跳过后续确认，请只用于可信的沙箱能力。'
  if (approval === 'ask') return '每次调用都需要在会话中确认。'
  if (approval === 'deny') return 'Agent 无法执行该工具。'
  return runtimePolicy.value.require_approval_for_high_risk
    ? '按风险策略：高风险调用需要确认。'
    : '按风险策略：全局确认已关闭，将直接执行。'
}

defineExpose({ isDirty, save })
</script>

<template>
  <div v-if="loading" class="center-state" aria-live="polite">
    <Loader2 :size="22" class="spin" />
    <span>正在加载通用配置</span>
  </div>
  <div v-else-if="loadError" class="settings-error-state" role="alert">
    <p>{{ loadError }}</p>
    <ElButton @click="load"><RotateCcw :size="15" />重试</ElButton>
  </div>
  <ElForm v-else label-position="top" class="settings-form">
    <header class="settings-section-heading">
      <div><span>运行时</span><h3>Agent 执行策略</h3></div>
      <p>控制任务规划、失败重试与外部能力的使用边界。</p>
    </header>

    <div class="settings-field-grid">
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
    </div>

    <section class="settings-card tool-policy-card">
      <div class="settings-card-title"><strong>高级运行策略</strong></div>
      <div class="tool-policy-grid">
        <label v-for="option in executorOptions" :key="option.value" class="tool-policy-switch">
          <span>{{ option.label }}</span>
          <ElSwitch
            :model-value="runtimePolicy.allowed_executor_types.includes(option.value)"
            inline-prompt active-text="开" inactive-text="关"
            @change="handleExecutorSwitch(option.value, $event)"
          />
        </label>
        <label class="tool-policy-number">
          <span>最大工具迭代</span>
          <ElInputNumber v-model="runtimePolicy.max_tool_iterations" :min="1" :max="1000" :step="1" controls-position="right" />
        </label>
        <label class="tool-policy-switch">
          <span>高风险工具执行前确认</span>
          <ElSwitch
            v-model="runtimePolicy.require_approval_for_high_risk"
            inline-prompt
            active-text="开"
            inactive-text="关"
          />
        </label>
      </div>
      <div v-if="approvalTools.length" class="tool-approval-settings">
        <div class="tool-approval-heading">
          <strong>系统工具审批</strong>
          <span>配置会持久保存，只影响后续调用；当前待确认操作仍需处理。</span>
        </div>
        <div
          v-for="tool in approvalTools"
          :key="tool.tool_id"
          class="tool-approval-row"
          :data-tool-id="tool.tool_id"
        >
          <div class="tool-approval-copy">
            <strong>{{ tool.label }}</strong>
            <code>{{ tool.function_name }}</code>
            <p>{{ approvalHint(tool.approval) }}</p>
          </div>
          <ElSelect
            v-model="tool.approval"
            :aria-label="`${tool.label}审批策略`"
            class="tool-approval-select"
          >
            <ElOption
              v-for="option in approvalOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </ElSelect>
        </div>
      </div>
    </section>

    <section class="settings-card tool-preflight-card">
      <div class="settings-card-title"><strong>能力预检</strong></div>
      <p class="settings-card-description">输入任务描述，检查当前工具和运行策略能否满足执行要求。</p>
      <div class="tool-preflight-input">
        <ElInput v-model="preflightMessage" type="textarea" resize="vertical" :autosize="{ minRows: 3, maxRows: 6 }" placeholder="输入任务描述" />
        <ElButton type="primary" :loading="checkingPreflight" @click="runPreflight">
          <ClipboardCheck :size="14" />检测
        </ElButton>
      </div>
      <div v-if="preflightResult" class="tool-preflight-result" aria-live="polite">
        <ElTag size="small" effect="light" :type="preflightStatusType(preflightResult.status)">{{ preflightStatusLabel(preflightResult.status) }}</ElTag>
        <div class="tool-preflight-checks">
          <p v-for="check in visiblePreflightChecks" :key="check.rule_id" :class="{ failed: !check.passed }">{{ check.user_message }}</p>
        </div>
      </div>
    </section>
  </ElForm>
</template>
