import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProviderDiagnosticCard from './ProviderDiagnosticCard.vue'

const mocks = vi.hoisted(() => ({ test: vi.fn() }))

vi.mock('@/lib/api/provider-diagnostics', () => ({
  providerDiagnosticsApi: { test: mocks.test },
}))

describe('ProviderDiagnosticCard', () => {
  beforeEach(() => {
    mocks.test.mockReset()
    mocks.test.mockResolvedValue({
      provider_type: 'mcp',
      provider_id: 'mcp.docs',
      check_kind: 'discovery',
      status: 'healthy',
      message: 'MCP Tool Schema 获取成功。',
      checked_at: '2026-08-19T09:00:00Z',
      latency_ms: 12,
      capability_count: 3,
      snapshot_state: 'fresh',
      failure: null,
    })
  })

  it('tests only the saved provider identity and renders the unified result', async () => {
    const wrapper = mount(ProviderDiagnosticCard, {
      props: { providerType: 'mcp', targetId: 'docs' },
    })

    await wrapper.get('.provider-diagnostic-button').trigger('click')
    await flushPromises()

    expect(mocks.test).toHaveBeenCalledWith({
      provider_type: 'mcp',
      target_id: 'docs',
    })
    expect(wrapper.get('.provider-diagnostic-result').text()).toContain('正常')
    expect(wrapper.get('.provider-diagnostic-result').text()).toContain('发现 3 项能力')
    expect(wrapper.text()).not.toContain('https://')
  })

  it('clears a stale result when saved configuration identity changes', async () => {
    const wrapper = mount(ProviderDiagnosticCard, {
      props: { providerType: 'mcp', targetId: 'docs', resetKey: 'enabled' },
    })
    await wrapper.get('.provider-diagnostic-button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.provider-diagnostic-result').exists()).toBe(true)

    await wrapper.setProps({ resetKey: 'disabled' })

    expect(wrapper.find('.provider-diagnostic-result').exists()).toBe(false)
  })

  it('discards an in-flight result after configuration changes', async () => {
    let resolveRequest!: (value: unknown) => void
    mocks.test.mockReturnValueOnce(new Promise((resolve) => {
      resolveRequest = resolve
    }))
    const wrapper = mount(ProviderDiagnosticCard, {
      props: { providerType: 'mcp', targetId: 'docs', resetKey: 'v1' },
    })

    await wrapper.get('.provider-diagnostic-button').trigger('click')
    await wrapper.setProps({ resetKey: 'v2' })
    resolveRequest({
      provider_type: 'mcp',
      provider_id: 'mcp.docs',
      check_kind: 'discovery',
      status: 'healthy',
      message: 'old result',
      checked_at: '2026-08-19T09:00:00Z',
      latency_ms: 5,
    })
    await flushPromises()

    expect(wrapper.find('.provider-diagnostic-result').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('old result')
  })

  it('does not start a diagnostic while unsaved changes disable the action', async () => {
    const wrapper = mount(ProviderDiagnosticCard, {
      props: { providerType: 'llm', disabled: true },
    })

    await wrapper.get('.provider-diagnostic-button').trigger('click')

    expect(mocks.test).not.toHaveBeenCalled()
  })

  it('labels configuration success without claiming remote connectivity', async () => {
    mocks.test.mockResolvedValueOnce({
      provider_type: 'api',
      provider_id: 'api.weather',
      check_kind: 'configuration',
      status: 'healthy',
      message: 'API Tool 配置有效；未调用远程 Operation。',
      checked_at: '2026-08-19T09:00:00Z',
      latency_ms: 3,
      capability_count: 1,
    })
    const wrapper = mount(ProviderDiagnosticCard, {
      props: { providerType: 'api', targetId: 'api.weather' },
    })

    await wrapper.get('.provider-diagnostic-button').trigger('click')
    await flushPromises()

    expect(wrapper.get('.provider-diagnostic-result').text()).toContain('配置有效')
    expect(wrapper.get('.provider-diagnostic-result').text()).not.toContain('连接正常')
  })
})
