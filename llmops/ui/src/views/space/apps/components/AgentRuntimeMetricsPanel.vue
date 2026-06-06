<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { AgentTaskRuntimeMetrics } from '@/models/agent-task'
import { getAppAgentRuntimeAnalysis } from '@/services/analysis'

const props = withDefaults(
  defineProps<{
    appId: string
    days?: number
  }>(),
  {
    days: 30,
  },
)

const loading = ref(false)
const runtimeMetrics = ref<AgentTaskRuntimeMetrics | null>(null)

const metricOverview = computed(() => runtimeMetrics.value?.overview || {})
const metricPlanner = computed(() => runtimeMetrics.value?.planner || {})
const metricWorker = computed(() => runtimeMetrics.value?.worker || {})
const metricStep = computed(() => runtimeMetrics.value?.step || {})
const metricTrace = computed(() => runtimeMetrics.value?.trace || {})
const metricWait = computed(() => runtimeMetrics.value?.wait || {})
const metricWorkerRows = computed(() => (runtimeMetrics.value?.worker?.by_worker || []).slice(0, 10))
const metricErrorRows = computed(() => (runtimeMetrics.value?.errors || []).slice(0, 10))

const loadMetrics = async () => {
  if (!props.appId) return
  loading.value = true
  try {
    const now = Math.floor(Date.now() / 1000)
    const res = await getAppAgentRuntimeAnalysis(props.appId, {
      from_ts: now - props.days * 24 * 60 * 60,
      to_ts: now,
      group_by: 'day',
    })
    runtimeMetrics.value = res.data
  } finally {
    loading.value = false
  }
}

function formatPercent(value?: number) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

function formatNumber(value?: number) {
  return new Intl.NumberFormat('zh-CN').format(Number(value || 0))
}

function formatCost(value?: number) {
  return `$${Number(value || 0).toFixed(4)}`
}

function formatSeconds(value?: number) {
  const seconds = Math.max(0, Math.round(value || 0))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}m ${rest}s`
}

function formatRatio(value?: number) {
  return Number(value || 0).toFixed(2)
}

watch(
  () => [props.appId, props.days],
  () => loadMetrics(),
)

onMounted(() => loadMetrics())
</script>

<template>
  <div v-loading="loading" class="space-y-4">
    <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <div class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="flex items-center gap-2 text-xs text-slate-500">
          <icon-dashboard class="text-base text-blue-600" />
          <span>任务数</span>
        </div>
        <div class="mt-2 text-xl font-semibold text-slate-900">
          {{ formatNumber(metricOverview.task_count) }}
        </div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="flex items-center gap-2 text-xs text-slate-500">
          <icon-bulb class="text-base text-emerald-600" />
          <span>成功率</span>
        </div>
        <div class="mt-2 text-xl font-semibold text-slate-900">
          {{ formatPercent(metricOverview.success_rate) }}
        </div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="flex items-center gap-2 text-xs text-slate-500">
          <icon-schedule class="text-base text-amber-600" />
          <span>等待数</span>
        </div>
        <div class="mt-2 text-xl font-semibold text-slate-900">
          {{ formatNumber(metricOverview.waiting_count) }}
        </div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="flex items-center gap-2 text-xs text-slate-500">
          <icon-language class="text-base text-indigo-600" />
          <span>平均耗时</span>
        </div>
        <div class="mt-2 text-xl font-semibold text-slate-900">
          {{ formatSeconds(metricOverview.avg_latency) }}
        </div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="flex items-center gap-2 text-xs text-slate-500">
          <icon-computer class="text-base text-cyan-600" />
          <span>Token</span>
        </div>
        <div class="mt-2 text-xl font-semibold text-slate-900">
          {{ formatNumber(metricOverview.total_token_count) }}
        </div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="flex items-center gap-2 text-xs text-slate-500">
          <icon-code class="text-base text-rose-600" />
          <span>成本</span>
        </div>
        <div class="mt-2 text-xl font-semibold text-slate-900">
          {{ formatCost(metricOverview.total_cost) }}
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <section class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="mb-3 flex items-center justify-between gap-3">
          <div class="text-sm font-semibold text-slate-900">Planner</div>
          <el-tag size="small" effect="plain">计划质量</el-tag>
        </div>
        <div class="space-y-2 text-sm text-slate-700">
          <div class="flex justify-between gap-3">
            <span>首计划成功率</span>
            <span class="font-medium">{{ formatPercent(metricPlanner.first_plan_success_rate) }}</span>
          </div>
          <div class="flex justify-between gap-3">
            <span>Replan Rate</span>
            <span class="font-medium">{{ formatPercent(metricPlanner.replan_rate) }}</span>
          </div>
          <div class="flex justify-between gap-3">
            <span>Plan Update Rate</span>
            <span class="font-medium">{{ formatPercent(metricPlanner.plan_update_rate) }}</span>
          </div>
          <div class="flex justify-between gap-3">
            <span>自动修复成功率</span>
            <span class="font-medium">{{ formatPercent(metricPlanner.auto_fix_success_rate) }}</span>
          </div>
          <div class="flex justify-between gap-3">
            <span>计划膨胀率</span>
            <span class="font-medium">{{ formatRatio(metricPlanner.avg_plan_inflation_ratio) }}</span>
          </div>
        </div>
      </section>

      <section class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="mb-3 flex items-center justify-between gap-3">
          <div class="text-sm font-semibold text-slate-900">Worker</div>
          <el-tag size="small" effect="plain" type="success">执行质量</el-tag>
        </div>
        <div class="space-y-2 text-sm text-slate-700">
          <div class="flex justify-between gap-3">
            <span>调用数</span>
            <span class="font-medium">{{ formatNumber(metricWorker.worker_call_count) }}</span>
          </div>
          <div class="flex justify-between gap-3">
            <span>成功率</span>
            <span class="font-medium">{{ formatPercent(metricWorker.worker_success_rate) }}</span>
          </div>
          <div class="flex justify-between gap-3">
            <span>等待数</span>
            <span class="font-medium">{{ formatNumber(metricWorker.worker_waiting_count) }}</span>
          </div>
          <div class="flex justify-between gap-3">
            <span>平均耗时</span>
            <span class="font-medium">{{ formatSeconds(metricWorker.avg_worker_latency) }}</span>
          </div>
        </div>
      </section>

      <section class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="mb-3 flex items-center justify-between gap-3">
          <div class="text-sm font-semibold text-slate-900">Trace</div>
          <el-tag size="small" effect="plain" type="info">可观测性</el-tag>
        </div>
        <div class="space-y-2 text-sm text-slate-700">
          <div class="flex justify-between gap-3">
            <span>事件数</span>
            <span class="font-medium">{{ formatNumber(metricTrace.trace_event_count) }}</span>
          </div>
          <div class="flex justify-between gap-3">
            <span>工具事件</span>
            <span class="font-medium">{{ formatNumber(metricTrace.tool_event_count) }}</span>
          </div>
          <div class="flex justify-between gap-3">
            <span>Preflight 失败</span>
            <span class="font-medium">{{ formatNumber(metricTrace.preflight_failed_count) }}</span>
          </div>
          <div class="flex justify-between gap-3">
            <span>Step 成功率</span>
            <span class="font-medium">{{ formatPercent(metricStep.step_success_rate) }}</span>
          </div>
        </div>
      </section>
    </div>

    <section class="rounded-lg border border-gray-200 bg-white p-4">
      <div class="mb-3 flex items-center justify-between gap-3">
        <div>
          <div class="text-sm font-semibold text-slate-900">Worker 排行</div>
          <div class="mt-1 text-xs text-slate-500">按调用量、成功率、等待和 Plan Update 观察 Worker 可靠性</div>
        </div>
      </div>
      <el-table :data="metricWorkerRows" stripe size="small">
        <el-table-column label="Worker" min-width="180">
          <template #default="{ row }">{{ row.worker_name || row.worker_agent_id }}</template>
        </el-table-column>
        <el-table-column label="调用" width="80">
          <template #default="{ row }">{{ row.call_count }}</template>
        </el-table-column>
        <el-table-column label="成功率" width="90">
          <template #default="{ row }">{{ formatPercent(row.success_rate) }}</template>
        </el-table-column>
        <el-table-column label="等待" width="80">
          <template #default="{ row }">{{ row.waiting_count }}</template>
        </el-table-column>
        <el-table-column label="Plan Update" width="120">
          <template #default="{ row }">{{ row.plan_update_count }}</template>
        </el-table-column>
        <el-table-column label="平均耗时" width="100">
          <template #default="{ row }">{{ formatSeconds(row.avg_latency) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!metricWorkerRows.length" description="暂无 Worker 调用数据" />
    </section>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <section class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="mb-3 text-sm font-semibold text-slate-900">等待信息</div>
        <div v-if="metricWait.by_type?.length" class="mb-3 flex flex-wrap gap-1">
          <el-tag
            v-for="item in metricWait.by_type"
            :key="`metric-wait-type-${item.wait_type}`"
            size="small"
            effect="plain"
            type="warning"
          >
            {{ item.wait_type || 'unknown' }} · {{ item.count }}
          </el-tag>
        </div>
        <div v-if="metricWait.missing_info?.length" class="flex flex-wrap gap-1">
          <el-tag
            v-for="item in metricWait.missing_info"
            :key="`metric-missing-${item.field}`"
            size="small"
            type="warning"
          >
            {{ item.field }} · {{ item.count }}
          </el-tag>
        </div>
        <el-empty
          v-else-if="!metricWait.by_type?.length"
          description="暂无等待字段"
        />
      </section>

      <section class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="mb-3 text-sm font-semibold text-slate-900">错误排行</div>
        <div v-if="metricErrorRows.length" class="space-y-2">
          <div
            v-for="item in metricErrorRows"
            :key="`metric-error-${item.error_code}`"
            class="flex justify-between gap-3 text-sm text-slate-700"
          >
            <span class="break-all">{{ item.error_code }}</span>
            <span class="font-medium">{{ item.count }}</span>
          </div>
        </div>
        <el-empty v-else description="暂无错误" />
      </section>
    </div>
  </div>
</template>
