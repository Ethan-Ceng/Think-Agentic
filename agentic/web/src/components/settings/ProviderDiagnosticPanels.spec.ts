import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsA2aPanel from './SettingsA2aPanel.vue'
import SettingsApiToolsPanel from './SettingsApiToolsPanel.vue'
import SettingsMcpPanel from './SettingsMcpPanel.vue'
import SettingsModelPanel from './SettingsModelPanel.vue'

const mocks = vi.hoisted(() => ({
  getLLMConfig: vi.fn(),
  getMCPServers: vi.fn(),
  getA2AServers: vi.fn(),
  listTools: vi.fn(),
}))

vi.mock('@/lib/api/config', () => ({
  DEFAULT_LLM_MAX_TOKENS: 8192,
  configApi: {
    getLLMConfig: mocks.getLLMConfig,
    updateLLMConfig: vi.fn(),
    getMCPServers: mocks.getMCPServers,
    updateMCPServerEnabled: vi.fn(),
    deleteMCPServer: vi.fn(),
    addMCPServer: vi.fn(),
    getA2AServers: mocks.getA2AServers,
    updateA2AServerEnabled: vi.fn(),
    deleteA2AServer: vi.fn(),
    addA2AServer: vi.fn(),
  },
}))

vi.mock('@/lib/api/tools', () => ({
  toolsApi: {
    listTools: mocks.listTools,
    updateBindings: vi.fn(),
    updateRegistration: vi.fn(),
    deleteRegistration: vi.fn(),
    createRegistration: vi.fn(),
    testRegistration: vi.fn(),
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}))

const DiagnosticStub = defineComponent({
  name: 'ProviderDiagnosticCard',
  props: {
    providerType: String,
    targetId: String,
    disabled: Boolean,
    buttonLabel: String,
  },
  template: '<div class="diagnostic-stub" />',
})

const mountOptions = {
  global: { stubs: { ProviderDiagnosticCard: DiagnosticStub } },
}

describe('settings Provider diagnostics integration', () => {
  beforeEach(() => {
    mocks.getLLMConfig.mockResolvedValue({
      base_url: 'https://llm.example.test',
      api_key: '******',
      model_name: 'model',
      temperature: 0.7,
      max_tokens: 8192,
    })
    mocks.getMCPServers.mockResolvedValue({
      mcp_servers: [
        { server_name: 'docs', enabled: false, transport: 'streamable_http', tools: [] },
      ],
    })
    mocks.getA2AServers.mockResolvedValue({
      a2a_servers: [
        {
          id: 'researcher',
          name: 'Researcher',
          description: '',
          input_modes: [],
          output_modes: [],
          streaming: false,
          push_notifications: false,
          enabled: false,
        },
      ],
    })
    mocks.listTools.mockResolvedValue({
      tools: [
        {
          tool_id: 'api.weather.lookup',
          function_name: 'weather_lookup',
          provider_id: 'api.weather',
          provider_label: 'Weather',
          group: 'custom',
          executor_type: 'api',
          label: 'Lookup',
          description: 'Lookup weather',
          schema: {},
          category: 'custom',
          risk_level: 'low',
          requires_sandbox: false,
          requires_browser: false,
          requires_credentials: false,
          enabled_by_default: true,
          enabled: true,
        },
      ],
      registrations: [
        {
          registration_id: 'weather',
          provider_id: 'api.weather',
          provider_label: 'Weather',
          source_type: 'api',
          executor_type: 'api',
          group: 'custom',
          category: 'custom',
          description: '',
          enabled: true,
          builtin: false,
          editable: true,
          requires_sandbox: false,
          requires_browser: false,
          requires_credentials: false,
          config: {},
        },
      ],
      runtime_policy: {
        allowed_executor_types: ['builtin', 'mcp', 'a2a', 'api'],
        max_tool_iterations: 100,
      },
    })
  })

  it('binds the LLM panel to the default Provider diagnostic', async () => {
    const wrapper = mount(SettingsModelPanel, mountOptions)
    await flushPromises()

    const diagnostic = wrapper.getComponent(DiagnosticStub)
    expect(diagnostic.props()).toMatchObject({
      providerType: 'llm',
      disabled: false,
    })
  })

  it('binds disabled MCP and A2A rows to their saved opaque IDs', async () => {
    const mcp = mount(SettingsMcpPanel, mountOptions)
    const a2a = mount(SettingsA2aPanel, mountOptions)
    await flushPromises()

    expect(mcp.getComponent(DiagnosticStub).props()).toMatchObject({
      providerType: 'mcp',
      targetId: 'docs',
    })
    expect(a2a.getComponent(DiagnosticStub).props()).toMatchObject({
      providerType: 'a2a',
      targetId: 'researcher',
    })
  })

  it('separates API configuration validation from real Operation invocation', async () => {
    const wrapper = mount(SettingsApiToolsPanel, mountOptions)
    await flushPromises()

    expect(wrapper.getComponent(DiagnosticStub).props()).toMatchObject({
      providerType: 'api',
      targetId: 'weather',
      buttonLabel: '校验已保存配置',
    })
    expect(wrapper.find('[aria-label="调用 Operation 测试 Weather"]').exists()).toBe(true)
  })
})
