import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ExecutionTree from './ExecutionTree.vue'

describe('ExecutionTree', () => {
  it('renders Planner and stable child hierarchy from parent_node_id', () => {
    const wrapper = mount(ExecutionTree, {
      props: {
        density: 'diagnostic',
        nodes: [
          node('tool:t1', 'step:s1', 'tool', '搜索资料', 4),
          node('plan:p1', 'run:r1', 'plan', '任务计划', 2, {
            step_count: 1,
            completed_steps: 0,
            replan_count: 1,
          }),
          node('step:s1', 'plan:p1', 'step', '检查实现', 3),
        ],
      },
    })

    expect(wrapper.text()).toContain('任务计划')
    expect(wrapper.text()).toContain('计划已调整 1 次')
    expect(wrapper.text()).toContain('检查实现')
    expect(wrapper.text()).toContain('1. 检查实现')
    expect(wrapper.text()).toContain('进行中')
    expect(wrapper.text()).toContain('搜索资料')
    const rows = wrapper.findAll('.execution-tree-row')
    expect(rows[1].attributes('style')).toContain('--execution-depth: 1')
    expect(rows[2].attributes('style')).toContain('--execution-depth: 2')
  })

  it('keeps plan steps and only the latest active micro action in chat density', async () => {
    const wrapper = mount(ExecutionTree, {
      props: {
        density: 'chat',
        nodes: [
          { ...node('model:m1', 'step:s1', 'model', '模型处理中', 4), status: 'running' },
          { ...node('tool:done', 'step:s1', 'tool', '已完成搜索', 5), status: 'succeeded' },
          { ...node('tool:t1', 'step:s1', 'tool', '正在读取页面', 6), status: 'running' },
          { ...node('step:s1', 'plan:p1', 'step', '检查实现', 3), ordinal: 0 },
          { ...node('step:s2', 'plan:p1', 'step', '实现页面', 2), ordinal: 1, status: 'pending' },
          node('plan:p1', 'run:r1', 'plan', '任务计划', 1, { step_count: 2 }),
        ],
      },
    })

    expect(wrapper.text()).not.toContain('模型处理中')
    expect(wrapper.text()).not.toContain('已完成搜索')
    expect(wrapper.text()).toContain('正在读取页面')
    expect(wrapper.text().indexOf('1. 检查实现')).toBeLessThan(
      wrapper.text().indexOf('2. 实现页面'),
    )
    await wrapper.get('.kind-tool .execution-node').trigger('click')
    expect(wrapper.emitted('toolClick')?.[0]?.[0]).toMatchObject({
      node_id: 'tool:t1',
      detail_kind: 'tool',
      detail_id: 't1',
    })
  })

  it('hides plan and step summaries in chat density', () => {
    const wrapper = mount(ExecutionTree, {
      props: {
        density: 'chat',
        nodes: [
          { ...node('plan:p1', 'run:r1', 'plan', '任务计划', 1), summary: '不要展示计划摘要' },
          { ...node('step:s1', 'plan:p1', 'step', '检查实现', 2), summary: '不要展示步骤总结' },
        ],
      },
    })

    expect(wrapper.text()).not.toContain('不要展示计划摘要')
    expect(wrapper.text()).not.toContain('不要展示步骤总结')
  })
})

function node(
  node_id: string,
  parent_node_id: string,
  kind: 'plan' | 'step' | 'tool' | 'model',
  title: string,
  cursor: number,
  metrics = {},
) {
  return {
    node_id,
    parent_node_id,
    kind,
    phase: kind === 'plan' ? 'plan' as const : 'execute' as const,
    status: 'running' as const,
    title,
    summary: title,
    cursor,
    metrics,
    detail_kind: kind === 'tool' ? 'tool' as const : undefined,
    detail_id: kind === 'tool' ? node_id.replace('tool:', '') : undefined,
  }
}
