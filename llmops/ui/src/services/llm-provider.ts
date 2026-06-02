import { del, get, patch, post } from '@/utils/request'
import type {
  GetLLMProvidersResponse,
  LLMModelResponse,
  LLMProviderResponse,
} from '@/models/llm-provider'

export const getLLMProviders = () => get<GetLLMProvidersResponse>('/llm-providers')

export const createLLMProvider = (body: Record<string, any>) => {
  return post<LLMProviderResponse>('/llm-providers', { body })
}

export const updateLLMProvider = (providerId: string, body: Record<string, any>) => {
  return patch<LLMProviderResponse>(`/llm-providers/${providerId}`, { body })
}

export const deleteLLMProvider = (providerId: string) => {
  return del<LLMProviderResponse>(`/llm-providers/${providerId}`)
}

export const createLLMModel = (providerId: string, body: Record<string, any>) => {
  return post<LLMModelResponse>(`/llm-providers/${providerId}/models`, { body })
}

export const updateLLMModel = (providerId: string, modelId: string, body: Record<string, any>) => {
  return patch<LLMModelResponse>(`/llm-providers/${providerId}/models/${modelId}`, { body })
}

export const deleteLLMModel = (providerId: string, modelId: string) => {
  return del<LLMModelResponse>(`/llm-providers/${providerId}/models/${modelId}`)
}
