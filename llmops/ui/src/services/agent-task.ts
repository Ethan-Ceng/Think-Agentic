import { get } from '@/utils/request'
import type {
  GetAgentTaskMetricsRequest,
  GetAgentTaskMetricsResponse,
  GetAgentTaskDetailResponse,
  GetAgentTasksWithPageRequest,
  GetAgentTasksWithPageResponse,
} from '@/models/agent-task'

export const getAppAgentTasksWithPage = (appId: string, req: GetAgentTasksWithPageRequest) => {
  return get<GetAgentTasksWithPageResponse>(`/apps/${appId}/agent-tasks`, {
    params: {
      page: req.current_page,
      page_size: req.page_size,
      status: req.status || 'all',
      user_id: req.user_id || 'all',
      search_word: req.search_word || '',
    },
  })
}

export const getAppAgentTaskDetail = (appId: string, taskId: string) => {
  return get<GetAgentTaskDetailResponse>(`/apps/${appId}/agent-tasks/${taskId}`)
}

export const getAppAgentTaskMetrics = (appId: string, req: GetAgentTaskMetricsRequest = {}) => {
  return get<GetAgentTaskMetricsResponse>(`/apps/${appId}/agent-tasks/metrics`, {
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
