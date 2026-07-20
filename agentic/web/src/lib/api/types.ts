import type { RunSkill, SkillRef } from '@/types/skill'

export type ApiResponse<T = unknown> = {
  code: number
  msg: string
  data: T | null
}

export type UserInfo = {
  id: string
  email: string
  name: string
  avatar: string
  status: string
  last_login_at?: string | null
  created_at?: string
}

export type AuthData = {
  access_token: string
  token_type: 'bearer'
  user: UserInfo
}

export type LoginParams = {
  email: string
  password: string
}

export type RegisterParams = {
  email: string
  password: string
  name?: string
  avatar?: string
}

export type SessionStatus = 'pending' | 'running' | 'waiting' | 'completed'
export type ExecutionStatus = 'pending' | 'running' | 'completed' | 'failed'
export type ToolEventStatus = 'calling' | 'called'
export type MCPTransport = 'stdio' | 'sse' | 'streamable_http'
export type ToolRiskLevel = 'low' | 'medium' | 'high'
export type ToolApprovalPolicy = 'auto' | 'allow' | 'ask' | 'deny'
export type ToolExecutorType = 'builtin' | 'mcp' | 'a2a' | 'api'
export type ToolSourceType = 'builtin' | 'mcp' | 'a2a' | 'api'

export type ToolFunctionResult = {
  success?: boolean
  message?: string | null
  data?: unknown
  [key: string]: unknown
}

export type LLMConfig = {
  base_url?: string
  api_key?: string
  model_name?: string
  temperature?: number
  max_tokens?: number
  [key: string]: unknown
}

export type AgentConfig = {
  max_iterations?: number
  max_retries?: number
  max_search_results?: number
  [key: string]: unknown
}

export type ListMCPServerItem = {
  server_name: string
  enabled: boolean
  transport: MCPTransport
  tools: string[]
}

export type MCPServersData = {
  mcp_servers: ListMCPServerItem[]
}

export type MCPServerConfig = {
  transport?: MCPTransport
  enabled?: boolean
  description?: string | null
  env?: Record<string, unknown> | null
  command?: string | null
  args?: string[] | null
  url?: string | null
  headers?: Record<string, unknown> | null
  [key: string]: unknown
}

export type MCPConfig = {
  mcpServers: Record<string, MCPServerConfig>
  [key: string]: unknown
}

export type ListA2AServerItem = {
  id: string
  name: string
  description: string
  input_modes: string[]
  output_modes: string[]
  streaming: boolean
  push_notifications: boolean
  enabled: boolean
}

export type A2AServersData = {
  a2a_servers: ListA2AServerItem[]
}

export type CreateA2AServerParams = {
  base_url: string
}

export type ToolBinding = {
  enabled: boolean
  risk_level: ToolRiskLevel
  approval?: ToolApprovalPolicy
  params?: Record<string, unknown>
}

export type RuntimeToolPolicy = {
  allowed_executor_types: ToolExecutorType[]
  max_tool_iterations: number
  require_approval_for_high_risk: boolean
}

export type ToolDescriptor = {
  tool_id: string
  function_name: string
  provider_id: string
  provider_label: string
  group: string
  executor_type: ToolExecutorType
  label: string
  description: string
  schema: Record<string, unknown>
  category: string
  risk_level: ToolRiskLevel
  requires_sandbox: boolean
  requires_browser: boolean
  requires_credentials: boolean
  enabled_by_default: boolean
  enabled: boolean
}

export type ToolApprovalSetting = {
  tool_id: string
  function_name: string
  label: string
  risk_level: ToolRiskLevel
  approval: ToolApprovalPolicy
}

export type ToolRegistration = {
  registration_id: string
  provider_id: string
  provider_label: string
  source_type: ToolSourceType
  executor_type: ToolExecutorType
  group: string
  category: string
  description: string
  enabled: boolean
  builtin: boolean
  editable: boolean
  requires_sandbox: boolean
  requires_browser: boolean
  requires_credentials: boolean
  config: Record<string, unknown>
}

export type ToolListData = {
  tools: ToolDescriptor[]
  registrations: ToolRegistration[]
  approval_tools: ToolApprovalSetting[]
  runtime_policy: RuntimeToolPolicy
}

export type UpdateToolBindingsParams = {
  bindings: Record<string, ToolBinding>
  runtime_policy: RuntimeToolPolicy
}

export type ToolRegistrationListData = {
  registrations: ToolRegistration[]
}

export type ToolRegistrationTestParams = {
  function_name?: string | null
  arguments?: Record<string, unknown>
}

export type ToolRegistrationTestData = {
  registration: ToolRegistration
  tools: ToolDescriptor[]
  selected_tool?: ToolDescriptor | null
  result?: ToolFunctionResult | null
}

export type CreateToolRegistrationParams = {
  provider_id: string
  provider_label: string
  source_type: ToolSourceType
  executor_type: ToolExecutorType
  group: string
  category: string
  description?: string
  enabled?: boolean
  requires_sandbox?: boolean
  requires_browser?: boolean
  requires_credentials?: boolean
  config?: Record<string, unknown>
}

export type UpdateToolRegistrationParams = Partial<Omit<CreateToolRegistrationParams, 'provider_id'>>

export type ToolCapabilitySummary = {
  schema_version: string
  executor_types: ToolExecutorType[]
  input_modalities: string[]
  output_modalities: string[]
  semantic_tags: string[]
  tool_names: string[]
  constraints: Record<string, unknown>
  generated_at: number
}

export type ToolPreflightCheck = {
  rule_id: string
  passed: boolean
  error_code?: string | null
  user_message: string
}

export type ToolPreflightResponse = {
  status: 'pass' | 'warning' | 'blocked'
  checks: ToolPreflightCheck[]
  capability_snapshot: ToolCapabilitySummary
}

export type ToolPreflightParams = {
  message: string
  input_modalities?: string[]
}

export type RunStatus = 'pending' | 'running' | 'waiting' | 'completed' | 'failed'
export type RunTraceStatus =
  | 'started'
  | 'running'
  | 'completed'
  | 'failed'
  | 'calling'
  | 'called'
  | 'blocked'
  | 'succeeded'

export type AgentRun = {
  id: string
  trace_id: string
  user_id: string
  session_id: string
  task_id?: string | null
  input_event_id?: string | null
  status: RunStatus
  input_summary: string
  final_summary: string
  error?: string | null
  tool_config_snapshot: Record<string, unknown>
  agent_config_snapshot: Record<string, unknown>
  llm_config_snapshot: Record<string, unknown>
  started_at?: string | null
  finished_at?: string | null
  updated_at?: string
  created_at: string
  [key: string]: unknown
}

export type RunStepRecord = {
  id: string
  run_id: string
  session_id: string
  event_id?: string | null
  step_id: string
  step_index?: number | null
  title?: string
  description: string
  status: RunTraceStatus
  success?: boolean | null
  result_summary: string
  error?: string | null
  attachments: unknown[]
  started_at?: string | null
  finished_at?: string | null
  updated_at?: string
  created_at: string
  [key: string]: unknown
}

export type ToolCallRecord = {
  id: string
  run_id: string
  run_step_id?: string | null
  step_id?: string | null
  session_id: string
  event_id?: string | null
  tool_call_id: string
  tool_id: string
  tool_name: string
  function_name: string
  provider_id?: string | null
  registration_id?: string | null
  source_type?: ToolSourceType | null
  executor_type?: ToolExecutorType | null
  risk_level?: ToolRiskLevel | null
  enabled_effective?: boolean | null
  requires_sandbox: boolean
  requires_browser: boolean
  requires_credentials: boolean
  status: RunTraceStatus
  arguments: Record<string, unknown>
  arguments_preview: string
  arguments_hash: string
  result: Record<string, unknown>
  result_preview: string
  success?: boolean | null
  error?: string | null
  latency_ms?: number | null
  started_at?: string | null
  finished_at?: string | null
  updated_at?: string
  created_at: string
  [key: string]: unknown
}

export type ModelCallRecord = {
  id: string
  run_id: string
  run_step_id?: string | null
  step_id?: string | null
  session_id: string
  agent_name: string
  provider: string
  base_url: string
  model_name: string
  temperature?: number | null
  max_tokens?: number | null
  tool_schema_count: number
  message_count: number
  tool_choice?: string | null
  response_format: Record<string, unknown>
  status: RunTraceStatus
  finish_reason?: string | null
  prompt_tokens?: number | null
  completion_tokens?: number | null
  total_tokens?: number | null
  latency_ms?: number | null
  request_preview: Record<string, unknown>
  response_preview: Record<string, unknown>
  error?: string | null
  started_at?: string | null
  finished_at?: string | null
  updated_at?: string
  created_at: string
  [key: string]: unknown
}

export type TraceEventRecord = {
  id: string
  trace_id: string
  run_id: string
  session_id: string
  event_id?: string | null
  event_type: string
  source: string
  payload: Record<string, unknown>
  created_at: string
  [key: string]: unknown
}

export type RunListData = {
  runs: AgentRun[]
}

export type RunDetailData = {
  run: AgentRun
  steps: RunStepRecord[]
  tool_calls: ToolCallRecord[]
  model_calls: ModelCallRecord[]
  events: TraceEventRecord[]
  skills: RunSkill[]
}

export type {
  PublishedSkill,
  RunSkill,
  SkillDetail,
  SkillDraft,
  SkillDraftFile,
  SkillDraftTree,
  SkillDraftTreeEntry,
  SkillManifest,
  SkillRef,
  SkillSelectionMode,
  SkillSource,
  SkillSummary,
  SkillValidationDiagnostic,
  SkillValidationResult,
  SkillVersion,
} from '@/types/skill'

export type RunEventsData = {
  events: TraceEventRecord[]
}

export type RunToolCallsData = {
  tool_calls: ToolCallRecord[]
}

export type RunModelCallsData = {
  model_calls: ModelCallRecord[]
}

export type FileInfo = {
  id: string
  filename: string
  filepath: string
  key: string
  extension: string
  content_type: string
  size: number
  parent_id?: string | null
  type?: 'file' | 'folder'
  name?: string
  mime_type?: string
  storage_provider?: 'local' | 'qcloud_cos' | 'aliyun_oss'
  source_type?: 'user_upload' | 'agent_generated'
  status?: 'available' | 'deleted'
  sha256?: string
  origin_session_id?: string | null
  origin_run_id?: string | null
  preview_url?: string
  download_url?: string
  created_at?: number
  updated_at?: number
  [key: string]: unknown
}

export type FileUploadParams = {
  file: File
  session_id?: string
  parent_id?: string | null
}

export type ManagedFile = Required<Pick<FileInfo, 'id' | 'filename' | 'size'>> & {
  parent_id: string | null
  type: 'file' | 'folder'
  name: string
  extension: string
  mime_type: string
  storage_provider: 'local' | 'qcloud_cos' | 'aliyun_oss'
  source_type: 'user_upload' | 'agent_generated'
  status: 'available' | 'deleted'
  preview_url: string
  download_url: string
  created_at: number
  updated_at: number
}

export type FilePaginator = {
  current_page: number
  page_size: number
  total_page: number
  total_record: number
}

export type ManagedFilesData = { list: ManagedFile[]; paginator: FilePaginator }
export type FolderTreeItem = { id: string; parent_id: string | null; name: string; depth: number }

export type SearchContentType = 'session' | 'message' | 'tool' | 'trace' | 'file'
export type SearchResultItem = {
  id: string
  content_type: SearchContentType
  session_id?: string | null
  run_id?: string | null
  event_id?: string | null
  title: string
  snippet: string
  created_at?: string | null
  metadata: Record<string, unknown>
}
export type SearchResults = {
  items: SearchResultItem[]
  query: string
  current_page: number
  page_size: number
  total_page: number
  total_record: number
}

export type StorageProvider = 'local' | 'qcloud_cos' | 'aliyun_oss'
export type StorageConfig = {
  default_provider: StorageProvider
  providers: {
    local: { enabled: boolean }
    qcloud_cos: { enabled: boolean; bucket: string; region: string; domain: string; scheme: 'http' | 'https'; secret_id: string; secret_key: string }
    aliyun_oss: { enabled: boolean; bucket: string; endpoint: string; region: string; domain: string; path_prefix: string; access_key_id: string; access_key_secret: string }
  }
}

export type Session = {
  session_id: string
  title: string
  latest_message: string
  latest_message_at: string
  status: SessionStatus
  unread_message_count: number
  [key: string]: unknown
}

export type SessionsData = {
  sessions: Session[]
}

export type CreateSessionParams = {
  title?: string
  [key: string]: unknown
}

export type ChatMessage = {
  role: 'user' | 'assistant' | 'system'
  message: string
  visible?: boolean
  attachments?: Array<{
    file_id: string
    filename: string
    size?: number
    [key: string]: unknown
  }>
  skills?: SkillRef[]
  [key: string]: unknown
}

export type ChatParams = {
  message?: string
  attachments?: string[]
  skills?: SkillRef[]
  event_id?: string
  [key: string]: unknown
}

export type ResumeMode = 'continue' | 'restart'

export type ResumeSessionParams = {
  mode: ResumeMode
}

export type ResolveInteractionParams = {
  decision: InteractionDecision
  answer?: string
  selected_values?: string[]
}

export type SessionDetail = Session & {
  events?: SSEEventData[]
}

export type PlanStep = {
  id: string
  description: string
  status: ExecutionStatus
  error?: string | null
  [key: string]: unknown
}

export type PlanEvent = {
  steps: PlanStep[]
  [key: string]: unknown
}

export type StepEvent = {
  id: string
  status: ExecutionStatus
  description: string
  error?: string | null
  [key: string]: unknown
}

export type ToolEvent = {
  name: string
  function: string
  args: Record<string, unknown>
  content?: unknown
  status?: ToolEventStatus
  function_result?: ToolFunctionResult | null
  [key: string]: unknown
}

export type InteractionType = 'ask_user' | 'tool_approval'
export type InteractionStatus = 'pending' | 'resolved'
export type InteractionDecision = 'answer' | 'approve' | 'reject'

export type InteractionOption = {
  value: string
  label: string
  description?: string | null
}

export type InteractionEvent = {
  action_id: string
  interaction_type: InteractionType
  status: InteractionStatus
  tool_call_id: string
  tool_name: string
  function_name: string
  function_args: Record<string, unknown>
  prompt: string
  description?: string | null
  options: InteractionOption[]
  allow_multiple: boolean
  allow_text: boolean
  placeholder?: string | null
  risk_level?: ToolRiskLevel | null
  decision?: InteractionDecision | null
  answer?: string | null
  selected_values: string[]
  [key: string]: unknown
}

export type SSEEventType =
  | 'message'
  | 'title'
  | 'plan'
  | 'step'
  | 'tool'
  | 'interaction'
  | 'wait'
  | 'done'
  | 'error'

export type SSEEventData =
  | { type: 'message'; data: ChatMessage }
  | { type: 'title'; data: { title: string; [key: string]: unknown } }
  | { type: 'plan'; data: PlanEvent }
  | { type: 'step'; data: StepEvent }
  | { type: 'tool'; data: ToolEvent }
  | { type: 'interaction'; data: InteractionEvent }
  | { type: 'wait'; data: Record<string, unknown> }
  | { type: 'done'; data: Record<string, unknown> }
  | { type: 'error'; data: { error: string; [key: string]: unknown } }

export type SSEEventHandler = (event: SSEEventData) => void

export type SessionFile = {
  id: string
  filename: string
  filepath: string
  key: string
  extension: string
  content_type: string
  size: number
  [key: string]: unknown
}

export type ViewFileParams = {
  filepath: string
  [key: string]: unknown
}

export type ViewShellParams = {
  shell_session_id: string
  [key: string]: unknown
}
