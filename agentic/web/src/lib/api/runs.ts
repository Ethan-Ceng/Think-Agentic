import { get } from './fetch'
import type {
  RunDetailData,
  RunEventsData,
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

  listSkills: (runId: string): Promise<RunSkill[]> => {
    return get<RunSkill[]>(`/runs/${runId}/skills`)
  },

  listEvents: (runId: string): Promise<RunEventsData> => {
    return get<RunEventsData>(`/runs/${runId}/events`)
  },

  listToolCalls: (runId: string): Promise<RunToolCallsData> => {
    return get<RunToolCallsData>(`/runs/${runId}/tool-calls`)
  },

  listModelCalls: (runId: string): Promise<RunModelCallsData> => {
    return get<RunModelCallsData>(`/runs/${runId}/model-calls`)
  },
}
