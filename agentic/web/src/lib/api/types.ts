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
  params?: Record<string, unknown>
}

export type RuntimeToolPolicy = {
  allowed_executor_types: ToolExecutorType[]
  max_tool_iterations: number
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

export type FileInfo = {
  id: string
  filename: string
  filepath: string
  key: string
  extension: string
  content_type: string
  size: number
  [key: string]: unknown
}

export type FileUploadParams = {
  file: File
  session_id?: string
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
  attachments?: Array<{
    file_id: string
    filename: string
    size?: number
    [key: string]: unknown
  }>
  [key: string]: unknown
}

export type ChatParams = {
  message?: string
  attachments?: string[]
  event_id?: string
  [key: string]: unknown
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

export type SSEEventType =
  | 'message'
  | 'title'
  | 'plan'
  | 'step'
  | 'tool'
  | 'wait'
  | 'done'
  | 'error'

export type SSEEventData =
  | { type: 'message'; data: ChatMessage }
  | { type: 'title'; data: { title: string; [key: string]: unknown } }
  | { type: 'plan'; data: PlanEvent }
  | { type: 'step'; data: StepEvent }
  | { type: 'tool'; data: ToolEvent }
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
