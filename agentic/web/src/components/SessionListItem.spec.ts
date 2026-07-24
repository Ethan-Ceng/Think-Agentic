import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import SessionListItem from './SessionListItem.vue'
import type { Session } from '@/lib/api/types'

const DropdownStub = defineComponent({
  name: 'ElDropdown',
  emits: ['command'],
  template: '<div><slot /><slot name="dropdown" /></div>',
})
const DropdownMenuStub = defineComponent({
  name: 'ElDropdownMenu',
  template: '<div><slot /></div>',
})
const DropdownItemStub = defineComponent({
  name: 'ElDropdownItem',
  props: {
    command: { type: String, required: true },
    disabled: Boolean,
    title: String,
  },
  template: '<div><slot /></div>',
})

function session(overrides: Partial<Session> = {}): Session {
  return {
    session_id: 'session-1',
    title: 'Original title',
    latest_message: 'latest',
    latest_message_at: '2026-07-24T10:00:00',
    status: 'completed',
    unread_message_count: 0,
    is_pinned: false,
    archived_at: null,
    has_next_message: false,
    ...overrides,
  }
}

function mountItem(value = session()) {
  return mount(SessionListItem, {
    props: { session: value, active: false },
    global: {
      stubs: {
        ElDropdown: DropdownStub,
        ElDropdownMenu: DropdownMenuStub,
        ElDropdownItem: DropdownItemStub,
      },
    },
  })
}

describe('SessionListItem', () => {
  it('renames inline with Enter and cancels with Escape', async () => {
    const wrapper = mountItem()
    wrapper.findComponent(DropdownStub).vm.$emit('command', 'rename')
    await nextTick()

    const input = wrapper.get('input[aria-label="新的任务标题"]')
    expect((input.element as HTMLInputElement).value).toBe('Original title')
    await input.setValue('  Durable title  ')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('rename')).toEqual([
      [expect.objectContaining({ session_id: 'session-1' }), 'Durable title'],
    ])

    await wrapper.setProps({ session: session({ title: 'Durable title' }) })
    expect(wrapper.find('input').exists()).toBe(false)

    wrapper.findComponent(DropdownStub).vm.$emit('command', 'rename')
    await nextTick()
    await wrapper.get('input').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('input').exists()).toBe(false)
  })

  it('emits pin and archive commands without opening the session', async () => {
    const wrapper = mountItem()
    const dropdown = wrapper.findComponent(DropdownStub)

    dropdown.vm.$emit('command', 'pin')
    dropdown.vm.$emit('command', 'archive')
    await nextTick()

    expect(wrapper.emitted('togglePin')).toHaveLength(1)
    expect(wrapper.emitted('archive')).toHaveLength(1)
    expect(wrapper.emitted('open')).toBeUndefined()
  })

  it('disables archive while running, waiting, or queued', () => {
    for (const value of [
      session({ status: 'running' }),
      session({ status: 'waiting' }),
      session({ has_next_message: true }),
    ]) {
      const wrapper = mountItem(value)
      const archive = wrapper
        .findAllComponents(DropdownItemStub)
        .find((item) => item.props('command') === 'archive')
      expect(archive?.props('disabled')).toBe(true)
      expect(archive?.props('title')).toBeTruthy()
    }
  })
})
