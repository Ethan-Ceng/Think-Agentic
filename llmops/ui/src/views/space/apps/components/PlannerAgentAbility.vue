<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { PlannerWorkerBinding } from '@/models/app'
import {
  bindPlannerWorker,
  deletePlannerWorkerBinding,
  getAppsWithPage,
  getPlannerWorkers,
  updatePlannerWorkerBinding,
} from '@/services/app'
import { normalizeListPaginator } from '@/utils/paginated-response'

const props = defineProps({
  app_id: { type: String, default: '', required: true },
})

const loading = ref(false)
const bindingLoading = ref(false)
const bindings = ref<PlannerWorkerBinding[]>([])
const workerApps = ref<Record<string, any>[]>([])
const selectedWorkerAppId = ref('')

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

const loadData = async () => {
  loading.value = true
  try {
    await Promise.all([loadPlannerWorkers(), loadWorkerApps()])
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
          <el-table-column label="名称" min-width="160">
            <template #default="{ row }">
              <div class="flex min-w-0 items-center gap-2">
                <el-avatar :size="24" shape="square" :src="row.worker_app?.icon || row.worker_agent.icon" />
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-slate-900">
                    {{ row.worker_app?.name || row.worker_agent.name }}
                  </div>
                  <div class="truncate text-xs text-slate-400">{{ row.worker_agent.id }}</div>
                </div>
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
    </div>
  </div>
</template>
