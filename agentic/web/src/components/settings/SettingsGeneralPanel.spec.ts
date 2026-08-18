import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsGeneralPanel from './SettingsGeneralPanel.vue'

const mocks = vi.hoisted(() => ({
  getAgentConfig: vi.fn(),
  updateAgentConfig: vi.fn(),
  listTools: vi.fn(),
  updateBindings: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@/lib/api/config', () => ({
  configApi: {
    getAgentConfig: mocks.getAgentConfig,
    updateAgentConfig: mocks.updateAgentConfig,
  },
}))

vi.mock('@/lib/api/tools', () => ({
  toolsApi: {
    listTools: mocks.listTools,
    updateBindings: mocks.updateBindings,
    preflight: vi.fn(),
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: mocks.toastSuccess, error: mocks.toastError }),
}))

const toolData = {
  tools: [],
  registrations: [],
  runtime_policy: {
    allowed_executor_types: ['builtin', 'mcp', 'a2a', 'api'],
    max_tool_iterations: 100,
  },
}

describe('SettingsGeneralPanel runtime settings', () => {
  beforeEach(() => {
    mocks.getAgentConfig.mockResolvedValue({})
    mocks.updateAgentConfig.mockResolvedValue({})
    mocks.listTools.mockResolvedValue(structuredClone(toolData))
    mocks.updateBindings.mockImplementation(async ({ runtime_policy }) => ({
      ...structuredClone(toolData),
      runtime_policy,
    }))
  })

  it('does not render or submit terminal-user approval settings', async () => {
    const wrapper = mount(SettingsGeneralPanel)
    await flushPromises()

    expect(wrapper.text()).not.toContain('高风险工具执行前确认')
    expect(wrapper.text()).not.toContain('系统工具审批')
    expect(wrapper.find('.tool-approval-settings').exists()).toBe(false)

    await wrapper.vm.save()

    expect(mocks.updateBindings).toHaveBeenCalledWith({
      bindings: {},
      runtime_policy: toolData.runtime_policy,
    })
    expect(JSON.stringify(mocks.updateBindings.mock.calls[0]?.[0])).not.toContain('approval')
  })
})
