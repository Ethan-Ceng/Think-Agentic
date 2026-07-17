import { beforeEach, describe, expect, it, vi } from 'vitest'
import { post } from './fetch'
import { configApi } from './config'
import type { LLMConfig } from './types'

vi.mock('./fetch', () => ({
  get: vi.fn(),
  post: vi.fn(),
}))

describe('configApi', () => {
  beforeEach(() => {
    vi.mocked(post).mockResolvedValue({})
  })

  it('replaces a cleared max_tokens value before updating LLM config', async () => {
    const config = {
      base_url: 'https://api.example.com/v1',
      model_name: 'example-model',
      temperature: 0.7,
      max_tokens: null,
    } as unknown as LLMConfig

    await configApi.updateLLMConfig(config)

    expect(post).toHaveBeenCalledWith('/app-config/llm', {
      ...config,
      max_tokens: 8192,
    })
  })
})
