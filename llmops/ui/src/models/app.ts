import { type BasePaginatorRequest, type BasePaginatorResponse, type BaseResponse } from '@/models/base' // 获取应用信息响应结构

export type AgentType = 'worker' | 'planner'

// 获取应用信息响应结构
export type GetAppResponse = BaseResponse<{
  id: string
  debug_conversation_id: string
  name: string
  icon: string
  description: string
  agent_type: AgentType
  status: string
  draft_updated_at: number
  updated_at: number
  created_at: number
}>

// 新增应用请求结构
export type CreateAppRequest = { name: string; icon: string; description: string; agent_type: AgentType }

// 更新应用请求结构
export type UpdateAppRequest = { name: string; icon: string; description: string }

// 获取应用分页列表数据请求
export type GetAppsWithPageRequest = BasePaginatorRequest & { search_word: string; agent_type?: AgentType | '' }

// 获取应用分页列表数据响应
export type GetAppsWithPageResponse = BasePaginatorResponse<{
  id: string
  name: string
  icon: string
  description: string
  agent_type: AgentType
  preset_prompt: string
  model_config: {
    provider: string
    model: string
  }
  status: string
  updated_at: number
  created_at: number
}>

// 获取特定应用的草稿配置响应结构
export type GetDraftAppConfigResponse = BaseResponse<{
  id: string
  model_config: { provider: string; model: string; parameters: Record<string, any> }
  dialog_round: number
  preset_prompt: string
  tools: {
    type: string
    provider: { id: string; name: string; label: string; icon: string; description: string }
    tool: {
      id: string
      name: string
      label: string
      description: string
      params: Record<string, any>
    }
  }[]
  workflows: { id: string; name: string; icon: string; description: string }[]
  datasets: { id: string; name: string; icon: string; description: string }[]
  retrieval_config: { retrieval_strategy: string; k: number; score: number }
  long_term_memory: { enable: boolean }
  opening_statement: string
  opening_questions: string[]
  speech_to_text: { enable: boolean }
  text_to_speech: { enable: boolean; voice: string; auto_play: boolean }
  suggested_after_answer: { enable: boolean }
  review_config: {
    enable: boolean
    keywords: string[]
    inputs_config: { enable: boolean; preset_response: string }
    outputs_config: { enable: boolean }
  }
  updated_at: number
  created_at: number
}>

// 更新特定应用的草稿配置请求结构
export type UpdateDraftAppConfigRequest = {
  model_config?: { provider: string; model: string; parameters: Record<string, any> }
  dialog_round?: number
  preset_prompt?: string
  tools?: { type: string; provider_id: string; tool_id: string; params: Record<string, any> }[]
  workflows?: string[]
  datasets?: string[]
  retrieval_config?: { retrieval_strategy: string; k: number; score: number }
  long_term_memory?: { enable: boolean }
  opening_statement?: string
  opening_questions?: string[]
  speech_to_text?: { enable: boolean }
  text_to_speech?: { enable: boolean; voice: string; auto_play: boolean }
  suggested_after_answer?: { enable: boolean }
  review_config?: {
    enable: boolean
    keywords: string[]
    inputs_config: { enable: boolean; preset_response: string }
    outputs_config: { enable: boolean }
  }
}

// 获取应用的调试会话消息列表响应结构
export type GetDebugConversationMessagesWithPageResponse = BasePaginatorResponse<{
  id: string
  conversation_id: string
  query: string
  image_urls: string[]
  answer: string
  total_token_count: number
  latency: number
  agent_thoughts: {
    id: string
    position: number
    event: string
    thought: string
    observation: string
    tool: string
    tool_input: Record<string, any>
    latency: number
    created_at: number
  }[]
  created_at: number
}>

// 获取应用的发布历史配置列表分页响应结构
export type GetPublishHistoriesWithPageResponse = BasePaginatorResponse<{
  id: string
  version: number
  created_at: number
}>

// 获取应用的调试会话消息列表请求结构
export type GetDebugConversationMessagesWithPageRequest = BasePaginatorRequest & {
  created_at?: number
}

// 获取应用发布配置响应结构
export type GetPublishedConfigResponse = BaseResponse<{
  web_app: {
    token: string
    status: string
  }
}>

// 重新生成WebApp凭证标识响应结构
export type RegenerateWebAppTokenResponse = BaseResponse<{
  token: string
}>

export type PlannerWorkerBinding = {
  id: string
  enabled: boolean
  priority: number
  conditions: Record<string, any>
  worker_agent: {
    id: string
    name: string
    icon: string
    description: string
    runtime_type: string
    product_category: string
    status: string
    target_ref_type: string
    target_ref_id: string
  }
  worker_app: {
    id: string
    name: string
    icon: string
    description: string
    agent_type: AgentType
    status: string
  } | null
  capability_summary?: WorkerCapabilitySummary
  created_at: number
  updated_at: number
}

export type GetPlannerWorkersResponse = BaseResponse<{ list: PlannerWorkerBinding[] }>

export type BindPlannerWorkerRequest = {
  worker_app_id?: string
  worker_agent_id?: string
  enabled: boolean
  priority: number
  conditions: Record<string, any>
}

export type UpdatePlannerWorkerBindingRequest = {
  enabled: boolean
  priority: number
  conditions: Record<string, any>
}

export type WorkerCapabilitySummary = {
  schema_version?: string
  executor_type?: string
  input_modalities?: string[]
  output_modalities?: string[]
  semantic_tags?: string[]
  skills?: {
    id?: string
    name?: string
    description?: string
    tags?: string[]
    input_modes?: string[]
    output_modes?: string[]
  }[]
  tool_names?: string[]
  model_features?: string[]
  constraints?: Record<string, any>
  manual_overrides?: Record<string, any>
  generated_at?: number
}

export type CapabilitySummaryResponse = BaseResponse<{
  app_id?: string
  agent_id: string
  version_id: string
  refreshed?: boolean
  capability_summary: WorkerCapabilitySummary
  warnings?: Record<string, any>[]
}>

export type RefreshCapabilitySummaryRequest = {
  preserve_manual_overrides: boolean
}

export type PatchCapabilitySummaryRequest = {
  manual_overrides: Record<string, any>
}

export type RoutingPolicyResponse = BaseResponse<{
  app_id: string
  agent_id: string
  version_id: string
  routing_policy: Record<string, any>
}>

export type RoutingPolicyRequest = {
  routing_policy: Record<string, any>
}

export type RoutingPolicyValidateResponse = BaseResponse<{
  valid: boolean
  routing_policy: Record<string, any>
  errors: Record<string, any>[]
  warnings: Record<string, any>[]
}>

export type PlannerPreflightRequest = {
  message: string
  input_modalities: string[]
  candidate_worker_ids?: string[]
}

export type PlannerPreflightResult = {
  worker_id: string
  worker_name?: string
  passed: boolean
  error_code?: string
  user_message?: string
  checks: Record<string, any>[]
  capability_snapshot: WorkerCapabilitySummary
}

export type PlannerPreflightResponse = BaseResponse<{
  status: 'succeeded' | 'failed' | string
  results: PlannerPreflightResult[]
  suggested_worker_ids: string[]
}>
