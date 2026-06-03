import { get } from '@/utils/request'
import type {
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
