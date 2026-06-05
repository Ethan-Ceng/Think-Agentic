<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type {
  AgentArtifactRef,
  AgentConversationMessage,
  AgentConversationUserOption,
  AgentFileRef,
  AgentMessageTask,
  AgentPlanItem,
  AgentStepItem,
  AgentTaskDetail,
  AgentTaskRuntimeMetrics,
  AgentTaskSummary,
  TraceEventItem,
  WorkerCallItem,
} from '@/models/agent-task'
import { dryRunPlanner } from '@/services/app'
import { getAppAgentTaskDetail, getAppAgentTaskMetrics, getAppAgentTasksWithPage } from '@/services/agent-task'
import JsonDrawer from './tasks/components/JsonDrawer.vue'
import TaskStatusTag from './tasks/components/TaskStatusTag.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const detailLoading = ref(false)
const metricsLoading = ref(false)
const records = ref<AgentTaskSummary[]>([])
const recordDetail = ref<AgentTaskDetail | null>(null)
const runtimeMetrics = ref<AgentTaskRuntimeMetrics | null>(null)
const userOptions = ref<AgentConversationUserOption[]>([])
const selectedUserId = ref('all')
const searchWord = ref('')
const activeDetailTab = ref('messages')
const logAgentFilter = ref('all')
const logTypeFilter = ref('all')
const logSearchWord = ref('')
const showLogPayload = ref(false)
const dryRunQuery = ref('')
const dryRunLoading = ref(false)
const dryRunResult = ref<Record<string, any> | null>(null)
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
const waitEvents = computed<TraceEventItem[]>(() => traceEvents.value.filter((event) => isWaitEvent(event)))
const currentWaitEvent = computed<TraceEventItem | null>(() => waitEvents.value[waitEvents.value.length - 1] || null)
const metricOverview = computed(() => runtimeMetrics.value?.overview || {})
const metricPlanner = computed(() => runtimeMetrics.value?.planner || {})
const metricWorker = computed(() => runtimeMetrics.value?.worker || {})
const metricStep = computed(() => runtimeMetrics.value?.step || {})
const metricTrace = computed(() => runtimeMetrics.value?.trace || {})
const metricWait = computed(() => runtimeMetrics.value?.wait || {})
const metricWorkerRows = computed(() => (runtimeMetrics.value?.worker?.by_worker || []).slice(0, 10))
const metricErrorRows = computed(() => (runtimeMetrics.value?.errors || []).slice(0, 10))

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
    dryRunQuery.value = res.data.user_input_preview || String(res.data.user_input?.query || '')
    dryRunResult.value = null
  } finally {
    detailLoading.value = false
  }
}

const loadMetrics = async () => {
  if (!appId.value) return
  metricsLoading.value = true
  try {
    const now = Math.floor(Date.now() / 1000)
    const res = await getAppAgentTaskMetrics(appId.value, {
      from_ts: now - 30 * 24 * 60 * 60,
      to_ts: now,
      user_id: selectedUserId.value,
      group_by: 'day',
    })
    runtimeMetrics.value = res.data
  } finally {
    metricsLoading.value = false
  }
}

const refresh = async () => {
  await loadRecords()
  await loadDetail()
  await loadMetrics()
}

const resetAndLoad = async () => {
  paginator.value.current_page = 1
  await loadRecords(1)
  await loadMetrics()
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

const uniqueTexts = (values: unknown[]) => {
  return Array.from(
    new Set(
      values
        .map((value) => String(value || '').trim())
        .filter(Boolean),
    ),
  )
}

const traceAgentName = (event: TraceEventItem) => {
  const payload = event.payload || {}
  const directName = event.agent?.name || event.step?.worker_agent?.name || event.worker_call?.worker_agent?.name
  if (directName) return directName

  const plannedSteps = Array.isArray(payload.planned_steps) ? payload.planned_steps : []
  const workerLists = [payload.workers, payload.selected_workers, payload.candidate_workers].filter(Array.isArray)
  const names = uniqueTexts([
    ...plannedSteps.map((step: Record<string, any>) => step.worker_name),
    ...workerLists.flat().map((worker: Record<string, any>) => worker.name),
    payload.worker_name,
  ])
  return names.join(' / ')
}

const traceStepName = (event: TraceEventItem) => {
  const payload = event.payload || {}
  if (event.step?.step_key) return event.step.step_key
  return String(payload.step_key || payload.failed_step_key || '')
}

const traceTaskText = (event: TraceEventItem) => {
  const payload = event.payload || {}
  if (event.step?.task) return event.step.task
  if (payload.task || payload.failed_step_task) return String(payload.task || payload.failed_step_task)

  const plannedSteps = Array.isArray(payload.planned_steps) ? payload.planned_steps : []
  const tasks = uniqueTexts(plannedSteps.map((step: Record<string, any>) => step.task))
  if (!tasks.length) return ''
  if (tasks.length <= 2) return tasks.join(' / ')
  return `${tasks.slice(0, 2).join(' / ')} 等 ${tasks.length} 个任务`
}

const traceSelectionReason = (event: TraceEventItem) => {
  const payload = event.payload || {}
  const plannedSteps = Array.isArray(payload.planned_steps) ? payload.planned_steps : []
  const reasons = uniqueTexts([
    event.step?.selection_reason,
    payload.selection_reason,
    payload.planning_reason,
    ...plannedSteps.map((step: Record<string, any>) => step.selection_reason),
    payload.reason,
  ])
  return reasons.slice(0, 2).join(' / ')
}

const traceSelectionSignals = (event: TraceEventItem) => {
  const payload = event.payload || {}
  const plannedSteps = Array.isArray(payload.planned_steps) ? payload.planned_steps : []
  const values = [
    ...(Array.isArray(event.step?.selection_signals) ? event.step?.selection_signals || [] : []),
    ...(Array.isArray(payload.selection_signals) ? payload.selection_signals : []),
    ...plannedSteps.flatMap((step: Record<string, any>) =>
      Array.isArray(step.selection_signals) ? step.selection_signals : [],
    ),
  ]
  return uniqueTexts(values).slice(0, 4)
}

const tracePayloadSummary = (event: TraceEventItem) => {
  const payload = event.payload || {}
  const plannedSteps = Array.isArray(payload.planned_steps) ? payload.planned_steps : []
  if (plannedSteps.length) {
    return `${plannedSteps.length} step · ${uniqueTexts(plannedSteps.map((step: Record<string, any>) => step.worker_name)).join(' / ')}`
  }
  return toPreview(payload, 180)
}

const matchesLogType = (event: TraceEventItem, type: string) => {
  const eventType = event.event_type || ''
  if (type === 'all') return true
  if (type === 'failed') {
    return eventType.includes('failed') || String(event.payload?.status || '').includes('failed')
  }
  if (type === 'replan') return eventType.includes('replan')
  if (type === 'plan_update') return eventType.includes('plan_update')
  if (type === 'preflight') return eventType.includes('preflight')
  if (type === 'wait') return eventType.startsWith('wait.')
  return eventType.startsWith(`${type}.`)
}

const isPlaybackEvent = (event: TraceEventItem) => {
  const eventType = event.event_type || ''
  return (
    eventType.startsWith('planner.') ||
    eventType === 'router.manager_run.created' ||
    eventType.startsWith('router.capability_preflight') ||
    eventType.startsWith('planner.replan.preflight') ||
    eventType.startsWith('planner.plan_update.preflight')
  )
}

const playbackSteps = (event: TraceEventItem) => {
  const payload = event.payload || {}
  const snapshot = payload.plan_snapshot || payload.new_plan || payload.current_plan_snapshot
  if (Array.isArray(snapshot?.steps)) return snapshot.steps
  if (Array.isArray(payload.planned_steps)) return payload.planned_steps
  return []
}

const playbackDiff = (event: TraceEventItem) => {
  const diff = event.payload?.plan_diff
  return diff && typeof diff === 'object' ? diff : null
}

const playbackStatusType = (event: TraceEventItem) => {
  const status = String(event.payload?.status || event.event_type || '')
  if (status.includes('failed') || status.includes('fallback') || status.includes('blocked')) return 'danger'
  if (status.includes('succeeded') || status.includes('validated') || status.includes('applied')) return 'success'
  return 'info'
}

const logAgentOptions = computed(() => {
  return uniqueTexts(
    traceEvents.value.flatMap((event) => traceAgentName(event).split('/').map((name) => name.trim())),
  )
})

const filteredTraceEvents = computed(() => {
  const keyword = logSearchWord.value.trim().toLowerCase()
  return traceEvents.value.filter((event) => {
    const agentName = traceAgentName(event)
    if (logAgentFilter.value !== 'all' && !agentName.includes(logAgentFilter.value)) return false
    if (!matchesLogType(event, logTypeFilter.value)) return false
    if (!keyword) return true
    return [
      event.event_type,
      traceMessage(event),
      agentName,
      traceStepName(event),
      traceTaskText(event),
      traceSelectionReason(event),
    ]
      .join(' ')
      .toLowerCase()
      .includes(keyword)
  })
})

const playbackEvents = computed(() => traceEvents.value.filter(isPlaybackEvent))

const planSourceLabel = (source?: string) => {
  const map: Record<string, string> = {
    llm_planner_v1: 'LLM Planner',
    llm_replan_v1: 'LLM Replan',
    llm_plan_feedback_v1: 'Feedback Update',
    manager_rule_v1: '规则计划',
    manager_replan_rule_v1: 'Rule Replan',
  }
  return map[String(source || '')] || source || ''
}

const taskPlanSource = (task: AgentMessageTask | AgentTaskDetail | AgentTaskSummary) => {
  const plan = (task as AgentMessageTask | AgentTaskDetail).plan
  return planSourceLabel(String(plan?.plan_json?.risk_assessment?.source || ''))
}

const planAttempt = (plan?: AgentPlanItem | null) => {
  return Number(plan?.plan_json?.replan?.attempt || plan?.plan_json?.plan_update?.attempt || 0)
}

const taskReplanCount = (task: AgentMessageTask | AgentTaskDetail) => {
  return Array.isArray(task.plans) ? task.plans.filter((plan) => plan.plan_json?.replan).length : 0
}

const taskPlanUpdateCount = (task: AgentMessageTask | AgentTaskDetail) => {
  return Array.isArray(task.plans) ? task.plans.filter((plan) => plan.plan_json?.plan_update).length : 0
}

const planForStep = (task: AgentMessageTask, step: AgentStepItem) => {
  return task.plans.find((plan) => plan.id === step.plan_id) || null
}

const stepPlanAttempt = (task: AgentMessageTask, step: AgentStepItem) => {
  return planAttempt(planForStep(task, step))
}

const workerCallPlanAttempt = (call: WorkerCallItem) => {
  return Number(call.invocation_json?.execution_policy?.plan_attempt || 0)
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

const toPreview = (value: unknown, limit = 220) => {
  if (value === null || value === undefined || value === '') return ''
  let text = ''
  if (typeof value === 'string') {
    text = value
  } else {
    try {
      text = JSON.stringify(value)
    } catch {
      text = String(value)
    }
  }
  return text.length <= limit ? text : `${text.slice(0, limit)}...`
}

const stepTaskText = (step: AgentStepItem) => {
  return String(step.task || step.input_json?.task || '')
}

const stepSelectionReason = (step: AgentStepItem) => {
  return String(
    step.selection_reason ||
      step.input_json?.planner_selection?.reason ||
      step.input_json?.planner_selection?.selection_reason ||
      '',
  )
}

const stepSelectionSignals = (step: AgentStepItem) => {
  const direct = Array.isArray(step.selection_signals) ? step.selection_signals : []
  const nested = Array.isArray(step.input_json?.planner_selection?.signals)
    ? step.input_json.planner_selection.signals
    : []
  return uniqueTexts([...direct, ...nested]).slice(0, 4)
}

const stepInputSummary = (step: AgentStepItem) => {
  return step.input_preview || stepTaskText(step) || toPreview(step.input_json)
}

const stepExpectedOutput = (step: AgentStepItem) => {
  return String(step.expected_output || step.input_json?.expected_output || '')
}

const stepSuccessCriteria = (step: AgentStepItem) => {
  const value = Array.isArray(step.success_criteria) ? step.success_criteria : step.input_json?.success_criteria
  return Array.isArray(value) ? uniqueTexts(value) : []
}

const stepRequiredArtifacts = (step: AgentStepItem) => {
  const value = Array.isArray(step.required_artifacts) ? step.required_artifacts : step.input_json?.required_artifacts
  return Array.isArray(value) ? uniqueTexts(value) : []
}

const stepHandoffContext = (step: AgentStepItem) => {
  return String(step.handoff_context || step.input_json?.handoff_context || '')
}

const hasStepContract = (step: AgentStepItem) => {
  return Boolean(
    stepExpectedOutput(step) ||
      stepSuccessCriteria(step).length ||
      stepRequiredArtifacts(step).length ||
      stepHandoffContext(step),
  )
}

const taskPreflight = (task: AgentMessageTask | AgentTaskDetail) => {
  const preflight = task.plan?.plan_json?.preflight
  return preflight && typeof preflight === 'object' ? preflight : null
}

const stepPreflight = (step: AgentStepItem) => {
  const preflight = step.input_json?.preflight
  return preflight && typeof preflight === 'object' ? preflight : null
}

const preflightChecks = (preflight: Record<string, any> | null) => {
  return Array.isArray(preflight?.checks) ? preflight.checks : []
}

const firstFailedPreflightCheck = (preflight: Record<string, any> | null) => {
  return preflightChecks(preflight).find((check) => !check?.passed)
}

const preflightStatusType = (status?: string, passed?: boolean) => {
  if (passed === false || status === 'failed') return 'danger'
  if (passed === true || status === 'succeeded') return 'success'
  return 'info'
}

const stepOutputSummary = (step: AgentStepItem) => {
  return String(
    step.output_preview ||
      step.output_json?.answer ||
      step.output_json?.summary ||
      step.output_json?.error_message ||
      step.output_json?.error ||
      '',
  )
}

const workerInputSummary = (call: WorkerCallItem) => {
  return call.invocation_preview || String(call.invocation_json?.task?.task || call.invocation_json?.task || '')
}

const workerOutputSummary = (call: WorkerCallItem) => {
  return call.result_preview || workerAnswer(call)
}

const workerRuntime = (call: WorkerCallItem) => {
  const runtime = call.result_json?.data?.runtime || call.result_json?.runtime
  return runtime && typeof runtime === 'object' ? runtime : null
}

const workerInternalSteps = (call: WorkerCallItem) => {
  const steps = call.result_json?.data?.internal_steps || call.result_json?.internal_steps
  return Array.isArray(steps) ? steps : []
}

const workerResultEvents = (call: WorkerCallItem) => {
  const events = call.result_json?.events
  return Array.isArray(events) ? events : []
}

const workerToolEvents = (call: WorkerCallItem) => {
  return workerResultEvents(call).filter((event: Record<string, any>) =>
    String(event.event_type || '').startsWith('worker.tool.'),
  )
}

const workerRuntimeFinalState = (call: WorkerCallItem) => {
  return String(workerRuntime(call)?.final_state || call.status || '')
}

const workerRuntimeLabel = (call: WorkerCallItem) => {
  const runtime = workerRuntime(call)
  if (!runtime) return ''
  const iterations = Number(runtime.iterations || 0)
  const maxIterations = Number(runtime.max_iterations || 0)
  if (!iterations && !maxIterations) return String(runtime.mode || '')
  return `${iterations}/${maxIterations || '-'} 轮`
}

const workerRuntimePolicyLabel = (call: WorkerCallItem) => {
  const executors = workerRuntime(call)?.policy?.allowed_executor_types
  if (!Array.isArray(executors) || executors.length === 0) return ''
  return executors.join(' / ')
}

const workerMemoryCompaction = (call: WorkerCallItem) => {
  const memory = call.result_json?.data?.memory_compaction || call.result_json?.memory_compaction
  return memory && typeof memory === 'object' ? memory : null
}

const workerReplanSignal = (call: WorkerCallItem) => {
  const signal = call.result_json?.data?.replan_signal || call.result_json?.replan_signal
  return signal && typeof signal === 'object' ? signal : null
}

const workerReplanLabel = (call: WorkerCallItem) => {
  const signal = workerReplanSignal(call)
  if (!signal?.needs_replan) return ''
  return String(signal.reason || 'needs_replan')
}

const workerPlanFeedback = (call: WorkerCallItem) => {
  const feedback = call.result_json?.data?.plan_feedback || call.result_json?.plan_feedback
  return feedback && typeof feedback === 'object' ? feedback : null
}

const workerPlanFeedbackMissingInfo = (call: WorkerCallItem) => {
  const missingInfo = workerPlanFeedback(call)?.missing_info
  return Array.isArray(missingInfo) ? uniqueTexts(missingInfo).slice(0, 3) : []
}

const workerPlanFeedbackArtifactCount = (call: WorkerCallItem) => {
  const artifacts = workerPlanFeedback(call)?.artifact_refs
  return Array.isArray(artifacts) ? artifacts.length : 0
}

const workerPlanFeedbackReason = (call: WorkerCallItem) => {
  return String(workerPlanFeedback(call)?.reason_code || '')
}

const hasWorkerPlanFeedback = (call: WorkerCallItem) => {
  const feedback = workerPlanFeedback(call)
  return Boolean(
    feedback &&
      (feedback.completed_enough ||
        feedback.needs_plan_update ||
        feedback.reason_code ||
        workerPlanFeedbackMissingInfo(call).length ||
        workerPlanFeedbackArtifactCount(call)),
  )
}

const isWaitEvent = (event: TraceEventItem) => {
  return String(event.event_type || '').startsWith('wait.') || Boolean(event.payload?.wait_type)
}

const waitTypeLabel = (event?: TraceEventItem | null) => {
  const type = String(event?.payload?.wait_type || '')
  const map: Record<string, string> = {
    user_input: '等待用户输入',
    approval: '等待审批',
    external_callback: '等待外部回调',
    schedule: '等待定时恢复',
    rate_limit: '等待限流恢复',
  }
  return map[type] || '等待处理'
}

const waitMissingInfo = (event?: TraceEventItem | null) => {
  const missingInfo = event?.payload?.missing_info
  return Array.isArray(missingInfo) ? uniqueTexts(missingInfo).slice(0, 6) : []
}

const waitSummary = (event?: TraceEventItem | null) => {
  return String(event?.payload?.summary || event?.payload?.message || event?.payload?.reason_code || '')
}

const workerEventStatusType = (status?: string) => {
  if (status === 'failed') return 'danger'
  if (status === 'succeeded' || status === 'completed') return 'success'
  if (status === 'cancelled') return 'warning'
  return 'info'
}

const workerToolName = (event: Record<string, any>) => {
  return String(event.payload?.tool_name || event.payload?.tool || event.payload?.raw_event?.tool || 'tool')
}

const workerToolExecutor = (event: Record<string, any>) => {
  return String(event.payload?.executor_type || event.payload?.tool_kind || event.payload?.metadata?.executor_type || '')
}

const workerToolInputSummary = (event: Record<string, any>) => {
  return String(
    event.payload?.tool_input_preview ||
      toPreview(event.payload?.tool_input || event.payload?.raw_event?.tool_input || {}, 160),
  )
}

const workerToolOutputSummary = (event: Record<string, any>) => {
  return String(
    event.payload?.observation_preview ||
      event.message ||
      event.payload?.raw_event?.observation ||
      '',
  )
}

const workerToolWorkflowNodeLabel = (event: Record<string, any>) => {
  const nodes = event.payload?.workflow_nodes
  if (!Array.isArray(nodes) || nodes.length === 0) return ''
  const failed = nodes.find((node: Record<string, any>) => node.status === 'failed')
  return failed ? `${nodes.length} nodes · failed: ${failed.title || failed.node_type}` : `${nodes.length} nodes`
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

const runPlannerDryRun = async () => {
  const query = dryRunQuery.value.trim()
  if (!appId.value || !query) return
  dryRunLoading.value = true
  try {
    const res = await dryRunPlanner(appId.value, {
      query,
      image_urls: [],
      input_modalities: [],
    })
    dryRunResult.value = res.data
  } finally {
    dryRunLoading.value = false
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
    await loadMetrics()
  },
)

onMounted(async () => {
  await loadRecords(1)
  await loadDetail()
  await loadMetrics()
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
                  <div
                    v-if="recordDetail.status === 'waiting' || currentWaitEvent"
                    class="mt-3 border border-amber-200 bg-amber-50 p-3"
                  >
                    <div class="flex flex-wrap items-center gap-2">
                      <el-tag size="small" type="warning">{{ waitTypeLabel(currentWaitEvent) }}</el-tag>
                      <span v-if="currentWaitEvent?.step_id" class="text-xs text-amber-700">
                        Step {{ traceStepName(currentWaitEvent) || currentWaitEvent.step_id }}
                      </span>
                    </div>
                    <p v-if="waitSummary(currentWaitEvent)" class="mt-2 break-words text-xs text-amber-800">
                      {{ waitSummary(currentWaitEvent) }}
                    </p>
                    <div v-if="waitMissingInfo(currentWaitEvent).length" class="mt-2 flex flex-wrap gap-1">
                      <el-tag
                        v-for="item in waitMissingInfo(currentWaitEvent)"
                        :key="`wait-${item}`"
                        size="small"
                        type="warning"
                      >
                        {{ item }}
                      </el-tag>
                    </div>
                  </div>
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
                                <el-tag v-if="taskReplanCount(task)" size="small" type="warning">
                                  Replan {{ taskReplanCount(task) }}
                                </el-tag>
                                <el-tag v-if="taskPlanUpdateCount(task)" size="small" type="warning">
                                  Plan Update {{ taskPlanUpdateCount(task) }}
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

                              <div v-if="taskPreflight(task)" class="border border-slate-200 bg-white p-2">
                                <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                                  <div class="text-xs font-medium text-slate-700">Preflight</div>
                                  <el-tag
                                    size="small"
                                    :type="preflightStatusType(taskPreflight(task)?.status)"
                                  >
                                    {{ taskPreflight(task)?.status || 'skipped' }}
                                  </el-tag>
                                </div>
                                <div class="grid grid-cols-1 gap-2 md:grid-cols-2">
                                  <div
                                    v-for="result in taskPreflight(task)?.results || []"
                                    :key="`${task.id}-${result.step_id}-${result.worker_id}`"
                                    class="bg-slate-50 p-2"
                                  >
                                    <div class="flex flex-wrap items-center gap-2">
                                      <span class="truncate text-xs font-medium text-slate-900">
                                        {{ result.step_id }}
                                      </span>
                                      <el-tag
                                        size="small"
                                        :type="preflightStatusType(result.status, result.passed)"
                                      >
                                        {{ result.passed ? '通过' : '阻断' }}
                                      </el-tag>
                                    </div>
                                    <p
                                      v-if="firstFailedPreflightCheck(result)"
                                      class="mt-1 break-words text-xs text-red-600"
                                    >
                                      {{
                                        firstFailedPreflightCheck(result)?.user_message ||
                                        firstFailedPreflightCheck(result)?.error_code
                                      }}
                                    </p>
                                    <div class="mt-2 flex flex-wrap gap-1">
                                      <el-tag
                                        v-for="check in result.checks || []"
                                        :key="`${result.step_id}-${check.rule_id}-${check.error_code || 'ok'}`"
                                        size="small"
                                        :type="preflightStatusType('', check.passed)"
                                      >
                                        {{ check.rule_id }}
                                      </el-tag>
                                    </div>
                                  </div>
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
                                          <el-tag v-if="stepPlanAttempt(task, step) > 0" size="small" type="warning">
                                            Attempt {{ stepPlanAttempt(task, step) }}
                                          </el-tag>
                                        </div>
                                        <div class="mt-1 text-xs text-slate-500">
                                          {{ step.worker_agent?.name || '未知 Worker' }}
                                        </div>
                                        <p v-if="stepTaskText(step)" class="mt-1 line-clamp-2 break-words text-xs text-slate-600">
                                          {{ stepTaskText(step) }}
                                        </p>
                                        <div class="mt-1 flex flex-wrap gap-1">
                                          <el-tag v-if="step.worker_agent?.target_ref_type" size="small" type="info">
                                            {{ step.worker_agent.target_ref_type }}
                                          </el-tag>
                                          <el-tag
                                            v-if="step.input_json?.preflight?.capability_snapshot?.executor_type"
                                            size="small"
                                            type="info"
                                          >
                                            {{ step.input_json.preflight.capability_snapshot.executor_type }}
                                          </el-tag>
                                        </div>
                                        <p
                                          v-if="stepSelectionReason(step)"
                                          class="mt-2 line-clamp-2 break-words text-xs text-slate-500"
                                        >
                                          选择依据：{{ stepSelectionReason(step) }}
                                        </p>
                                        <div v-if="stepSelectionSignals(step).length" class="mt-1 flex flex-wrap gap-1">
                                          <el-tag
                                            v-for="signal in stepSelectionSignals(step)"
                                            :key="`${step.id}-${signal}`"
                                            size="small"
                                            type="info"
                                          >
                                            {{ signal }}
                                          </el-tag>
                                        </div>
                                      </div>
                                      <div class="flex shrink-0 flex-wrap items-center gap-2">
                                        <el-button size="small" @click="openJson('Step 输入', step.input_json)">输入</el-button>
                                        <el-button size="small" @click="openJson('Step 输出', step.output_json)">输出</el-button>
                                      </div>
                                    </div>

                                    <div v-if="hasStepContract(step)" class="mt-3 border border-slate-200 bg-slate-50 p-2">
                                      <div class="mb-2 text-xs font-medium text-slate-700">执行契约</div>
                                      <div class="grid grid-cols-1 gap-2 md:grid-cols-2">
                                        <div v-if="stepExpectedOutput(step)">
                                          <div class="mb-1 text-xs text-slate-500">预期输出</div>
                                          <p class="line-clamp-3 break-words text-xs text-slate-700">
                                            {{ stepExpectedOutput(step) }}
                                          </p>
                                        </div>
                                        <div v-if="stepHandoffContext(step)">
                                          <div class="mb-1 text-xs text-slate-500">交接上下文</div>
                                          <p class="line-clamp-3 break-words text-xs text-slate-700">
                                            {{ stepHandoffContext(step) }}
                                          </p>
                                        </div>
                                      </div>
                                      <div v-if="stepSuccessCriteria(step).length" class="mt-2">
                                        <div class="mb-1 text-xs text-slate-500">成功标准</div>
                                        <div class="flex flex-wrap gap-1">
                                          <el-tag
                                            v-for="criteria in stepSuccessCriteria(step)"
                                            :key="`${step.id}-criteria-${criteria}`"
                                            size="small"
                                            type="success"
                                          >
                                            {{ criteria }}
                                          </el-tag>
                                        </div>
                                      </div>
                                      <div v-if="stepRequiredArtifacts(step).length" class="mt-2">
                                        <div class="mb-1 text-xs text-slate-500">必需产物</div>
                                        <div class="flex flex-wrap gap-1">
                                          <el-tag
                                            v-for="artifact in stepRequiredArtifacts(step)"
                                            :key="`${step.id}-artifact-${artifact}`"
                                            size="small"
                                            type="info"
                                          >
                                            {{ artifact }}
                                          </el-tag>
                                        </div>
                                      </div>
                                    </div>

                                    <div class="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                                      <div class="bg-slate-50 p-2">
                                        <div class="mb-1 text-xs font-medium text-slate-700">Step 输入</div>
                                        <p class="line-clamp-3 break-words text-xs text-slate-500">
                                          {{ stepInputSummary(step) || '-' }}
                                        </p>
                                      </div>
                                      <div class="bg-slate-50 p-2">
                                        <div class="mb-1 text-xs font-medium text-slate-700">Step 输出</div>
                                        <p class="line-clamp-3 break-words text-xs text-slate-500">
                                          {{ stepOutputSummary(step) || '-' }}
                                        </p>
                                      </div>
                                    </div>

                                    <div v-if="stepPreflight(step)" class="mt-3 border border-slate-200 bg-slate-50 p-2">
                                      <div class="flex flex-wrap items-center justify-between gap-2">
                                        <div class="text-xs font-medium text-slate-700">Preflight</div>
                                        <el-tag
                                          size="small"
                                          :type="preflightStatusType(stepPreflight(step)?.status, stepPreflight(step)?.passed)"
                                        >
                                          {{ stepPreflight(step)?.passed === false ? '阻断' : '通过' }}
                                        </el-tag>
                                      </div>
                                      <p
                                        v-if="firstFailedPreflightCheck(stepPreflight(step))"
                                        class="mt-2 break-words text-xs text-red-600"
                                      >
                                        {{
                                          firstFailedPreflightCheck(stepPreflight(step))?.user_message ||
                                          firstFailedPreflightCheck(stepPreflight(step))?.error_code
                                        }}
                                      </p>
                                      <div class="mt-2 flex flex-wrap gap-1">
                                        <el-tag
                                          v-for="check in preflightChecks(stepPreflight(step))"
                                          :key="`${step.id}-${check.rule_id}-${check.error_code || 'ok'}`"
                                          size="small"
                                          :type="preflightStatusType('', check.passed)"
                                        >
                                          {{ check.rule_id }}
                                        </el-tag>
                                      </div>
                                    </div>

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
                                            <el-tag v-if="call.worker_agent?.target_ref_type" size="small" type="info">
                                              {{ call.worker_agent.target_ref_type }}
                                            </el-tag>
                                            <el-tag
                                              v-if="call.invocation_json?.execution_policy?.executor_type"
                                              size="small"
                                              type="info"
                                            >
                                              {{ call.invocation_json.execution_policy.executor_type }}
                                            </el-tag>
                                            <el-tag
                                              v-if="workerCallPlanAttempt(call) > 0"
                                              size="small"
                                              type="warning"
                                            >
                                              Attempt {{ workerCallPlanAttempt(call) }}
                                            </el-tag>
                                            <span class="text-xs text-slate-400">
                                              {{ formatSeconds(call.latency) }} · {{ call.token_count }} Token
                                            </span>
                                          </div>
                                          <div class="flex shrink-0 items-center gap-2">
                                            <el-button size="small" @click="openJson('WorkerInvocation', call.invocation_json)">Invocation</el-button>
                                            <el-button size="small" @click="openJson('WorkerResult', call.result_json)">Result</el-button>
                                          </div>
                                        </div>
                                        <div class="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                                          <div>
                                            <div class="mb-1 text-xs font-medium text-slate-600">Invocation</div>
                                            <p class="line-clamp-3 break-words text-xs text-slate-500">
                                              {{ workerInputSummary(call) || '-' }}
                                            </p>
                                          </div>
                                          <div>
                                            <div class="mb-1 text-xs font-medium text-slate-600">Result</div>
                                            <p class="line-clamp-3 break-words text-xs text-slate-500">
                                              {{ workerOutputSummary(call) || '-' }}
                                            </p>
                                          </div>
                                        </div>

                                        <div
                                          v-if="
                                            workerRuntime(call) ||
                                            workerInternalSteps(call).length ||
                                            workerToolEvents(call).length ||
                                            hasWorkerPlanFeedback(call)
                                          "
                                          class="mt-3 border-t border-slate-200 pt-2"
                                        >
                                          <div class="flex flex-wrap items-center justify-between gap-2">
                                            <div class="flex flex-wrap items-center gap-2">
                                              <span class="text-xs font-medium text-slate-700">Worker Runtime</span>
                                              <el-tag
                                                v-if="workerRuntimeFinalState(call)"
                                                size="small"
                                                :type="workerEventStatusType(workerRuntimeFinalState(call))"
                                              >
                                                {{ workerRuntimeFinalState(call) }}
                                              </el-tag>
                                              <span v-if="workerRuntimeLabel(call)" class="text-xs text-slate-400">
                                                {{ workerRuntimeLabel(call) }}
                                              </span>
                                              <el-tag
                                                v-if="workerRuntimePolicyLabel(call)"
                                                size="small"
                                                type="info"
                                              >
                                                {{ workerRuntimePolicyLabel(call) }}
                                              </el-tag>
                                              <el-tag
                                                v-if="workerReplanLabel(call)"
                                                size="small"
                                                type="warning"
                                              >
                                                replan: {{ workerReplanLabel(call) }}
                                              </el-tag>
                                              <el-tag
                                                v-if="workerPlanFeedback(call)?.completed_enough"
                                                size="small"
                                                type="success"
                                              >
                                                已足够完成
                                              </el-tag>
                                              <el-tag
                                                v-if="workerPlanFeedback(call)?.needs_plan_update"
                                                size="small"
                                                type="warning"
                                              >
                                                请求更新计划
                                              </el-tag>
                                              <el-tag
                                                v-if="workerPlanFeedbackReason(call) === 'waiting_user'"
                                                size="small"
                                                type="warning"
                                              >
                                                等待用户
                                              </el-tag>
                                              <el-tag
                                                v-else-if="workerPlanFeedbackReason(call)"
                                                size="small"
                                                type="info"
                                              >
                                                {{ workerPlanFeedbackReason(call) }}
                                              </el-tag>
                                            </div>
                                            <el-button
                                              v-if="workerRuntime(call) || workerPlanFeedback(call)"
                                              size="small"
                                              @click="openJson('Worker Runtime', call.result_json?.data || call.result_json)"
                                            >
                                              Runtime JSON
                                            </el-button>
                                          </div>

                                          <div v-if="workerPlanFeedbackMissingInfo(call).length" class="mt-2 flex flex-wrap gap-1">
                                            <el-tag
                                              v-for="item in workerPlanFeedbackMissingInfo(call)"
                                              :key="`${call.id}-missing-${item}`"
                                              size="small"
                                              type="warning"
                                            >
                                              缺 {{ item }}
                                            </el-tag>
                                          </div>
                                          <p
                                            v-if="workerPlanFeedbackArtifactCount(call)"
                                            class="mt-2 text-xs text-slate-500"
                                          >
                                            反馈产物 {{ workerPlanFeedbackArtifactCount(call) }} 个
                                          </p>

                                          <p
                                            v-if="workerMemoryCompaction(call)?.summary"
                                            class="mt-2 line-clamp-2 break-words text-xs text-slate-500"
                                          >
                                            Memory: {{ workerMemoryCompaction(call)?.summary }}
                                          </p>

                                          <div v-if="workerInternalSteps(call).length" class="mt-2 flex flex-wrap gap-1">
                                            <el-tag
                                              v-for="internalStep in workerInternalSteps(call)"
                                              :key="`${call.id}-${internalStep.internal_step_id || internalStep.tool_name}`"
                                              size="small"
                                              :type="workerEventStatusType(internalStep.status)"
                                            >
                                              {{ internalStep.tool_name || internalStep.goal || internalStep.internal_step_id }}
                                            </el-tag>
                                          </div>

                                          <div v-if="workerToolEvents(call).length" class="mt-2 space-y-1">
                                            <div
                                              v-for="event in workerToolEvents(call)"
                                              :key="`${call.id}-${event.event_type}-${event.payload?.tool_call_id || event.id}`"
                                              class="flex flex-wrap items-start justify-between gap-2 border border-slate-200 bg-white px-2 py-1"
                                            >
                                              <div class="min-w-0 flex-1">
                                                <div class="flex flex-wrap items-center gap-2">
                                                  <el-tag size="small" :type="workerEventStatusType(event.status)">
                                                    {{ event.event_type.replace('worker.tool.', '') }}
                                                  </el-tag>
                                                  <span class="truncate text-xs font-medium text-slate-800">
                                                    {{ workerToolName(event) }}
                                                  </span>
                                                  <el-tag v-if="workerToolExecutor(event)" size="small" type="info">
                                                    {{ workerToolExecutor(event) }}
                                                  </el-tag>
                                                  <span
                                                    v-if="workerToolWorkflowNodeLabel(event)"
                                                    class="text-xs text-slate-400"
                                                  >
                                                    {{ workerToolWorkflowNodeLabel(event) }}
                                                  </span>
                                                </div>
                                                <p
                                                  v-if="workerToolInputSummary(event)"
                                                  class="mt-1 line-clamp-1 break-words text-xs text-slate-500"
                                                >
                                                  输入：{{ workerToolInputSummary(event) }}
                                                </p>
                                                <p
                                                  v-if="workerToolOutputSummary(event)"
                                                  class="mt-1 line-clamp-2 break-words text-xs text-slate-500"
                                                >
                                                  结果：{{ workerToolOutputSummary(event) }}
                                                </p>
                                              </div>
                                              <el-button link type="primary" @click="openJson('Worker Tool Event', event)">
                                                JSON
                                              </el-button>
                                            </div>
                                          </div>
                                        </div>
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

              <el-tab-pane label="运行分析" name="metrics">
                <div v-loading="metricsLoading" class="space-y-4 pb-4">
                  <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
                    <div class="bg-slate-50 p-3">
                      <div class="text-xs text-slate-500">任务数</div>
                      <div class="mt-1 text-lg font-semibold text-slate-900">
                        {{ formatNumber(metricOverview.task_count) }}
                      </div>
                    </div>
                    <div class="bg-slate-50 p-3">
                      <div class="text-xs text-slate-500">成功率</div>
                      <div class="mt-1 text-lg font-semibold text-slate-900">
                        {{ formatPercent(metricOverview.success_rate) }}
                      </div>
                    </div>
                    <div class="bg-slate-50 p-3">
                      <div class="text-xs text-slate-500">等待数</div>
                      <div class="mt-1 text-lg font-semibold text-slate-900">
                        {{ formatNumber(metricOverview.waiting_count) }}
                      </div>
                    </div>
                    <div class="bg-slate-50 p-3">
                      <div class="text-xs text-slate-500">平均耗时</div>
                      <div class="mt-1 text-lg font-semibold text-slate-900">
                        {{ formatSeconds(metricOverview.avg_latency) }}
                      </div>
                    </div>
                    <div class="bg-slate-50 p-3">
                      <div class="text-xs text-slate-500">Token</div>
                      <div class="mt-1 text-lg font-semibold text-slate-900">
                        {{ formatNumber(metricOverview.total_token_count) }}
                      </div>
                    </div>
                    <div class="bg-slate-50 p-3">
                      <div class="text-xs text-slate-500">成本</div>
                      <div class="mt-1 text-lg font-semibold text-slate-900">
                        {{ formatCost(metricOverview.total_cost) }}
                      </div>
                    </div>
                  </div>

                  <div class="grid grid-cols-1 gap-3 xl:grid-cols-3">
                    <section class="border border-slate-200 p-3">
                      <div class="mb-3 text-sm font-medium text-slate-900">Planner</div>
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
                          <span class="font-medium">{{ metricPlanner.avg_plan_inflation_ratio || 0 }}</span>
                        </div>
                      </div>
                    </section>

                    <section class="border border-slate-200 p-3">
                      <div class="mb-3 text-sm font-medium text-slate-900">Worker</div>
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

                    <section class="border border-slate-200 p-3">
                      <div class="mb-3 text-sm font-medium text-slate-900">Trace</div>
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

                  <section class="border border-slate-200 p-3">
                    <div class="mb-3 text-sm font-medium text-slate-900">Worker 排行</div>
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

                  <div class="grid grid-cols-1 gap-3 xl:grid-cols-2">
                    <section class="border border-slate-200 p-3">
                      <div class="mb-3 text-sm font-medium text-slate-900">等待信息</div>
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
                      <el-empty v-else description="暂无等待字段" />
                    </section>

                    <section class="border border-slate-200 p-3">
                      <div class="mb-3 text-sm font-medium text-slate-900">错误排行</div>
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
              </el-tab-pane>

              <el-tab-pane label="执行日志" name="logs">
                <div class="pb-4">
                  <div class="mb-3 flex flex-wrap items-center gap-2">
                    <el-select v-model="logAgentFilter" class="w-[180px]" size="small">
                      <el-option label="全部 Agent" value="all" />
                      <el-option
                        v-for="agentName in logAgentOptions"
                        :key="agentName"
                        :label="agentName"
                        :value="agentName"
                      />
                    </el-select>
                    <el-select v-model="logTypeFilter" class="w-[150px]" size="small">
                      <el-option label="全部事件" value="all" />
                      <el-option label="Planner" value="planner" />
                      <el-option label="Replan" value="replan" />
                      <el-option label="Plan Update" value="plan_update" />
                      <el-option label="Worker" value="worker" />
                      <el-option label="Router" value="router" />
                      <el-option label="Preflight" value="preflight" />
                      <el-option label="Wait" value="wait" />
                      <el-option label="失败" value="failed" />
                    </el-select>
                    <el-input
                      v-model="logSearchWord"
                      clearable
                      size="small"
                      class="min-w-[180px] flex-1"
                      placeholder="搜索事件、Agent、Step 或选择理由"
                    />
                    <el-switch
                      v-model="showLogPayload"
                      size="small"
                      active-text="Payload"
                      inactive-text="摘要"
                    />
                  </div>

                  <el-table :data="filteredTraceEvents" stripe>
                    <el-table-column label="时间" width="170">
                      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
                    </el-table-column>
                    <el-table-column label="事件" min-width="220">
                      <template #default="{ row }">
                        <div class="font-medium text-slate-900">{{ row.event_type }}</div>
                        <div v-if="traceMessage(row)" class="truncate text-xs text-slate-500">{{ traceMessage(row) }}</div>
                      </template>
                    </el-table-column>
                    <el-table-column label="Agent" min-width="150">
                      <template #default="{ row }">
                        <div class="truncate text-sm text-slate-700">{{ traceAgentName(row) || '-' }}</div>
                      </template>
                    </el-table-column>
                    <el-table-column label="Step / 任务" min-width="260">
                      <template #default="{ row }">
                        <div class="font-medium text-slate-800">{{ traceStepName(row) || '-' }}</div>
                        <div v-if="traceTaskText(row)" class="line-clamp-2 break-words text-xs text-slate-500">
                          {{ traceTaskText(row) }}
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="选择依据" min-width="260">
                      <template #default="{ row }">
                        <div class="line-clamp-2 break-words text-sm text-slate-700">
                          {{ traceSelectionReason(row) || '-' }}
                        </div>
                        <div v-if="traceSelectionSignals(row).length" class="mt-1 flex flex-wrap gap-1">
                          <el-tag
                            v-for="signal in traceSelectionSignals(row)"
                            :key="`${row.id}-${signal}`"
                            size="small"
                            type="info"
                          >
                            {{ signal }}
                          </el-tag>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="showLogPayload" label="Payload 摘要" min-width="220">
                      <template #default="{ row }">
                        <div class="line-clamp-2 break-words text-xs text-slate-500">
                          {{ tracePayloadSummary(row) }}
                        </div>
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
                  <el-empty
                    v-if="!filteredTraceEvents.length"
                    class="py-10"
                    description="没有匹配的执行事件"
                  />
                </div>
              </el-tab-pane>

              <el-tab-pane label="调度回放" name="playback">
                <div class="space-y-3 pb-4">
                  <section class="border border-slate-200 p-3">
                    <div class="flex flex-wrap items-center justify-between gap-2">
                      <div class="min-w-0">
                        <div class="text-sm font-medium text-slate-900">重新规划，不执行</div>
                        <p class="mt-1 text-xs text-slate-500">
                          只调用 Planner 生成计划和能力预检，不创建任务，不调用 Worker。
                        </p>
                      </div>
                      <div class="flex min-w-[280px] flex-1 flex-wrap items-center gap-2 md:flex-nowrap">
                        <el-input
                          v-model="dryRunQuery"
                          size="small"
                          class="min-w-[220px] flex-1"
                          placeholder="输入要重新规划的问题"
                          @keyup.enter="runPlannerDryRun"
                        />
                        <el-button size="small" type="primary" :loading="dryRunLoading" @click="runPlannerDryRun">
                          Dry-run
                        </el-button>
                      </div>
                    </div>

                    <div v-if="dryRunResult" class="mt-3 border-t border-slate-100 pt-3">
                      <div class="mb-2 flex flex-wrap items-center gap-2">
                        <el-tag size="small" :type="dryRunResult.status === 'ready' ? 'success' : 'danger'">
                          {{ dryRunResult.status }}
                        </el-tag>
                        <el-tag v-if="dryRunResult.source" size="small" type="info">
                          {{ planSourceLabel(dryRunResult.source) || dryRunResult.source }}
                        </el-tag>
                        <span class="text-xs text-slate-400">{{ dryRunResult.latency_ms || 0 }} ms</span>
                        <el-button size="small" @click="openJson('Planner Dry-run', dryRunResult)">JSON</el-button>
                      </div>
                      <p v-if="dryRunResult.fallback_reason" class="mb-2 break-words text-xs text-red-600">
                        {{ dryRunResult.fallback_reason }}
                      </p>
                      <div class="grid grid-cols-1 gap-2 lg:grid-cols-2">
                        <div
                          v-for="step in dryRunResult.planned_steps || []"
                          :key="`${dryRunResult.query}-${step.step_id}`"
                          class="bg-slate-50 p-2"
                        >
                          <div class="flex flex-wrap items-center gap-2">
                            <span class="text-xs font-medium text-slate-900">{{ step.step_id }}</span>
                            <span class="text-xs text-slate-500">{{ step.worker_name || step.worker_id }}</span>
                          </div>
                          <p class="mt-1 line-clamp-2 break-words text-xs text-slate-600">{{ step.task }}</p>
                          <p v-if="step.selection_reason" class="mt-1 line-clamp-2 break-words text-xs text-slate-500">
                            {{ step.selection_reason }}
                          </p>
                        </div>
                      </div>
                    </div>
                  </section>

                  <el-empty v-if="!playbackEvents.length" description="暂无 Planner 调度事件" />
                  <el-timeline v-else>
                    <el-timeline-item
                      v-for="event in playbackEvents"
                      :key="event.id"
                      :timestamp="formatDate(event.created_at)"
                      placement="top"
                    >
                      <div class="border border-slate-200 p-3">
                        <div class="flex flex-wrap items-start justify-between gap-2">
                          <div class="min-w-0">
                            <div class="flex flex-wrap items-center gap-2">
                              <span class="font-medium text-slate-900">{{ event.event_type }}</span>
                              <el-tag size="small" :type="playbackStatusType(event)">
                                {{ event.payload?.status || event.payload?.source || 'trace' }}
                              </el-tag>
                              <span class="text-xs text-slate-400">{{ traceAgentName(event) || 'Planner' }}</span>
                            </div>
                            <p v-if="traceSelectionReason(event)" class="mt-1 line-clamp-2 break-words text-xs text-slate-500">
                              {{ traceSelectionReason(event) }}
                            </p>
                            <p
                              v-if="event.payload?.feedback?.reason_code"
                              class="mt-1 line-clamp-2 break-words text-xs text-amber-700"
                            >
                              Feedback: {{ event.payload.feedback.reason_code }}
                            </p>
                          </div>
                          <div class="flex shrink-0 flex-wrap items-center gap-2">
                            <el-button size="small" @click="openJson('调度事件', event)">事件 JSON</el-button>
                            <el-button
                              v-if="event.payload?.plan_snapshot"
                              size="small"
                              @click="openJson('计划快照', event.payload.plan_snapshot)"
                            >
                              计划
                            </el-button>
                            <el-button
                              v-if="event.payload?.previous_plan"
                              size="small"
                              @click="openJson('Previous Plan', event.payload.previous_plan)"
                            >
                              旧计划
                            </el-button>
                            <el-button
                              v-if="event.payload?.new_plan"
                              size="small"
                              @click="openJson('New Plan', event.payload.new_plan)"
                            >
                              新计划
                            </el-button>
                            <el-button
                              v-if="playbackDiff(event)"
                              size="small"
                              @click="openJson('Plan Diff', playbackDiff(event))"
                            >
                              Diff
                            </el-button>
                            <el-button
                              v-if="event.payload?.feedback"
                              size="small"
                              @click="openJson('Plan Feedback', event.payload.feedback)"
                            >
                              Feedback
                            </el-button>
                          </div>
                        </div>

                        <div v-if="playbackSteps(event).length" class="mt-3 grid grid-cols-1 gap-2 lg:grid-cols-2">
                          <div
                            v-for="step in playbackSteps(event)"
                            :key="`${event.id}-${step.step_id}-${step.worker_id}`"
                            class="bg-slate-50 p-2"
                          >
                            <div class="flex flex-wrap items-center gap-2">
                              <span class="text-xs font-medium text-slate-900">{{ step.step_id }}</span>
                              <span class="truncate text-xs text-slate-500">{{ step.worker_name || step.worker_id }}</span>
                            </div>
                            <p class="mt-1 line-clamp-2 break-words text-xs text-slate-600">{{ step.task }}</p>
                            <p v-if="step.selection_reason" class="mt-1 line-clamp-2 break-words text-xs text-slate-500">
                              {{ step.selection_reason }}
                            </p>
                          </div>
                        </div>

                        <div v-if="playbackDiff(event)" class="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                          <el-tag size="small" type="success">
                            新增 {{ playbackDiff(event)?.summary?.added || 0 }}
                          </el-tag>
                          <el-tag size="small" type="danger">
                            移除 {{ playbackDiff(event)?.summary?.removed || 0 }}
                          </el-tag>
                          <el-tag size="small" type="warning">
                            变更 {{ playbackDiff(event)?.summary?.changed || 0 }}
                          </el-tag>
                        </div>
                      </div>
                    </el-timeline-item>
                  </el-timeline>
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
