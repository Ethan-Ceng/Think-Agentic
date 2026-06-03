<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type {
  AgentArtifactRef,
  AgentFileRef,
  AgentTaskDetail,
  AgentTaskSummary,
  TraceEventItem,
  WorkerCallItem,
} from '@/models/agent-task'
import { getAppAgentTaskDetail, getAppAgentTasksWithPage } from '@/services/agent-task'
import JsonDrawer from './tasks/components/JsonDrawer.vue'
import TaskStatusTag from './tasks/components/TaskStatusTag.vue'

type StatusFilter = 'all' | 'created' | 'running' | 'waiting_approval' | 'succeeded' | 'failed' | 'cancelled'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const detailLoading = ref(false)
const tasks = ref<AgentTaskSummary[]>([])
const taskDetail = ref<AgentTaskDetail | null>(null)
const statusFilter = ref<StatusFilter>('all')
const searchWord = ref('')
const activeDetailTab = ref('plan')
const paginator = ref({
  current_page: 1,
  page_size: 20,
  total_page: 0,
  total_record: 0,
})

const jsonDrawerVisible = ref(false)
const jsonDrawerTitle = ref('')
const jsonDrawerData = ref<unknown>(null)

const appId = computed(() => String(route.params?.app_id || ''))
const selectedTaskId = computed(() => String(route.params?.task_id || ''))
const hasRunningTask = computed(() => tasks.value.some((task) => ['created', 'running', 'waiting_approval'].includes(task.status)))

const statusOptions: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: '全部状态' },
  { value: 'created', label: '已创建' },
  { value: 'running', label: '运行中' },
  { value: 'waiting_approval', label: '待审批' },
  { value: 'succeeded', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
]

const loadTasks = async (page = paginator.value.current_page) => {
  if (!appId.value) return
  loading.value = true
  try {
    const res = await getAppAgentTasksWithPage(appId.value, {
      current_page: page,
      page_size: paginator.value.page_size,
      status: statusFilter.value,
      search_word: searchWord.value.trim(),
    })
    tasks.value = res.data.list
    paginator.value = {
      current_page: res.data.current_page,
      page_size: res.data.page_size,
      total_page: res.data.total_page,
      total_record: res.data.total_record,
    }
  } finally {
    loading.value = false
  }
}

const loadDetail = async () => {
  taskDetail.value = null
  if (!appId.value || !selectedTaskId.value) return
  detailLoading.value = true
  try {
    const res = await getAppAgentTaskDetail(appId.value, selectedTaskId.value)
    taskDetail.value = res.data
  } finally {
    detailLoading.value = false
  }
}

const refresh = async () => {
  await loadTasks()
  await loadDetail()
}

const resetAndLoad = async () => {
  paginator.value.current_page = 1
  await loadTasks(1)
}

const openTask = async (task: AgentTaskSummary) => {
  await router.push({
    name: 'space-apps-task-detail',
    params: { app_id: appId.value, task_id: task.id },
  })
}

const openJson = (title: string, data: unknown) => {
  jsonDrawerTitle.value = title
  jsonDrawerData.value = data
  jsonDrawerVisible.value = true
}

const backToList = async () => {
  await router.push({ name: 'space-apps-tasks', params: { app_id: appId.value } })
}

const workerCallsForStep = (stepId: string) => {
  return taskDetail.value?.worker_calls.filter((call) => call.step_id === stepId) || []
}

const traceEventsForStep = (stepId: string) => {
  return taskDetail.value?.trace_events.filter((event) => event.step_id === stepId) || []
}

const workerAnswer = (call: WorkerCallItem) => {
  return String(call.result_json?.answer || call.result_json?.data?.answer || call.result_json?.summary || '')
}

const traceMessage = (event: TraceEventItem) => {
  return String(event.payload?.message || event.payload?.status || event.payload?.summary || event.payload?.event_type || '')
}

const fileName = (file: AgentFileRef | AgentArtifactRef) => {
  return file.name || file.metadata?.file?.name || file.file_id || file.id || '未命名文件'
}

const filePreviewUrl = (file: AgentFileRef | AgentArtifactRef) => {
  return file.preview_url || file.download_url || file.metadata?.file?.preview_url || file.metadata?.file?.download_url || ''
}

const fileDownloadUrl = (file: AgentFileRef | AgentArtifactRef) => {
  return file.download_url || file.preview_url || file.metadata?.file?.download_url || file.metadata?.file?.preview_url || ''
}

const openFile = (file: AgentFileRef | AgentArtifactRef, mode: 'preview' | 'download') => {
  const url = mode === 'preview' ? filePreviewUrl(file) : fileDownloadUrl(file)
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

const goToFileLibrary = async (file: AgentFileRef | AgentArtifactRef) => {
  await router.push({
    name: 'space-files-list',
    query: { search_word: fileName(file) },
  })
}

function formatDate(timestamp: number) {
  if (!timestamp) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp * 1000))
}

function formatDuration(startedAt: number, finishedAt: number) {
  if (!startedAt) return '-'
  const end = finishedAt || Math.floor(Date.now() / 1000)
  const seconds = Math.max(0, end - startedAt)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}m ${rest}s`
}

function formatFileSize(size?: number) {
  if (!size) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = size
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value >= 10 || unitIndex === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`
}

function runTypeLabel(runType: string) {
  if (runType === 'router') return 'Router'
  if (runType === 'worker') return 'Worker'
  return runType || '-'
}

function riskLabel(riskLevel?: string) {
  if (!riskLevel) return '-'
  if (riskLevel === 'low') return '低风险'
  if (riskLevel === 'medium') return '中风险'
  if (riskLevel === 'high') return '高风险'
  return riskLevel
}

watch([statusFilter], () => resetAndLoad())

watch(
  () => route.params?.task_id,
  () => loadDetail(),
)

watch(
  () => route.params?.app_id,
  async () => {
    await loadTasks(1)
    await loadDetail()
  },
)

onMounted(async () => {
  await loadTasks(1)
  await loadDetail()
})
</script>

<template>
  <div class="h-full min-h-0 overflow-hidden bg-slate-50 p-4">
    <div class="flex h-full min-h-0 flex-col gap-3">
      <section class="shrink-0 bg-white p-4 ring-1 ring-slate-200">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <h2 class="text-base font-semibold text-slate-900">执行记录</h2>
            <p class="mt-1 text-sm text-slate-500">Agent 任务运行历史</p>
          </div>
          <div class="flex shrink-0 flex-wrap items-center gap-2">
            <el-tag v-if="hasRunningTask" type="primary">存在运行中任务</el-tag>
            <el-button :loading="loading || detailLoading" @click="refresh">
              <template #icon>
                <icon-sync />
              </template>
              刷新
            </el-button>
          </div>
        </div>
      </section>

      <div class="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[380px_minmax(0,1fr)]">
        <section class="flex min-h-0 flex-col bg-white ring-1 ring-slate-200">
          <div class="shrink-0 border-b border-slate-100 p-3">
            <div class="flex flex-wrap items-center gap-2">
              <el-select v-model="statusFilter" class="w-[140px]" size="small">
                <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-input
                v-model="searchWord"
                clearable
                size="small"
                class="min-w-[160px] flex-1"
                placeholder="搜索输入"
                @clear="resetAndLoad"
                @keyup.enter="resetAndLoad"
              />
              <el-button size="small" @click="resetAndLoad">搜索</el-button>
            </div>
          </div>

          <div v-loading="loading" class="min-h-0 flex-1 overflow-auto">
            <button
              v-for="task in tasks"
              :key="task.id"
              :class="[
                'block w-full border-b border-slate-100 px-3 py-3 text-left transition-colors hover:bg-slate-50',
                selectedTaskId === task.id ? 'bg-blue-50' : 'bg-white',
              ]"
              @click="openTask(task)"
            >
              <div class="flex min-w-0 items-center justify-between gap-2">
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-slate-900">
                    {{ task.user_input_preview || task.summary || task.id }}
                  </div>
                  <div class="mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-slate-500">
                    <span>{{ runTypeLabel(task.run_type) }}</span>
                    <span>·</span>
                    <span>{{ task.step_count }} 步</span>
                    <span>·</span>
                    <span>{{ task.artifact_count }} 产物</span>
                  </div>
                </div>
                <task-status-tag :status="task.status" />
              </div>
              <div class="mt-2 flex items-center justify-between gap-2 text-xs text-slate-400">
                <span>{{ formatDate(task.created_at) }}</span>
                <span>{{ formatDuration(task.started_at, task.finished_at) }}</span>
              </div>
            </button>

            <el-empty v-if="!loading && !tasks.length" class="py-12" description="暂无执行记录" />
          </div>

          <div v-if="paginator.total_record > 0" class="shrink-0 border-t border-slate-100 p-3">
            <el-pagination
              v-model:current-page="paginator.current_page"
              v-model:page-size="paginator.page_size"
              small
              :page-sizes="[10, 20, 50]"
              :total="paginator.total_record"
              layout="total, prev, pager, next"
              @current-change="loadTasks"
              @size-change="resetAndLoad"
            />
          </div>
        </section>

        <section v-loading="detailLoading" class="min-h-0 overflow-auto bg-white ring-1 ring-slate-200">
          <el-empty v-if="!selectedTaskId" class="py-20" description="选择一条执行记录查看详情" />
          <el-empty v-else-if="!detailLoading && !taskDetail" class="py-20" description="任务详情不存在" />

          <div v-else-if="taskDetail" class="min-h-full">
            <header class="border-b border-slate-100 p-4">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="mb-2 flex flex-wrap items-center gap-2">
                    <task-status-tag :status="taskDetail.status" />
                    <el-tag size="small" type="info">{{ runTypeLabel(taskDetail.run_type) }}</el-tag>
                    <el-tag v-if="taskDetail.plan" size="small" type="warning">
                      {{ riskLabel(taskDetail.plan.risk_level) }}
                    </el-tag>
                  </div>
                  <h3 class="break-words text-base font-semibold text-slate-900">
                    {{ taskDetail.user_input_preview || taskDetail.summary || taskDetail.id }}
                  </h3>
                  <p v-if="taskDetail.summary" class="mt-1 break-words text-sm text-slate-500">
                    {{ taskDetail.summary }}
                  </p>
                  <p v-if="taskDetail.error_message" class="mt-1 break-words text-sm text-red-600">
                    {{ taskDetail.error_message }}
                  </p>
                </div>
                <div class="flex shrink-0 flex-wrap items-center gap-2">
                  <el-button @click="backToList">返回列表</el-button>
                  <el-button @click="openJson('任务 JSON', taskDetail)">查看 JSON</el-button>
                </div>
              </div>

              <div class="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
                <div class="bg-slate-50 p-3">
                  <div class="text-xs text-slate-500">步骤</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">{{ taskDetail.step_count }}</div>
                </div>
                <div class="bg-slate-50 p-3">
                  <div class="text-xs text-slate-500">Worker 调用</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">{{ taskDetail.worker_call_count }}</div>
                </div>
                <div class="bg-slate-50 p-3">
                  <div class="text-xs text-slate-500">产物</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">{{ taskDetail.artifact_count }}</div>
                </div>
                <div class="bg-slate-50 p-3">
                  <div class="text-xs text-slate-500">事件</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">{{ taskDetail.trace_count }}</div>
                </div>
                <div class="bg-slate-50 p-3">
                  <div class="text-xs text-slate-500">耗时</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">
                    {{ formatDuration(taskDetail.started_at, taskDetail.finished_at) }}
                  </div>
                </div>
              </div>
            </header>

            <el-tabs v-model="activeDetailTab" class="agent-task-tabs px-4">
              <el-tab-pane label="计划与步骤" name="plan">
                <div class="space-y-3 pb-4">
                  <div v-if="taskDetail.plan" class="flex flex-wrap items-center justify-between gap-2 bg-slate-50 p-3">
                    <div class="text-sm text-slate-600">
                      Schema：{{ taskDetail.plan.schema_version }} · 风险：{{ riskLabel(taskDetail.plan.risk_level) }}
                    </div>
                    <el-button size="small" @click="openJson('计划 JSON', taskDetail.plan.plan_json)">查看计划 JSON</el-button>
                  </div>

                  <el-empty v-if="!taskDetail.steps.length" description="暂无步骤" />
                  <el-timeline v-else>
                    <el-timeline-item
                      v-for="step in taskDetail.steps"
                      :key="step.id"
                      :timestamp="formatDate(step.created_at)"
                      placement="top"
                    >
                      <div class="border border-slate-200 bg-white p-3">
                        <div class="flex flex-wrap items-start justify-between gap-2">
                          <div class="min-w-0">
                            <div class="flex flex-wrap items-center gap-2">
                              <span class="font-medium text-slate-900">{{ step.step_key }}</span>
                              <task-status-tag :status="step.status" />
                              <el-tag size="small" type="info">{{ step.execution_mode }}</el-tag>
                            </div>
                            <div class="mt-1 text-sm text-slate-500">
                              {{ step.worker_agent?.name || '未知 Worker' }}
                            </div>
                            <div v-if="step.dependencies.length" class="mt-1 text-xs text-slate-400">
                              依赖：{{ step.dependencies.join(', ') }}
                            </div>
                          </div>
                          <div class="flex shrink-0 flex-wrap items-center gap-2">
                            <el-button size="small" @click="openJson('步骤输入', step.input_json)">输入</el-button>
                            <el-button size="small" @click="openJson('步骤输出', step.output_json)">输出</el-button>
                          </div>
                        </div>
                        <div v-if="workerCallsForStep(step.id).length" class="mt-3 text-xs text-slate-500">
                          Worker 调用 {{ workerCallsForStep(step.id).length }} 次 · 事件 {{ traceEventsForStep(step.id).length }} 条
                        </div>
                      </div>
                    </el-timeline-item>
                  </el-timeline>
                </div>
              </el-tab-pane>

              <el-tab-pane label="Worker 调用" name="workers">
                <div class="space-y-3 pb-4">
                  <el-empty v-if="!taskDetail.worker_calls.length" description="暂无 Worker 调用" />
                  <article v-for="call in taskDetail.worker_calls" :key="call.id" class="border border-slate-200 p-3">
                    <div class="flex flex-wrap items-start justify-between gap-2">
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                          <span class="font-medium text-slate-900">{{ call.worker_agent?.name || 'Worker' }}</span>
                          <task-status-tag :status="call.status" />
                          <span class="text-xs text-slate-400">{{ formatDate(call.created_at) }}</span>
                        </div>
                        <p v-if="workerAnswer(call)" class="mt-2 break-words text-sm text-slate-600">
                          {{ workerAnswer(call) }}
                        </p>
                      </div>
                      <div class="flex shrink-0 flex-wrap items-center gap-2">
                        <el-button size="small" @click="openJson('WorkerInvocation', call.invocation_json)">Invocation</el-button>
                        <el-button size="small" @click="openJson('WorkerResult', call.result_json)">Result</el-button>
                      </div>
                    </div>
                    <div class="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                      <span>Token：{{ call.token_count }}</span>
                      <span>成本：{{ call.cost }}</span>
                      <span>延迟：{{ call.latency }}s</span>
                    </div>
                  </article>
                </div>
              </el-tab-pane>

              <el-tab-pane label="文件与产物" name="files">
                <div class="grid grid-cols-1 gap-3 pb-4 lg:grid-cols-2">
                  <section class="border border-slate-200 p-3">
                    <div class="mb-3 font-medium text-slate-900">输入文件</div>
                    <el-empty v-if="!taskDetail.input_files.length" description="暂无输入文件" />
                    <div v-else class="space-y-2">
                      <div v-for="file in taskDetail.input_files" :key="file.file_id || file.id || file.name" class="bg-slate-50 p-3">
                        <div class="flex items-start gap-2">
                          <icon-file class="mt-0.5 shrink-0 text-slate-500" />
                          <div class="min-w-0 flex-1">
                            <div class="truncate text-sm font-medium text-slate-900">{{ fileName(file) }}</div>
                            <div class="mt-1 text-xs text-slate-500">
                              {{ file.mime_type || file.extension || '-' }} · {{ formatFileSize(file.size) }}
                            </div>
                            <p v-if="file.content" class="mt-2 line-clamp-3 break-words text-xs text-slate-500">
                              {{ file.content }}
                            </p>
                          </div>
                        </div>
                        <div class="mt-2 flex flex-wrap items-center gap-2">
                          <el-button size="small" :disabled="!filePreviewUrl(file)" @click="openFile(file, 'preview')">预览</el-button>
                          <el-button size="small" :disabled="!fileDownloadUrl(file)" @click="openFile(file, 'download')">下载</el-button>
                          <el-button size="small" @click="goToFileLibrary(file)">文件库</el-button>
                          <el-button size="small" @click="openJson('输入文件', file)">JSON</el-button>
                        </div>
                      </div>
                    </div>
                  </section>

                  <section class="border border-slate-200 p-3">
                    <div class="mb-3 font-medium text-slate-900">产物文件</div>
                    <el-empty v-if="!taskDetail.artifacts.length" description="暂无产物" />
                    <div v-else class="space-y-2">
                      <div v-for="artifact in taskDetail.artifacts" :key="artifact.file_id || artifact.artifact_id || artifact.name" class="bg-slate-50 p-3">
                        <div class="flex items-start gap-2">
                          <icon-file class="mt-0.5 shrink-0 text-blue-600" />
                          <div class="min-w-0 flex-1">
                            <div class="truncate text-sm font-medium text-slate-900">{{ fileName(artifact) }}</div>
                            <p v-if="artifact.summary" class="mt-1 break-words text-xs text-slate-500">
                              {{ artifact.summary }}
                            </p>
                          </div>
                        </div>
                        <div class="mt-2 flex flex-wrap items-center gap-2">
                          <el-button size="small" :disabled="!filePreviewUrl(artifact)" @click="openFile(artifact, 'preview')">预览</el-button>
                          <el-button size="small" :disabled="!fileDownloadUrl(artifact)" @click="openFile(artifact, 'download')">下载</el-button>
                          <el-button size="small" @click="goToFileLibrary(artifact)">文件库</el-button>
                          <el-button size="small" @click="openJson('产物', artifact)">JSON</el-button>
                        </div>
                      </div>
                    </div>
                  </section>
                </div>
              </el-tab-pane>

              <el-tab-pane label="执行日志" name="logs">
                <div class="pb-4">
                  <el-table :data="taskDetail.trace_events" stripe>
                    <el-table-column label="时间" width="170">
                      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
                    </el-table-column>
                    <el-table-column label="事件" min-width="220">
                      <template #default="{ row }">
                        <div class="font-medium text-slate-900">{{ row.event_type }}</div>
                        <div v-if="traceMessage(row)" class="truncate text-xs text-slate-500">{{ traceMessage(row) }}</div>
                      </template>
                    </el-table-column>
                    <el-table-column label="Step" width="160">
                      <template #default="{ row }">{{ row.step_id || '-' }}</template>
                    </el-table-column>
                    <el-table-column label="延迟" width="90">
                      <template #default="{ row }">{{ row.latency || '-' }}</template>
                    </el-table-column>
                    <el-table-column label="操作" width="90" fixed="right">
                      <template #default="{ row }">
                        <el-button link type="primary" @click="openJson('TraceEvent', row)">JSON</el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </el-tab-pane>
            </el-tabs>
          </div>
        </section>
      </div>
    </div>

    <json-drawer v-model:visible="jsonDrawerVisible" :title="jsonDrawerTitle" :data="jsonDrawerData" />
  </div>
</template>

<style scoped>
.agent-task-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
</style>
