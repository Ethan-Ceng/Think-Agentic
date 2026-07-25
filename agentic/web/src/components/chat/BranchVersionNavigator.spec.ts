import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { BranchFamilyResponse } from '@/lib/api/types'
import BranchVersionNavigator from './BranchVersionNavigator.vue'

function makeFamily(count = 4, currentIndex = 2): BranchFamilyResponse {
  return {
    source_session_id: 'source-1',
    target_event_id: 'event-1',
    current_session_id: currentIndex === 0 ? 'source-1' : `branch-${currentIndex}`,
    variants: Array.from({ length: count }, (_, index) => ({
      session_id: index === 0 ? 'source-1' : `branch-${index}`,
      title: index === 0 ? 'Original task' : `Version ${index + 1}`,
      operation:
        index === 0
          ? 'original'
          : index % 3 === 1
            ? 'edit'
            : index % 3 === 2
              ? 'regenerate'
              : 'fork',
      status: 'completed',
      archived_at: index === count - 1 ? '2026-07-25T10:00:00' : null,
      created_at: `2026-07-25T09:${String(index).padStart(2, '0')}:00`,
      is_current: index === currentIndex,
    })),
  }
}

describe('BranchVersionNavigator', () => {
  it('shows the current operation, stable count, archive state and version list', () => {
    const wrapper = mount(BranchVersionNavigator, {
      props: {
        family: makeFamily(50, 49),
      },
    })

    expect(wrapper.get('.branch-version-count').text()).toBe('50 / 50')
    expect(wrapper.get('.branch-version-operation').text()).toContain('编辑后的版本')
    expect(wrapper.get('.branch-version-archive').text()).toBe('已归档')
    expect(wrapper.get('select').attributes('aria-label')).toBe('选择对话版本')
    expect(wrapper.findAll('option')).toHaveLength(50)
    expect(wrapper.get('select').element.value).toBe('branch-49')
  })

  it('emits previous, next and direct-list navigation without execution intent', async () => {
    const wrapper = mount(BranchVersionNavigator, {
      props: {
        family: makeFamily(5, 2),
      },
    })

    const previous = wrapper.get('.branch-version-previous')
    const next = wrapper.get('.branch-version-next')
    expect(previous.attributes('aria-label')).toBe('上一个对话版本')
    expect(next.attributes('aria-label')).toBe('下一个对话版本')

    await previous.trigger('click')
    await next.trigger('click')
    await wrapper.get('select').setValue('branch-4')

    expect(wrapper.emitted('navigate')).toEqual([
      ['branch-1'],
      ['branch-3'],
      ['branch-4'],
    ])
  })

  it('disables boundary buttons and exposes recoverable loading errors', async () => {
    const first = mount(BranchVersionNavigator, {
      props: {
        family: makeFamily(2, 0),
      },
    })
    expect(first.get('.branch-version-previous').attributes()).toHaveProperty(
      'disabled',
    )
    expect(first.get('.branch-version-next').attributes()).not.toHaveProperty(
      'disabled',
    )

    const error = mount(BranchVersionNavigator, {
      props: {
        family: null,
        error: '暂时无法加载',
        sourceSessionId: 'source-1',
        closable: true,
      },
    })
    expect(error.text()).toContain('版本导航加载失败')
    expect(error.text()).toContain('暂时无法加载')

    await error.get('[data-action="retry"]').trigger('click')
    await error.get('[data-action="source"]').trigger('click')
    await error.get('[data-action="close"]').trigger('click')
    expect(error.emitted('retry')).toHaveLength(1)
    expect(error.emitted('navigate-source')).toHaveLength(1)
    expect(error.emitted('close')).toHaveLength(1)
  })
})
