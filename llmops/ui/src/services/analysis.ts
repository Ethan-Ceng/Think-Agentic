import { get } from '@/utils/request'
import type {
  GetAppAgentRuntimeAnalysisRequest,
  GetAppAgentRuntimeAnalysisResponse,
  GetAppAnalysisResponse,
} from '@/models/analysis'

// 获取应用统计分析服务
export const getAppAnalysis = (app_id: string) => {
  return get<GetAppAnalysisResponse>(`/analysis/app/${app_id}`)
}

export const getAppAgentRuntimeAnalysis = (
  app_id: string,
  req: GetAppAgentRuntimeAnalysisRequest = {},
) => {
  return get<GetAppAgentRuntimeAnalysisResponse>(`/analysis/app/${app_id}/agent-runtime`, {
    params: {
      from_ts: req.from_ts,
      to_ts: req.to_ts,
      status: req.status || 'all',
      user_id: req.user_id || 'all',
      router_agent_id: req.router_agent_id || 'all',
      worker_agent_id: req.worker_agent_id || 'all',
      group_by: req.group_by || 'day',
    },
  })
}
