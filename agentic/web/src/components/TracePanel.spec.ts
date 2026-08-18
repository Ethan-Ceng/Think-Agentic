import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TracePanel from './TracePanel.vue'

const mocks = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
  listSkills: vi.fn(),
}))

vi.mock('@/lib/api/runs', () => ({
  runsApi: mocks,
}))

const run = {
  id: 'run-1',
  trace_id: 'trace-1',
  session_id: 'session-1',
  user_id: 'user-1',
  status: 'completed',
  input_summary: 'stream a response',
  created_at: '2026-08-18T04:00:00Z',
  started_at: '2026-08-18T04:00:00Z',
  finished_at: '2026-08-18T04:00:02Z',
}

function modelCall(ttftMs?: number | null) {
  return {
    id: 'model-1',
    run_id: 'run-1',
    session_id: 'session-1',
    agent_name: 'LeadAgent',
    provider: 'openai-compatible',
    base_url: 'https://example.test',
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

async function mountModels(ttftMs?: number | null) {
  mocks.listRuns.mockResolvedValue({ runs: [run] })
  mocks.getRun.mockResolvedValue({
    run,
    steps: [],
    tool_calls: [],
    model_calls: [modelCall(ttftMs)],
    events: [],
    skills: [],
  })
  mocks.listSkills.mockResolvedValue([])

  const wrapper = mount(TracePanel, {
    props: { sessionId: 'session-1' },
    global: {
      stubs: {
        ElTag: { template: '<span><slot /></span>' },
        RunSkillsPanel: true,
        UiState: true,
      },
    },
  })
  await flushPromises()
  const modelsTab = wrapper
    .findAll('.trace-tabs button')
    .find((button) => button.text().includes('模型'))
  expect(modelsTab).toBeDefined()
  await modelsTab!.trigger('click')
  return wrapper
}

describe('TracePanel model timing', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('shows TTFT separately from total model latency', async () => {
    const wrapper = await mountModels(87)

    const metadata = wrapper.get('.trace-record .record-meta').text()
    expect(metadata).toContain('首 Token 87 ms')
    expect(metadata).toContain('总耗时 1.3 s')
  })

  it('keeps historical model calls without TTFT readable', async () => {
    const wrapper = await mountModels(null)

    expect(wrapper.get('.trace-record .record-meta').text()).toContain('首 Token -')
  })
})
