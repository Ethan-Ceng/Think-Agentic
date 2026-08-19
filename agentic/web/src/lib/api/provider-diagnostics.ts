import { post } from './fetch'
import type { FailureInfo } from './types'

export type ProviderDiagnosticType = 'llm' | 'mcp' | 'a2a' | 'api'
export type ProviderDiagnosticCheckKind =
  | 'inference'
  | 'discovery'
  | 'configuration'
export type ProviderDiagnosticStatus = 'healthy' | 'degraded' | 'unhealthy'

export type ProviderDiagnosticRequest = {
  provider_type: ProviderDiagnosticType
  target_id?: string | null
}

export type ProviderDiagnosticResult = {
  provider_type: ProviderDiagnosticType
  provider_id: string
  check_kind: ProviderDiagnosticCheckKind
  status: ProviderDiagnosticStatus
  message: string
  checked_at: string
  latency_ms: number
  capability_count?: number | null
  snapshot_state?: 'fresh' | 'stale' | null
  failure?: FailureInfo | null
}

export const providerDiagnosticsApi = {
  test: (
    params: ProviderDiagnosticRequest,
  ): Promise<ProviderDiagnosticResult> =>
    post<ProviderDiagnosticResult>('/provider-diagnostics/test', params, {
      timeout: 35_000,
    }),
}
