import { get, post } from './fetch'
import type {
  CreateToolRegistrationParams,
  ToolCapabilitySummary,
  ToolListData,
  ToolPreflightParams,
  ToolPreflightResponse,
  ToolRegistrationTestData,
  ToolRegistrationTestParams,
  ToolRegistrationListData,
  UpdateToolRegistrationParams,
  UpdateToolBindingsParams,
} from './types'

export const toolsApi = {
  listTools: (): Promise<ToolListData> => {
    return get<ToolListData>('/tools')
  },

  updateBindings: (params: UpdateToolBindingsParams): Promise<ToolListData> => {
    return post<ToolListData>('/tools/bindings', params)
  },

  listRegistrations: (): Promise<ToolRegistrationListData> => {
    return get<ToolRegistrationListData>('/tools/registrations')
  },

  createRegistration: (params: CreateToolRegistrationParams): Promise<ToolRegistrationListData> => {
    return post<ToolRegistrationListData>('/tools/registrations', params)
  },

  updateRegistration: (
    registrationId: string,
    params: UpdateToolRegistrationParams,
  ): Promise<ToolRegistrationListData> => {
    return post<ToolRegistrationListData>(`/tools/registrations/${registrationId}`, params)
  },

  deleteRegistration: (registrationId: string): Promise<ToolRegistrationListData> => {
    return post<ToolRegistrationListData>(`/tools/registrations/${registrationId}/delete`, {})
  },

  testRegistration: (
    registrationId: string,
    params: ToolRegistrationTestParams,
  ): Promise<ToolRegistrationTestData> => {
    return post<ToolRegistrationTestData>(`/tools/registrations/${registrationId}/test`, params)
  },

  getCapabilitySummary: (): Promise<ToolCapabilitySummary> => {
    return get<ToolCapabilitySummary>('/tools/capability-summary')
  },

  preflight: (params: ToolPreflightParams): Promise<ToolPreflightResponse> => {
    return post<ToolPreflightResponse>('/tools/preflight', params)
  },

  resetDefaults: (): Promise<ToolListData> => {
    return post<ToolListData>('/tools/reset-defaults', {})
  },
}
