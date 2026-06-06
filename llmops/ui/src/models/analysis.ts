import type { BaseResponse } from '@/models/base'
import type { AgentTaskRuntimeMetrics } from '@/models/agent-task'

// 获取应用分析结果响应结构
export type GetAppAnalysisResponse = BaseResponse<{
  total_messages: { data: number; pop: number }
  active_accounts: { data: number; pop: number }
  avg_of_conversation_messages: { data: number; pop: number }
  token_output_rate: { data: number; pop: number }
  cost_consumption: { data: number; pop: number }
  total_messages_trend: { x_axis: number[]; y_axis: number[] }
  active_accounts_trend: { x_axis: number[]; y_axis: number[] }
  avg_of_conversation_messages_trend: { x_axis: number[]; y_axis: number[] }
  cost_consumption_trend: { x_axis: number[]; y_axis: number[] }
}>

export type GetAppAgentRuntimeAnalysisRequest = {
  from_ts?: number
  to_ts?: number
  status?: string
  user_id?: string
  router_agent_id?: string
  worker_agent_id?: string
  group_by?: 'day' | 'worker' | 'router' | 'status' | string
}

export type GetAppAgentRuntimeAnalysisResponse = BaseResponse<AgentTaskRuntimeMetrics>
