<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { PlannerPreflightResult, PlannerWorkerBinding, WorkerCapabilitySummary } from '@/models/app'
import {
  bindPlannerWorker,
  deletePlannerWorkerBinding,
  getAppsWithPage,
  getPlannerWorkers,
  getPlannerRoutingPolicy,
  preflightPlannerWorkers,
  savePlannerRoutingPolicy,
  updatePlannerWorkerBinding,
  validatePlannerRoutingPolicy,
} from '@/services/app'
import { normalizeListPaginator } from '@/utils/paginated-response'
import CapabilitySummaryPanel from './CapabilitySummaryPanel.vue'

const props = defineProps({
  app_id: { type: String, default: '', required: true },
})

const loading = ref(false)
const bindingLoading = ref(false)
const routingLoading = ref(false)
const preflightLoading = ref(false)
const bindings = ref<PlannerWorkerBinding[]>([])
const workerApps = ref<Record<string, any>[]>([])
const selectedWorkerAppId = ref('')
const routingPolicyText = ref('{}')
const routingPolicyErrors = ref<Record<string, any>[]>([])
const routingPolicyWarnings = ref<Record<string, any>[]>([])
const preflightMessage = ref('')
const preflightInputModalities = ref<string[]>(['text/plain'])
const preflightResults = ref<PlannerPreflightResult[]>([])
const preflightStatus = ref('')

const boundWorkerAppIds = computed(() =>
  new Set(bindings.value.map((item) => item.worker_app?.id).filter(Boolean) as string[]),
)
const availableWorkerApps = computed(() =>
  workerApps.value.filter((app) => app.id !== props.app_id && !boundWorkerAppIds.value.has(app.id)),
)

const loadPlannerWorkers = async () => {
  if (!props.app_id) return
  bindingLoading.value = true
  try {
    const resp = await getPlannerWorkers(props.app_id)
    bindings.value = resp.data.list || []
  } finally {
    bindingLoading.value = false
  }
}

const loadWorkerApps = async () => {
  const resp = await getAppsWithPage({
    current_page: 1,
    page_size: 100,
    search_word: '',
    agent_type: 'worker',
  })
  const { list } = normalizeListPaginator<Record<string, any>>(resp.data as Record<string, any>)
  workerApps.value = list.map((item) => ({ ...item, agent_type: item.agent_type || 'worker' }))
}

const loadRoutingPolicy = async () => {
  if (!props.app_id) return
  routingLoading.value = true
  try {
    const resp = await getPlannerRoutingPolicy(props.app_id)
    routingPolicyText.value = JSON.stringify(resp.data.routing_policy || {}, null, 2)
    routingPolicyErrors.value = []
    routingPolicyWarnings.value = []
  } finally {
    routingLoading.value = false
  }
}

const loadData = async () => {
  loading.value = true
  try {
    await Promise.all([loadPlannerWorkers(), loadWorkerApps(), loadRoutingPolicy()])
  } finally {
    loading.value = false
  }
}

const addBinding = async () => {
  if (!selectedWorkerAppId.value) return
  await bindPlannerWorker(props.app_id, {
    worker_app_id: selectedWorkerAppId.value,
    enabled: true,
    priority: 0,
    conditions: {},
  })
  selectedWorkerAppId.value = ''
  ElMessage.success('WorkerAgent 已绑定')
  await loadData()
}

const saveBinding = async (binding: PlannerWorkerBinding) => {
  await updatePlannerWorkerBinding(props.app_id, binding.id, {
    enabled: binding.enabled,
    priority: Number(binding.priority || 0),
    conditions: binding.conditions || {},
  })
  ElMessage.success('绑定已更新')
  await loadPlannerWorkers()
}

const removeBinding = async (binding: PlannerWorkerBinding) => {
  await deletePlannerWorkerBinding(props.app_id, binding.id)
  ElMessage.success('绑定已删除')
  await loadData()
}

const parseRoutingPolicy = () => {
  try {
    const parsed = JSON.parse(routingPolicyText.value || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('routing_policy 必须是 JSON 对象')
    }
    return parsed as Record<string, any>
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'JSON 格式不正确')
    return null
  }
}

const validateRouting = async () => {
  const routing_policy = parseRoutingPolicy()
  if (!routing_policy) return false
  routingLoading.value = true
  try {
    const resp = await validatePlannerRoutingPolicy(props.app_id, { routing_policy })
    routingPolicyErrors.value = resp.data.errors || []
    routingPolicyWarnings.value = resp.data.warnings || []
    if (resp.data.valid) {
      ElMessage.success('编排规则校验通过')
    }
    return resp.data.valid
  } finally {
    routingLoading.value = false
  }
}

const saveRouting = async () => {
  const routing_policy = parseRoutingPolicy()
  if (!routing_policy) return
  routingLoading.value = true
  try {
    const resp = await savePlannerRoutingPolicy(props.app_id, { routing_policy })
    routingPolicyText.value = JSON.stringify(resp.data.routing_policy || {}, null, 2)
    routingPolicyErrors.value = []
    routingPolicyWarnings.value = []
    ElMessage.success('编排规则已保存')
  } finally {
    routingLoading.value = false
  }
}

const runPreflight = async () => {
  const message = preflightMessage.value.trim()
  if (!message) return
  preflightLoading.value = true
  try {
    const resp = await preflightPlannerWorkers(props.app_id, {
      message,
      input_modalities: preflightInputModalities.value,
    })
    preflightStatus.value = resp.data.status
    preflightResults.value = resp.data.results || []
  } finally {
    preflightLoading.value = false
  }
}

const capabilityTags = (summary?: WorkerCapabilitySummary) => summary?.semantic_tags || []

const firstFailedCheck = (result: PlannerPreflightResult) =>
  (result.checks || []).find((check) => !check.passed)

const preflightTagType = (result: PlannerPreflightResult) => (result.passed ? 'success' : 'danger')

watch(
  () => props.app_id,
  () => loadData(),
)

onMounted(loadData)
</script>

<template>
  <div v-loading="loading" class="flex h-full min-h-0 flex-col">
    <div class="shrink-0 border-b border-slate-200/75 bg-white/80 px-3 py-2">
      <div class="text-xs font-semibold leading-tight text-slate-900">Planner 编排</div>
      <div class="mt-0.5 line-clamp-1 text-[11px] leading-snug text-slate-500">
        WorkerAgent 绑定与执行优先级
      </div>
    </div>

    <div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-3 scrollbar-y-sleek">
      <section class="border border-slate-200 bg-white p-3">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div class="text-sm font-semibold text-slate-900">WorkerAgent</div>
          <div class="flex min-w-0 flex-1 justify-end gap-2">
            <el-select
              v-model="selectedWorkerAppId"
              clearable
              filterable
              class="min-w-[180px] max-w-[260px]"
              size="small"
            >
              <el-option
                v-for="app in availableWorkerApps"
                :key="app.id"
                :label="app.name"
                :value="app.id"
              />
            </el-select>
            <el-button size="small" type="primary" :disabled="!selectedWorkerAppId" @click="addBinding">
              绑定
            </el-button>
          </div>
        </div>

        <el-table v-loading="bindingLoading" :data="bindings" size="small" stripe>
          <el-table-column type="expand" width="42">
            <template #default="{ row }">
              <div class="px-3 py-2">
                <capability-summary-panel
                  title="绑定 Worker 能力"
                  :subtitle="row.worker_app?.name || row.worker_agent.name"
                  :summary="row.capability_summary"
                  compact
                  @refresh="loadPlannerWorkers"
                />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="名称" min-width="160">
            <template #default="{ row }">
              <div class="flex min-w-0 items-center gap-2">
                <el-avatar :size="24" shape="square" :src="row.worker_app?.icon || row.worker_agent.icon" />
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-slate-900">
                    {{ row.worker_app?.name || row.worker_agent.name }}
                  </div>
                  <div class="mt-0.5 flex min-w-0 flex-wrap items-center gap-1">
                    <el-tag size="small" type="info">{{ row.worker_agent.target_ref_type || 'worker' }}</el-tag>
                    <span class="truncate text-xs text-slate-400">{{ row.worker_agent.id }}</span>
                  </div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="能力" min-width="160">
            <template #default="{ row }">
              <div class="flex flex-wrap gap-1">
                <el-tag
                  v-for="tag in capabilityTags(row.capability_summary)"
                  :key="tag"
                  size="small"
                  type="info"
                >
                  {{ tag }}
                </el-tag>
                <span v-if="!capabilityTags(row.capability_summary).length" class="text-xs text-slate-400">
                  -
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" @change="() => saveBinding(row)" />
            </template>
          </el-table-column>
          <el-table-column label="优先级" width="120">
            <template #default="{ row }">
              <el-input-number
                v-model="row.priority"
                :min="0"
                :max="100"
                size="small"
                controls-position="right"
                @change="() => saveBinding(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" @click="() => removeBinding(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section v-loading="routingLoading" class="border border-slate-200 bg-white p-3">
        <div class="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-sm font-semibold text-slate-900">编排规则</div>
            <div class="mt-0.5 text-xs text-slate-500">routing_policy_v1</div>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <el-button size="small" @click="loadRoutingPolicy">
              <template #icon>
                <icon-sync />
              </template>
              恢复
            </el-button>
            <el-button size="small" @click="validateRouting">校验</el-button>
            <el-button size="small" type="primary" @click="saveRouting">保存</el-button>
          </div>
        </div>
        <el-input
          v-model="routingPolicyText"
          type="textarea"
          :rows="12"
          resize="vertical"
          spellcheck="false"
          class="font-mono"
        />
        <div v-if="routingPolicyErrors.length || routingPolicyWarnings.length" class="mt-3 space-y-2">
          <el-alert
            v-for="error in routingPolicyErrors"
            :key="`error-${error.field}-${error.message}`"
            type="error"
            :title="`${error.field || 'routing_policy'}: ${error.message || error}`"
            show-icon
            :closable="false"
          />
          <el-alert
            v-for="warning in routingPolicyWarnings"
            :key="`warning-${warning.field}-${warning.message}`"
            type="warning"
            :title="`${warning.field || 'routing_policy'}: ${warning.message || warning}`"
            show-icon
            :closable="false"
          />
        </div>
      </section>

      <section class="border border-slate-200 bg-white p-3">
        <div class="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-sm font-semibold text-slate-900">Preflight 诊断</div>
            <div class="mt-0.5 text-xs text-slate-500">按当前绑定 Worker 和编排规则检查输入</div>
          </div>
          <el-tag v-if="preflightStatus" size="small" :type="preflightStatus === 'succeeded' ? 'success' : 'danger'">
            {{ preflightStatus }}
          </el-tag>
        </div>
        <div class="space-y-3">
          <el-input
            v-model="preflightMessage"
            clearable
            placeholder="输入要诊断的问题"
            @keyup.enter="runPreflight"
          />
          <div class="flex flex-wrap items-center justify-between gap-2">
            <el-checkbox-group v-model="preflightInputModalities">
              <el-checkbox label="text/plain">文本</el-checkbox>
              <el-checkbox label="image/png">图片</el-checkbox>
              <el-checkbox label="application/pdf">PDF</el-checkbox>
            </el-checkbox-group>
            <el-button
              type="primary"
              :loading="preflightLoading"
              :disabled="!preflightMessage.trim()"
              @click="runPreflight"
            >
              诊断
            </el-button>
          </div>
          <el-table v-if="preflightResults.length" :data="preflightResults" size="small" stripe>
            <el-table-column label="Worker" min-width="160">
              <template #default="{ row }">
                <div class="font-medium text-slate-900">{{ row.worker_name || row.worker_id }}</div>
                <div class="truncate text-xs text-slate-400">{{ row.worker_id }}</div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="preflightTagType(row)">
                  {{ row.passed ? '通过' : '阻断' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="结果" min-width="220">
              <template #default="{ row }">
                <div v-if="firstFailedCheck(row)" class="text-xs text-red-600">
                  {{ firstFailedCheck(row)?.user_message || firstFailedCheck(row)?.error_code }}
                </div>
                <div v-else class="text-xs text-slate-500">能力校验通过</div>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>
    </div>
  </div>
</template>
