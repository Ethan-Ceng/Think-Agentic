import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RunProcessBlock from './RunProcessBlock.vue'

describe('RunProcessBlock', () => {
  it('shows compact Planner progress and delegates the user toggle', async () => {
    const wrapper = mount(RunProcessBlock, {
      props: {
        state: {
          runId: 'run-1',
          inputEventId: 'input-1',
          run: {
            run_id: 'run-1',
            session_id: 'session-1',
            input_event_id: 'input-1',
            status: 'running',
            mode: 'plan',
            summary: '执行中',
            metrics: { step_count: 3, completed_steps: 1, tool_count: 2 },
          },
          nodes: [],
          cursor: 3,
          expanded: false,
          userToggled: false,
          hydrated: false,
          loading: false,
          error: '',
          traceComplete: true,
        },
      },
    })

    expect(wrapper.text()).toContain('正在执行计划 · 1/3')
    expect(wrapper.text()).toContain('2 个工具')
    expect(wrapper.find('.run-process-detail').exists()).toBe(false)
    await wrapper.get('.run-process-toggle').trigger('click')
    expect(wrapper.emitted('toggle')).toEqual([['run-1']])
  })

  it('renders the current tool once and forwards its detail click', async () => {
    const wrapper = mount(RunProcessBlock, {
      props: {
        state: {
          runId: 'run-1',
          inputEventId: 'input-1',
          run: {
            run_id: 'run-1',
            session_id: 'session-1',
            input_event_id: 'input-1',
            status: 'running',
            mode: 'plan',
            summary: '执行中',
            metrics: { step_count: 1, completed_steps: 0, tool_count: 1 },
          },
          nodes: [{
            node_id: 'tool:call-1',
            parent_node_id: 'step:1',
            kind: 'tool',
            phase: 'execute',
            status: 'running',
            title: '搜索资料',
            summary: '搜索资料',
            cursor: 3,
            metrics: {},
            detail_kind: 'tool',
            detail_id: 'call-1',
          }],
          cursor: 3,
          expanded: true,
          userToggled: false,
          hydrated: false,
          loading: false,
          error: '',
          traceComplete: true,
        },
      },
    })

    expect(wrapper.text().match(/搜索资料/g)).toHaveLength(1)
    await wrapper.get('.kind-tool .execution-node').trigger('click')
    expect(wrapper.emitted('toolClick')?.[0]).toEqual([
      'run-1',
      expect.objectContaining({ detail_id: 'call-1' }),
    ])
  })
})
