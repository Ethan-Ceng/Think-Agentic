<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type {
  AgentArtifactRef,
  AgentConversationMessage,
  AgentConversationUserOption,
  AgentFileRef,
  AgentMessageTask,
  AgentStepItem,
  AgentTaskDetail,
  AgentTaskSummary,
  TraceEventItem,
  WorkerCallItem,
} from '@/models/agent-task'
import { getAppAgentTaskDetail, getAppAgentTasksWithPage } from '@/services/agent-task'
import JsonDrawer from './tasks/components/JsonDrawer.vue'
import TaskStatusTag from './tasks/components/TaskStatusTag.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const detailLoading = ref(false)
const records = ref<AgentTaskSummary[]>([])
const recordDetail = ref<AgentTaskDetail | null>(null)
const userOptions = ref<AgentConversationUserOption[]>([])
const selectedUserId = ref('all')
const searchWord = ref('')
const activeDetailTab = ref('messages')
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
const selectedRecordId = computed(() => String(route.params?.task_id || ''))
const messages = computed<AgentConversationMessage[]>(() => recordDetail.value?.messages || [])
const associatedTasks = computed<AgentTaskSummary[]>(() => recordDetail.value?.agent_tasks || [])
const traceEvents = computed<TraceEventItem[]>(() => recordDetail.value?.trace_events || [])

const loadRecords = async (page = paginator.value.current_page) => {
  if (!appId.value) return
  loading.value = true
  try {
    const res = await getAppAgentTasksWithPage(appId.value, {
      current_page: page,
      page_size: paginator.value.page_size,
      user_id: selectedUserId.value,
      search_word: searchWord.value.trim(),
    })
    records.value = res.data.list
    userOptions.value = res.data.users || []
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
  recordDetail.value = null
  if (!appId.value || !selectedRecordId.value) return
  detailLoading.value = true
  try {
    const res = await getAppAgentTaskDetail(appId.value, selectedRecordId.value)
    recordDetail.value = res.data
    activeDetailTab.value = 'messages'
  } finally {
    detailLoading.value = false
  }
}

const refresh = async () => {
  await loadRecords()
  await loadDetail()
}

const resetAndLoad = async () => {
  paginator.value.current_page = 1
  await loadRecords(1)
}

const openRecord = async (record: AgentTaskSummary) => {
  await router.push({
    name: 'space-apps-task-detail',
    params: { app_id: appId.value, task_id: record.id },
  })
}

const backToList = async () => {
  await router.push({ name: 'space-apps-tasks', params: { app_id: appId.value } })
}

const openJson = (title: string, data: unknown) => {
  jsonDrawerTitle.value = title
  jsonDrawerData.value = data
  jsonDrawerVisible.value = true
}

const recordTitle = (record: AgentTaskSummary) => {
  if (record.name && record.name !== 'New Conversation') return record.name
  return record.user_input_preview || record.summary || '新会话'
}

const sourceLabel = (source: string) => {
  const map: Record<string, string> = {
    debugger: '预览调试',
    web_app: '发布页',
    service_api: 'OpenAPI',
    assistant_agent: '助手',
    wechat: '微信',
    router: 'PlannerAgent',
    worker: 'Worker',
    conversation: '会话',
  }
  return map[source] || source || '-'
}

const traceMessage = (event: TraceEventItem) => {
  return String(
    event.payload?.message ||
      event.payload?.thought ||
      event.payload?.answer ||
      event.payload?.observation ||
      event.payload?.reason ||
      event.payload?.error_message ||
      '',
  )
}

const planSourceLabel = (source?: string) => {
  const map: Record<string, string> = {
    llm_planner_v1: 'LLM Planner',
    manager_rule_v1: '规则计划',
  }
  return map[String(source || '')] || source || ''
}

const taskPlanSource = (task: AgentMessageTask | AgentTaskDetail | AgentTaskSummary) => {
  const plan = (task as AgentMessageTask | AgentTaskDetail).plan
  return planSourceLabel(String(plan?.plan_json?.risk_assessment?.source || ''))
}

const messageAgentTasks = (message: AgentConversationMessage) => {
  return message.agent_tasks || []
}

const workerCallsForStep = (task: AgentMessageTask, stepId: string) => {
  return task.worker_calls.filter((call) => call.step_id === stepId)
}

const traceEventsForStep = (task: AgentMessageTask, stepId: string) => {
  return task.trace_events.filter((event) => event.step_id === stepId)
}

const workerAnswer = (call: WorkerCallItem) => {
  return String(call.result_json?.answer || call.result_json?.data?.answer || call.result_json?.summary || call.result_json?.error || '')
}

const stepOutputSummary = (step: AgentStepItem) => {
  return String(step.output_json?.answer || step.output_json?.summary || step.output_json?.error_message || step.output_json?.error || '')
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

function formatSeconds(value?: number) {
  const seconds = Math.max(0, Math.round(value || 0))
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

watch([selectedUserId], () => resetAndLoad())

watch(
  () => route.params?.task_id,
  () => loadDetail(),
)

watch(
  () => route.params?.app_id,
  async () => {
    await loadRecords(1)
    await loadDetail()
  },
)

onMounted(async () => {
  await loadRecords(1)
  await loadDetail()
})
</script>

<template>
  <div class="h-full min-h-0 overflow-hidden bg-slate-50 p-4">
    <div class="flex h-full min-h-0 flex-col gap-3">
      <section class="shrink-0 bg-white p-4 ring-1 ring-slate-200">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <h2 class="text-base font-semibold text-slate-900">会话记录</h2>
            <p class="mt-1 text-sm text-slate-500">按会话查看每轮对话和 Agent 执行事件</p>
          </div>
          <div class="flex shrink-0 flex-wrap items-center gap-2">
            <el-button :loading="loading || detailLoading" @click="refresh">
              <template #icon>
                <icon-sync />
              </template>
              刷新
            </el-button>
          </div>
        </div>
      </section>

      <div class="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[400px_minmax(0,1fr)]">
        <section class="flex min-h-0 flex-col bg-white ring-1 ring-slate-200">
          <div class="shrink-0 border-b border-slate-100 p-3">
            <div class="flex flex-wrap items-center gap-2">
              <el-select v-model="selectedUserId" class="w-[150px]" size="small">
                <el-option label="全部用户" value="all" />
                <el-option
                  v-for="item in userOptions"
                  :key="item.id"
                  :label="item.label"
                  :value="item.id"
                />
              </el-select>
              <el-input
                v-model="searchWord"
                clearable
                size="small"
                class="min-w-[160px] flex-1"
                placeholder="搜索会话或问题"
                @clear="resetAndLoad"
                @keyup.enter="resetAndLoad"
              />
              <el-button size="small" @click="resetAndLoad">搜索</el-button>
            </div>
          </div>

          <div v-loading="loading" class="min-h-0 flex-1 overflow-auto">
            <button
              v-for="record in records"
              :key="record.id"
              :class="[
                'block w-full border-b border-slate-100 px-3 py-3 text-left transition-colors hover:bg-slate-50',
                selectedRecordId === record.id ? 'bg-blue-50' : 'bg-white',
              ]"
              @click="openRecord(record)"
            >
              <div class="flex min-w-0 items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-slate-900">
                    {{ recordTitle(record) }}
                  </div>
                  <div class="mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-slate-500">
                    <span>{{ sourceLabel(record.run_type) }}</span>
                    <span>·</span>
                    <span>{{ record.message_count || 0 }} 轮</span>
                    <span>·</span>
                    <span>{{ record.trace_count }} 事件</span>
                  </div>
                </div>
                <task-status-tag :status="record.status" />
              </div>
              <div class="mt-2 flex items-center justify-between gap-2 text-xs text-slate-400">
                <span>{{ formatDate(record.updated_at || record.created_at) }}</span>
                <span>{{ formatSeconds(record.latency) }}</span>
              </div>
            </button>

            <el-empty v-if="!loading && !records.length" class="py-12" description="暂无会话记录" />
          </div>

          <div v-if="paginator.total_record > 0" class="shrink-0 border-t border-slate-100 p-3">
            <el-pagination
              v-model:current-page="paginator.current_page"
              v-model:page-size="paginator.page_size"
              small
              :page-sizes="[10, 20, 50]"
              :total="paginator.total_record"
              layout="total, prev, pager, next"
              @current-change="loadRecords"
              @size-change="resetAndLoad"
            />
          </div>
        </section>

        <section v-loading="detailLoading" class="min-h-0 overflow-auto bg-white ring-1 ring-slate-200">
          <el-empty v-if="!selectedRecordId" class="py-20" description="选择一个会话查看执行详情" />
          <el-empty v-else-if="!detailLoading && !recordDetail" class="py-20" description="会话记录不存在" />

          <div v-else-if="recordDetail" class="min-h-full">
            <header class="border-b border-slate-100 p-4">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="mb-2 flex flex-wrap items-center gap-2">
                    <task-status-tag :status="recordDetail.status" />
                    <el-tag size="small" type="info">{{ sourceLabel(recordDetail.run_type) }}</el-tag>
                  </div>
                  <h3 class="break-words text-base font-semibold text-slate-900">
                    {{ recordTitle(recordDetail) }}
                  </h3>
                  <p v-if="recordDetail.summary" class="mt-1 line-clamp-2 break-words text-sm text-slate-500">
                    {{ recordDetail.summary }}
                  </p>
                  <p v-if="recordDetail.error_message" class="mt-1 break-words text-sm text-red-600">
                    {{ recordDetail.error_message }}
                  </p>
                </div>
                <div class="flex shrink-0 flex-wrap items-center gap-2">
                  <el-button @click="backToList">返回列表</el-button>
                  <el-button @click="openJson('会话 JSON', recordDetail)">查看 JSON</el-button>
                </div>
              </div>

              <div class="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
                <div class="bg-slate-50 p-3">
                  <div class="text-xs text-slate-500">对话轮次</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">{{ recordDetail.message_count || 0 }}</div>
                </div>
                <div class="bg-slate-50 p-3">
                  <div class="text-xs text-slate-500">执行事件</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">{{ recordDetail.trace_count }}</div>
                </div>
                <div class="bg-slate-50 p-3">
                  <div class="text-xs text-slate-500">关联任务</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">{{ recordDetail.task_count || 0 }}</div>
                </div>
                <div class="bg-slate-50 p-3">
                  <div class="text-xs text-slate-500">Token</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">{{ recordDetail.total_token_count || 0 }}</div>
                </div>
                <div class="bg-slate-50 p-3">
                  <div class="text-xs text-slate-500">耗时</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">{{ formatSeconds(recordDetail.latency) }}</div>
                </div>
              </div>
            </header>

            <el-tabs v-model="activeDetailTab" class="execution-tabs px-4">
              <el-tab-pane label="对话轮次" name="messages">
                <div class="space-y-5 pb-4">
                  <el-empty v-if="!messages.length" description="暂无对话消息" />

                  <section v-for="(message, idx) in messages" :key="message.id" class="space-y-3">
                    <div class="flex justify-end">
                      <div class="max-w-[82%] min-w-0">
                        <div class="mb-1 text-right text-xs text-slate-400">
                          第 {{ idx + 1 }} 轮 · {{ formatDate(message.created_at) }}
                        </div>
                        <div class="rounded-md bg-blue-600 px-4 py-3 text-sm text-white">
                          <p class="whitespace-pre-wrap break-words">{{ message.query }}</p>
                          <div v-if="message.image_urls.length" class="mt-3 flex flex-wrap justify-end gap-2">
                            <el-image
                              v-for="url in message.image_urls"
                              :key="url"
                              :src="url"
                              :preview-src-list="message.image_urls"
                              fit="cover"
                              class="h-20 w-20 rounded border border-blue-200 bg-white/10"
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    <div class="flex justify-start">
                      <div class="max-w-[92%] min-w-0">
                        <div class="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                          <span class="font-medium text-slate-600">Agent</span>
                          <task-status-tag :status="message.status" />
                          <span>{{ formatSeconds(message.latency) }}</span>
                          <span>{{ message.total_token_count }} Token</span>
                          <span>{{ message.trace_events.length }} 事件</span>
                          <span v-if="messageAgentTasks(message).length">{{ messageAgentTasks(message).length }} 任务</span>
                        </div>

                        <div class="rounded-md bg-slate-100 px-4 py-3 text-sm text-slate-700">
                          <p v-if="message.answer" class="whitespace-pre-wrap break-words">{{ message.answer }}</p>
                          <p v-else-if="message.error" class="break-words text-red-600">{{ message.error }}</p>
                          <p v-else class="text-slate-400">暂无回答</p>
                        </div>

                        <div class="mt-2 flex flex-wrap items-center gap-2">
                          <el-button size="small" @click="openJson('消息 JSON', message)">消息 JSON</el-button>
                          <el-button
                            size="small"
                            :disabled="!message.trace_events.length"
                            @click="openJson('执行事件', message.trace_events)"
                          >
                            事件 JSON
                          </el-button>
                        </div>

                        <el-collapse v-if="messageAgentTasks(message).length" class="mt-2">
                          <el-collapse-item
                            v-for="task in messageAgentTasks(message)"
                            :key="task.id"
                            :name="task.id"
                          >
                            <template #title>
                              <div class="flex min-w-0 flex-1 items-center gap-2 pr-3">
                                <span class="truncate text-sm font-medium text-slate-900">
                                  {{ task.entry_agent?.name || sourceLabel(task.run_type) }}
                                </span>
                                <task-status-tag :status="task.status" />
                                <span class="shrink-0 text-xs text-slate-400">
                                  {{ task.step_count }} 步 · {{ task.worker_call_count }} Worker · {{ task.trace_count }} 事件
                                </span>
                                <el-tag v-if="taskPlanSource(task)" size="small" type="info">
                                  {{ taskPlanSource(task) }}
                                </el-tag>
                              </div>
                            </template>

                            <div class="space-y-3">
                              <div class="flex flex-wrap items-center justify-between gap-2 bg-slate-50 p-2 text-xs text-slate-500">
                                <span class="truncate">{{ task.user_input_preview || task.summary || task.id }}</span>
                                <div class="flex shrink-0 items-center gap-2">
                                  <el-button size="small" @click="openJson('AgentTask', task)">任务 JSON</el-button>
                                  <el-button size="small" :disabled="!task.plan" @click="openJson('AgentPlan', task.plan)">计划 JSON</el-button>
                                </div>
                              </div>

                              <el-empty v-if="!task.steps.length" description="暂无执行步骤" />
                              <el-timeline v-else>
                                <el-timeline-item
                                  v-for="step in task.steps"
                                  :key="step.id"
                                  :timestamp="formatDate(step.created_at)"
                                  placement="top"
                                >
                                  <div class="border border-slate-200 p-3">
                                    <div class="flex flex-wrap items-start justify-between gap-2">
                                      <div class="min-w-0">
                                        <div class="flex flex-wrap items-center gap-2">
                                          <span class="font-medium text-slate-900">{{ step.step_key }}</span>
                                          <task-status-tag :status="step.status" />
                                          <el-tag size="small" type="info">{{ step.execution_mode }}</el-tag>
                                        </div>
                                        <div class="mt-1 text-xs text-slate-500">
                                          {{ step.worker_agent?.name || '未知 Worker' }}
                                        </div>
                                      </div>
                                      <div class="flex shrink-0 flex-wrap items-center gap-2">
                                        <el-button size="small" @click="openJson('Step 输入', step.input_json)">输入</el-button>
                                        <el-button size="small" @click="openJson('Step 输出', step.output_json)">输出</el-button>
                                      </div>
                                    </div>

                                    <p v-if="stepOutputSummary(step)" class="mt-2 line-clamp-3 break-words text-xs text-slate-500">
                                      {{ stepOutputSummary(step) }}
                                    </p>

                                    <div v-if="workerCallsForStep(task, step.id).length" class="mt-3 space-y-2">
                                      <div
                                        v-for="call in workerCallsForStep(task, step.id)"
                                        :key="call.id"
                                        class="bg-slate-50 p-2"
                                      >
                                        <div class="flex flex-wrap items-center justify-between gap-2">
                                          <div class="flex min-w-0 flex-wrap items-center gap-2">
                                            <span class="truncate text-xs font-medium text-slate-900">
                                              {{ call.worker_agent?.name || 'Worker' }}
                                            </span>
                                            <task-status-tag :status="call.status" />
                                            <span class="text-xs text-slate-400">
                                              {{ formatSeconds(call.latency) }} · {{ call.token_count }} Token
                                            </span>
                                          </div>
                                          <div class="flex shrink-0 items-center gap-2">
                                            <el-button size="small" @click="openJson('WorkerInvocation', call.invocation_json)">Invocation</el-button>
                                            <el-button size="small" @click="openJson('WorkerResult', call.result_json)">Result</el-button>
                                          </div>
                                        </div>
                                        <p v-if="workerAnswer(call)" class="mt-2 line-clamp-3 break-words text-xs text-slate-500">
                                          {{ workerAnswer(call) }}
                                        </p>
                                      </div>
                                    </div>

                                    <div v-if="traceEventsForStep(task, step.id).length" class="mt-3">
                                      <el-table :data="traceEventsForStep(task, step.id)" stripe size="small">
                                        <el-table-column label="事件" min-width="180">
                                          <template #default="{ row }">
                                            <div class="font-medium text-slate-900">{{ row.event_type }}</div>
                                            <div v-if="traceMessage(row)" class="truncate text-xs text-slate-500">{{ traceMessage(row) }}</div>
                                          </template>
                                        </el-table-column>
                                        <el-table-column label="耗时" width="90">
                                          <template #default="{ row }">{{ formatSeconds(row.latency) }}</template>
                                        </el-table-column>
                                        <el-table-column label="操作" width="80">
                                          <template #default="{ row }">
                                            <el-button link type="primary" @click="openJson('TraceEvent', row)">JSON</el-button>
                                          </template>
                                        </el-table-column>
                                      </el-table>
                                    </div>
                                  </div>
                                </el-timeline-item>
                              </el-timeline>

                              <div v-if="task.artifacts.length" class="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                <span>产物 {{ task.artifacts.length }} 个</span>
                                <el-button size="small" @click="openJson('任务产物', task.artifacts)">产物 JSON</el-button>
                              </div>
                            </div>
                          </el-collapse-item>
                        </el-collapse>

                        <el-collapse v-if="message.trace_events.length" class="mt-2">
                          <el-collapse-item :title="`执行事件 ${message.trace_events.length}`" :name="message.id">
                            <el-table :data="message.trace_events" stripe size="small">
                              <el-table-column label="事件" min-width="180">
                                <template #default="{ row }">
                                  <div class="font-medium text-slate-900">{{ row.event_type }}</div>
                                  <div v-if="traceMessage(row)" class="truncate text-xs text-slate-500">{{ traceMessage(row) }}</div>
                                </template>
                              </el-table-column>
                              <el-table-column label="耗时" width="90">
                                <template #default="{ row }">{{ formatSeconds(row.latency) }}</template>
                              </el-table-column>
                              <el-table-column label="操作" width="80">
                                <template #default="{ row }">
                                  <el-button link type="primary" @click="openJson('TraceEvent', row)">JSON</el-button>
                                </template>
                              </el-table-column>
                            </el-table>
                          </el-collapse-item>
                        </el-collapse>
                      </div>
                    </div>
                  </section>
                </div>
              </el-tab-pane>

              <el-tab-pane label="执行日志" name="logs">
                <div class="pb-4">
                  <el-table :data="traceEvents" stripe>
                    <el-table-column label="时间" width="170">
                      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
                    </el-table-column>
                    <el-table-column label="事件" min-width="220">
                      <template #default="{ row }">
                        <div class="font-medium text-slate-900">{{ row.event_type }}</div>
                        <div v-if="traceMessage(row)" class="truncate text-xs text-slate-500">{{ traceMessage(row) }}</div>
                      </template>
                    </el-table-column>
                    <el-table-column label="Token" width="90">
                      <template #default="{ row }">{{ row.token_count || 0 }}</template>
                    </el-table-column>
                    <el-table-column label="耗时" width="90">
                      <template #default="{ row }">{{ formatSeconds(row.latency) }}</template>
                    </el-table-column>
                    <el-table-column label="操作" width="90" fixed="right">
                      <template #default="{ row }">
                        <el-button link type="primary" @click="openJson('TraceEvent', row)">JSON</el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </el-tab-pane>

              <el-tab-pane label="关联任务" name="tasks">
                <div class="space-y-3 pb-4">
                  <el-empty v-if="!associatedTasks.length" description="暂无 Router/Worker 任务" />
                  <article v-for="task in associatedTasks" :key="task.id" class="border border-slate-200 p-3">
                    <div class="flex flex-wrap items-start justify-between gap-2">
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                          <span class="font-medium text-slate-900">{{ task.user_input_preview || task.id }}</span>
                          <task-status-tag :status="task.status" />
                        </div>
                        <p v-if="task.summary" class="mt-2 line-clamp-2 break-words text-sm text-slate-600">
                          {{ task.summary }}
                        </p>
                      </div>
                      <el-button size="small" @click="openJson('AgentTask', task)">JSON</el-button>
                    </div>
                    <div class="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                      <span>Step: {{ task.step_count }}</span>
                      <span>Worker: {{ task.worker_call_count }}</span>
                      <span>事件: {{ task.trace_count }}</span>
                    </div>
                  </article>
                </div>
              </el-tab-pane>

              <el-tab-pane label="文件" name="files">
                <div class="grid grid-cols-1 gap-3 pb-4 lg:grid-cols-2">
                  <section class="border border-slate-200 p-3">
                    <div class="mb-3 font-medium text-slate-900">输入文件</div>
                    <el-empty v-if="!recordDetail.input_files.length" description="暂无输入文件" />
                    <div v-else class="space-y-2">
                      <div v-for="file in recordDetail.input_files" :key="file.file_id || file.id || file.name" class="bg-slate-50 p-3">
                        <div class="truncate text-sm font-medium text-slate-900">{{ fileName(file) }}</div>
                        <div class="mt-1 text-xs text-slate-500">
                          {{ file.mime_type || file.extension || file.source || '-' }} · {{ formatFileSize(file.size) }}
                        </div>
                        <div class="mt-2 flex flex-wrap items-center gap-2">
                          <el-button size="small" :disabled="!filePreviewUrl(file)" @click="openFile(file, 'preview')">预览</el-button>
                          <el-button size="small" :disabled="!fileDownloadUrl(file)" @click="openFile(file, 'download')">下载</el-button>
                          <el-button size="small" @click="openJson('输入文件', file)">JSON</el-button>
                        </div>
                      </div>
                    </div>
                  </section>

                  <section class="border border-slate-200 p-3">
                    <div class="mb-3 font-medium text-slate-900">产物文件</div>
                    <el-empty v-if="!recordDetail.artifacts.length" description="暂无产物" />
                    <div v-else class="space-y-2">
                      <div v-for="artifact in recordDetail.artifacts" :key="artifact.file_id || artifact.artifact_id || artifact.name" class="bg-slate-50 p-3">
                        <div class="truncate text-sm font-medium text-slate-900">{{ fileName(artifact) }}</div>
                        <p v-if="artifact.summary" class="mt-1 break-words text-xs text-slate-500">
                          {{ artifact.summary }}
                        </p>
                        <div class="mt-2 flex flex-wrap items-center gap-2">
                          <el-button size="small" :disabled="!filePreviewUrl(artifact)" @click="openFile(artifact, 'preview')">预览</el-button>
                          <el-button size="small" :disabled="!fileDownloadUrl(artifact)" @click="openFile(artifact, 'download')">下载</el-button>
                          <el-button size="small" @click="openJson('产物', artifact)">JSON</el-button>
                        </div>
                      </div>
                    </div>
                  </section>
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
.execution-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
</style>
