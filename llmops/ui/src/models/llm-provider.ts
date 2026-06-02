import type { BaseResponse } from '@/models/base'

export type LLMModel = {
  id: string
  provider_id: string
  model: string
  display_name: string
  model_type: string
  features: string[]
  context_window: number
  max_output_tokens: number
  default_parameters: Record<string, any>
  enabled: boolean
  is_default: boolean
}

export type LLMProvider = {
  id: string
  provider: string
  name: string
  base_url: string
  api_key: string
  enabled: boolean
  is_default: boolean
  config: Record<string, any>
  models: LLMModel[]
}

export type GetLLMProvidersResponse = BaseResponse<LLMProvider[]>
export type LLMProviderResponse = BaseResponse<LLMProvider>
export type LLMModelResponse = BaseResponse<LLMModel>
