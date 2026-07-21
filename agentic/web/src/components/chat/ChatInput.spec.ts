import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChatInput from './ChatInput.vue'
import ChatComposer from './ChatComposer.vue'

vi.mock('@/lib/api/skills', () => ({
  skillsApi: { list: vi.fn().mockResolvedValue([]) },
}))
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }),
}))
vi.mock('./ChatComposer.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      name: 'ChatComposer',
      inheritAttrs: false,
      props: ['modelValue'],
      emits: ['update:modelValue', 'send'],
      setup: () => () => h('div'),
    }),
  }
})

const draftKey = (sessionId: string) => `agentic:chat-draft:${sessionId}`

function mountInput(sessionId: string, onSend = vi.fn().mockResolvedValue(undefined)) {
  return mount(ChatInput, {
    props: { sessionId, onSend },
    global: { stubs: { ElInput: true, ElTooltip: true, ElProgress: true } },
  })
}

describe('ChatInput session draft persistence', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('restores text for the same session after remounting', async () => {
    const first = mountInput('session-1')
    first.findComponent(ChatComposer).vm.$emit('update:modelValue', 'unfinished draft')
    await flushPromises()

    expect(localStorage.getItem(draftKey('session-1'))).toBe('unfinished draft')
    first.unmount()

    const restored = mountInput('session-1')
    expect(restored.findComponent(ChatComposer).props('modelValue')).toBe('unfinished draft')
  })

  it('isolates drafts when switching sessions', async () => {
    localStorage.setItem(draftKey('session-2'), 'second session')
    const wrapper = mountInput('session-1')
    wrapper.findComponent(ChatComposer).vm.$emit('update:modelValue', 'first session')
    await wrapper.setProps({ sessionId: 'session-2' })
    await flushPromises()

    expect(localStorage.getItem(draftKey('session-1'))).toBe('first session')
    expect(wrapper.findComponent(ChatComposer).props('modelValue')).toBe('second session')
  })

  it('clears the stored draft after a successful send', async () => {
    const onSend = vi.fn().mockResolvedValue(undefined)
    const wrapper = mountInput('session-1', onSend)
    const composer = wrapper.findComponent(ChatComposer)
    composer.vm.$emit('update:modelValue', 'send me')
    composer.vm.$emit('send')
    await flushPromises()

    expect(onSend).toHaveBeenCalledOnce()
    expect(localStorage.getItem(draftKey('session-1'))).toBeNull()
    expect(composer.props('modelValue')).toBe('')
  })

  it('keeps the draft when queueing or sending fails', async () => {
    const onSend = vi.fn().mockRejectedValue(new Error('queue conflict'))
    const wrapper = mountInput('session-1', onSend)
    const composer = wrapper.findComponent(ChatComposer)
    composer.vm.$emit('update:modelValue', 'keep me')
    composer.vm.$emit('send')
    await flushPromises()

    expect(localStorage.getItem(draftKey('session-1'))).toBe('keep me')
    expect(composer.props('modelValue')).toBe('keep me')
  })

  it('keeps editing usable when localStorage rejects writes', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage unavailable')
    })
    const wrapper = mountInput('session-1')
    const composer = wrapper.findComponent(ChatComposer)

    expect(() => composer.vm.$emit('update:modelValue', 'memory only')).not.toThrow()
    await flushPromises()
    expect(composer.props('modelValue')).toBe('memory only')
  })

  it('does not clear the next session draft when an earlier send finishes late', async () => {
    let finishSend!: () => void
    const onSend = vi.fn().mockImplementation(
      () => new Promise<void>((resolve) => { finishSend = resolve }),
    )
    localStorage.setItem(draftKey('session-2'), 'second session draft')
    const wrapper = mountInput('session-1', onSend)
    const composer = wrapper.findComponent(ChatComposer)
    composer.vm.$emit('update:modelValue', 'first session message')
    composer.vm.$emit('send')
    await flushPromises()

    await wrapper.setProps({ sessionId: 'session-2' })
    await flushPromises()
    finishSend()
    await flushPromises()

    expect(localStorage.getItem(draftKey('session-1'))).toBeNull()
    expect(localStorage.getItem(draftKey('session-2'))).toBe('second session draft')
    expect(composer.props('modelValue')).toBe('second session draft')
  })
})
