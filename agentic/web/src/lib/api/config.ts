import { get, post } from './fetch'
import type {
  A2AServersData,
  AgentConfig,
  CreateA2AServerParams,
  LLMConfig,
  MCPConfig,
  MCPServersData,
  StorageConfig,
} from './types'

export const configApi = {
  getStorageConfig: (): Promise<StorageConfig> => get<StorageConfig>('/app-config/storage'),

  updateStorageConfig: (config: StorageConfig): Promise<StorageConfig> => post<StorageConfig>('/app-config/storage', config),

  testStorageConfig: (provider: StorageConfig['default_provider']): Promise<{ provider: string; ok: boolean }> =>
    post<{ provider: string; ok: boolean }>('/app-config/storage/test', { provider }),
  getLLMConfig: (): Promise<LLMConfig> => {
    return get<LLMConfig>('/app-config/llm')
  },

  updateLLMConfig: (config: LLMConfig): Promise<LLMConfig> => {
    return post<LLMConfig>('/app-config/llm', config)
  },

  getAgentConfig: (): Promise<AgentConfig> => {
    return get<AgentConfig>('/app-config/agent')
  },

  updateAgentConfig: (config: AgentConfig): Promise<AgentConfig> => {
    return post<AgentConfig>('/app-config/agent', config)
  },

  getMCPServers: (): Promise<MCPServersData> => {
    return get<MCPServersData>('/app-config/mcp-servers')
  },

  addMCPServer: (config: MCPConfig): Promise<void> => {
    return post<void>('/app-config/mcp-servers', config)
  },

  deleteMCPServer: (serverName: string): Promise<void> => {
    return post<void>(`/app-config/mcp-servers/${serverName}/delete`, {})
  },

  updateMCPServerEnabled: (serverName: string, enabled: boolean): Promise<void> => {
    return post<void>(`/app-config/mcp-servers/${serverName}/enabled`, { enabled })
  },

  getA2AServers: (): Promise<A2AServersData> => {
    return get<A2AServersData>('/app-config/a2a-servers')
  },

  addA2AServer: (params: CreateA2AServerParams): Promise<void> => {
    return post<void>('/app-config/a2a-servers', params)
  },

  deleteA2AServer: (a2aId: string): Promise<void> => {
    return post<void>(`/app-config/a2a-servers/${a2aId}/delete`, {})
  },

  updateA2AServerEnabled: (a2aId: string, enabled: boolean): Promise<void> => {
    return post<void>(`/app-config/a2a-servers/${a2aId}/enabled`, { enabled })
  },
}
