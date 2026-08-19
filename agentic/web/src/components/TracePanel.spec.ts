import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TracePanel from './TracePanel.vue'

const mocks = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getExecution: vi.fn(),
  getRun: vi.fn(),
  listSkills: vi.fn(),
  listEvents: vi.fn(),
  listToolCalls: vi.fn(),
  listModelCalls: vi.fn(),
}))

vi.mock('@/lib/api/runs', () => ({ runsApi: mocks }))

const run = {
  id: 'run-1',
  trace_id: 'trace-1',
  session_id: 'session-1',
  user_id: 'user-1',
  status: 'completed',
  input_summary: '',
  final_summary: '',
  tool_config_snapshot: {},
  agent_config_snapshot: {},
  llm_config_snapshot: {},
  created_at: '2026-08-18T04:00:00Z',
  started_at: '2026-08-18T04:00:00Z',
  finished_at: '2026-08-18T04:00:02Z',
}

const execution = {
  schema_version: 1,
  run: {
    run_id: 'run-1',
    session_id: 'session-1',
    input_event_id: 'input-1',
    status: 'succeeded',
    mode: 'plan',
    summary: '任务已完成',
    started_at: '2026-08-18T04:00:00Z',
    finished_at: '2026-08-18T04:00:02Z',
    latency_ms: 2000,
    metrics: { step_count: 1, completed_steps: 1, tool_count: 1, model_count: 1 },
  },
  nodes: [
    {
      node_id: 'step:1',
      parent_node_id: 'plan:1',
      kind: 'step',
      phase: 'execute',
      status: 'succeeded',
      title: '检查实现',
      summary: '已完成',
      cursor: 2,
      metrics: {},
    },
  ],
  next_cursor: 2,
  has_more: false,
  trace_complete: true,
  warnings: [],
}

describe('TracePanel', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocks.listRuns.mockResolvedValue({ runs: [run] })
    mocks.getExecution.mockResolvedValue(execution)
    mocks.listSkills.mockResolvedValue([])
    mocks.listEvents.mockResolvedValue({ events: [], next_cursor: null, has_more: false })
    mocks.listToolCalls.mockResolvedValue({ tool_calls: [], next_cursor: null, has_more: false })
    mocks.listModelCalls.mockResolvedValue({ model_calls: [], next_cursor: null, has_more: false })
  })

  it('loads only the execution summary on first paint', async () => {
    const wrapper = await mountPanel()

    expect(mocks.listRuns).toHaveBeenCalledTimes(1)
    expect(mocks.getExecution).toHaveBeenCalledTimes(1)
    expect(mocks.getRun).not.toHaveBeenCalled()
    expect(mocks.listSkills).not.toHaveBeenCalled()
    expect(mocks.listEvents).not.toHaveBeenCalled()
    expect(mocks.listToolCalls).not.toHaveBeenCalled()
    expect(mocks.listModelCalls).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('检查实现')
  })

  it('loads model diagnostics lazily and separates TTFT from total latency', async () => {
    mocks.listModelCalls.mockResolvedValue({
      model_calls: [modelCall(87)],
      next_cursor: 'model-1',
      has_more: false,
    })
    const wrapper = await mountPanel()
    await clickTab(wrapper, '模型')

    const metadata = wrapper.get('.trace-record .record-meta').text()
    expect(metadata).toContain('LeadAgent')
    expect(wrapper.get('.trace-record dl').text()).toContain('首 Token87 ms')
    expect(wrapper.get('.trace-record dl').text()).toContain('总耗时1.3 s')
    expect(mocks.listModelCalls).toHaveBeenCalledTimes(1)
  })

  it('loads Skills once and keeps tab switches request-free', async () => {
    mocks.listSkills.mockResolvedValue([
      {
        id: 'skill-1',
        run_id: 'run-1',
        skill_id: 'skill-1',
        skill_version_id: 'v1',
        name: 'documents',
        source: 'bundled',
        selection_mode: 'manual',
        content_sha256: 'abc',
      },
    ])
    const wrapper = await mountPanel()

    await clickTab(wrapper, 'Skills')
    await clickTab(wrapper, '执行链')
    await clickTab(wrapper, 'Skills')

    expect(mocks.listSkills).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('documents')
  })

  it('paginates tool records with their own cursor', async () => {
    mocks.listToolCalls
      .mockResolvedValueOnce({
        tool_calls: [toolCall('tool-1')],
        next_cursor: 'tool-1',
        has_more: true,
      })
      .mockResolvedValueOnce({
        tool_calls: [toolCall('tool-2')],
        next_cursor: 'tool-2',
        has_more: false,
      })
    const wrapper = await mountPanel()
    await clickTab(wrapper, '工具')
    await wrapper.get('.load-more').trigger('click')
    await flushPromises()

    expect(mocks.listToolCalls).toHaveBeenNthCalledWith(2, 'run-1', {
      after: 'tool-1',
      limit: 100,
    })
    expect(wrapper.findAll('.trace-record')).toHaveLength(2)
  })

  it('renders technical event allowlist fields without dumping payload JSON', async () => {
    mocks.listEvents.mockResolvedValue({
      events: [
        {
          id: 'event-1',
          trace_id: 'trace-1',
          run_id: 'run-1',
          session_id: 'session-1',
          event_type: 'model.succeeded',
          ingest_seq: 9,
          schema_version: 2,
          node_id: 'model:1',
          parent_node_id: 'step:1',
          visibility: 'user',
          summary: '模型调用完成',
          payload: { reasoning_content: 'must-not-render' },
          created_at: '2026-08-18T04:00:01Z',
        },
      ],
      next_cursor: 9,
      has_more: false,
    })
    const wrapper = await mountPanel()
    await clickTab(wrapper, '技术事件')

    expect(wrapper.text()).toContain('模型调用完成')
    expect(wrapper.text()).toContain('model:1')
    expect(wrapper.text()).not.toContain('must-not-render')
  })
})

async function mountPanel() {
  const wrapper = mount(TracePanel, {
    props: { sessionId: 'session-1' },
    global: { stubs: { UiState: true } },
  })
  await flushPromises()
  return wrapper
}

async function clickTab(wrapper: Awaited<ReturnType<typeof mountPanel>>, label: string) {
  const tab = wrapper.findAll('.trace-tabs button').find((item) => item.text().includes(label))
  expect(tab).toBeDefined()
  await tab!.trigger('click')
  await flushPromises()
}

function modelCall(ttftMs?: number | null) {
  return {
    id: 'model-1',
    run_id: 'run-1',
    session_id: 'session-1',
    agent_name: 'LeadAgent',
    provider: 'openai-compatible',
    base_url: '',
    model_name: 'test-model',
    tool_schema_count: 0,
    message_count: 2,
    response_format: {},
    status: 'succeeded',
    total_tokens: 42,
    ttft_ms: ttftMs,
    latency_ms: 1250,
    request_preview: {},
    response_preview: {},
    created_at: '2026-08-18T04:00:00Z',
  }
}

function toolCall(id: string) {
  return {
    id,
    run_id: 'run-1',
    session_id: 'session-1',
    tool_call_id: id,
    tool_id: 'builtin.search.search_web',
    tool_name: 'search',
    function_name: 'search_web',
    status: 'called',
    arguments: {},
    arguments_preview: '',
    arguments_hash: 'hash',
    result: {},
    result_preview: '',
    requires_sandbox: false,
    requires_browser: false,
    requires_credentials: false,
    created_at: '2026-08-18T04:00:00Z',
  }
}
