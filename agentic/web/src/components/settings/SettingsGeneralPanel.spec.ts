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
  approval_tools: [
    {
      tool_id: 'builtin.shell.shell_execute',
      function_name: 'shell_execute',
      label: '执行 Shell 命令',
      risk_level: 'high',
      approval: 'auto',
    },
    {
      tool_id: 'builtin.browser.browser_console_exec',
      function_name: 'browser_console_exec',
      label: '执行浏览器脚本',
      risk_level: 'high',
      approval: 'ask',
    },
  ],
  runtime_policy: {
    allowed_executor_types: ['builtin', 'mcp', 'a2a', 'api'],
    max_tool_iterations: 100,
    require_approval_for_high_risk: true,
  },
}

describe('SettingsGeneralPanel approval settings', () => {
  beforeEach(() => {
    mocks.getAgentConfig.mockResolvedValue({})
    mocks.updateAgentConfig.mockResolvedValue({})
    mocks.listTools.mockResolvedValue(structuredClone(toolData))
    mocks.updateBindings.mockImplementation(async ({ bindings, runtime_policy }) => ({
      ...structuredClone(toolData),
      approval_tools: toolData.approval_tools.map((item) => ({
        ...item,
        approval: bindings[item.tool_id]?.approval ?? item.approval,
      })),
      runtime_policy,
    }))
  })

  it('saves a persistent per-tool approval without changing other tools', async () => {
    const wrapper = mount(SettingsGeneralPanel)
    await flushPromises()

    expect(wrapper.text()).toContain('执行 Shell 命令')

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    expect(selects).toHaveLength(2)
    selects[0].vm.$emit('update:modelValue', 'allow')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('始终允许会跳过后续确认')

    await wrapper.vm.save()

    expect(mocks.updateBindings).toHaveBeenCalledWith({
      bindings: {
        'builtin.shell.shell_execute': {
          enabled: true,
          risk_level: 'high',
          approval: 'allow',
        },
      },
      runtime_policy: toolData.runtime_policy,
    })
  })
})
