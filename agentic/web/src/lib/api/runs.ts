import { get } from './fetch'
import type {
  RunDetailData,
  RunEventsData,
  RunExecutionView,
  RunListData,
  RunModelCallsData,
  RunToolCallsData,
} from './types'
import type { RunSkill } from '@/types/skill'

export const runsApi = {
  listRuns: (params?: { session_id?: string; limit?: number }): Promise<RunListData> => {
    return get<RunListData>('/runs', params)
  },

  getRun: (runId: string): Promise<RunDetailData> => {
    return get<RunDetailData>(`/runs/${runId}`)
  },

  getExecution: (
    runId: string,
    params?: { after?: number; limit?: number; detail?: 'summary' | 'detail' },
  ): Promise<RunExecutionView> => {
    return get<RunExecutionView>(`/runs/${runId}/execution`, params)
  },

  listSkills: (runId: string): Promise<RunSkill[]> => {
    return get<{ skills: RunSkill[] }>(`/runs/${runId}/skills`).then((data) => data.skills || [])
  },

  listEvents: (runId: string, params?: { after?: number; limit?: number }): Promise<RunEventsData> => {
    return get<RunEventsData>(`/runs/${runId}/events`, params)
  },

  listToolCalls: (
    runId: string,
    params?: { after?: string; limit?: number },
  ): Promise<RunToolCallsData> => {
    return get<RunToolCallsData>(`/runs/${runId}/tool-calls`, params)
  },

  listModelCalls: (
    runId: string,
    params?: { after?: string; limit?: number },
  ): Promise<RunModelCallsData> => {
    return get<RunModelCallsData>(`/runs/${runId}/model-calls`, params)
  },
}
