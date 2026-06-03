import type { BaseResponse } from '@/models/base'

export type AgentTaskStatus =
  | 'created'
  | 'running'
  | 'waiting_approval'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

export type AgentRef = {
  id: string
  name: string
  icon: string
  description: string
  runtime_type: string
  product_category: string
  status: string
  target_ref_type: string
  target_ref_id: string
} | null

export type AgentTaskSummary = {
  id: string
  record_type?: string
  conversation_id?: string
  name?: string
  run_type: string
  entry_agent: AgentRef
  status: AgentTaskStatus | string
  user_input: Record<string, any>
  user_input_preview: string
  final_result: Record<string, any>
  summary: string
  error_code: string
  error_message: string
  version: number
  step_count: number
  succeeded_step_count: number
  failed_step_count: number
  worker_call_count: number
  artifact_count: number
  trace_count: number
  message_count?: number
  task_count?: number
  total_token_count?: number
  total_price?: number
  latency?: number
  started_at: number
  finished_at: number
  created_at: number
  updated_at: number
}

export type AgentPlanItem = {
  id: string
  schema_version: string
  plan_json: Record<string, any>
  risk_level: string
  status: string
  created_at: number
  updated_at: number
}

export type AgentStepItem = {
  id: string
  plan_id: string
  step_key: string
  worker_agent: AgentRef
  dependencies: string[]
  execution_mode: string
  status: AgentTaskStatus | string
  input_json: Record<string, any>
  output_json: Record<string, any>
  retry_count: number
  timeout_seconds: number
  started_at: number
  finished_at: number
  created_at: number
  updated_at: number
}

export type WorkerCallItem = {
  id: string
  step_id: string
  worker_agent: AgentRef
  invocation_json: Record<string, any>
  result_json: Record<string, any>
  status: AgentTaskStatus | string
  token_count: number
  cost: number
  latency: number
  created_at: number
  updated_at: number
}

export type CapabilityCallItem = {
  id: string
  step_id: string
  worker_call_id: string | null
  capability_id: string
  input_json: Record<string, any>
  output_json: Record<string, any>
  status: AgentTaskStatus | string
  risk_level: string
  approval_id: string | null
  idempotency_key: string
  latency: number
  created_at: number
  updated_at: number
}

export type TraceEventItem = {
  id: string
  trace_id: string
  task_id: string
  plan_id: string | null
  step_id: string | null
  worker_call_id: string | null
  capability_call_id: string | null
  approval_id: string | null
  event_type: string
  payload: Record<string, any>
  token_count: number
  cost: number
  latency: number
  created_at: number
  updated_at: number
}

export type AgentFileRef = {
  id?: string
  file_id?: string
  name?: string
  mime_type?: string
  extension?: string
  size?: number
  source?: string
  summary?: string
  download_url?: string
  preview_url?: string
  metadata?: Record<string, any>
  content?: string
  content_truncated?: boolean
}

export type AgentArtifactRef = AgentFileRef & {
  artifact_id?: string
  type?: string
  task_id?: string
  step_id?: string
  worker_id?: string
}

export type AgentConversationUserOption = {
  id: string
  label: string
  type: string
}

export type AgentTaskDetail = AgentTaskSummary & {
  messages?: AgentConversationMessage[]
  agent_tasks?: AgentTaskSummary[]
  plans: AgentPlanItem[]
  plan: AgentPlanItem | null
  steps: AgentStepItem[]
  worker_calls: WorkerCallItem[]
  capability_calls: CapabilityCallItem[]
  trace_events: TraceEventItem[]
  input_files: AgentFileRef[]
  artifacts: AgentArtifactRef[]
}

export type AgentConversationMessage = {
  id: string
  conversation_id: string
  invoke_from: string
  status: AgentTaskStatus | string
  query: string
  image_urls: string[]
  answer: string
  error: string
  message: Record<string, any>[]
  total_token_count: number
  total_price: number
  latency: number
  created_at: number
  updated_at: number
  trace_events: TraceEventItem[]
}

export type GetAgentTasksWithPageRequest = {
  current_page: number
  page_size: number
  status?: string
  user_id?: string
  search_word?: string
}

export type GetAgentTasksWithPageResponse = BaseResponse<{
  list: AgentTaskSummary[]
  users: AgentConversationUserOption[]
  total_page: number
  total_record: number
  current_page: number
  page_size: number
}>

export type GetAgentTaskDetailResponse = BaseResponse<AgentTaskDetail>
