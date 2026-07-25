import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import MarkdownContent from '@/components/MarkdownContent.vue'
import type { TimelineItem } from '@/lib/session-events'
import ChatInlineBranchEditor from './ChatInlineBranchEditor.vue'
import ChatMessage from './ChatMessage.vue'

vi.mock('@/components/chat/ChatInlineBranchEditor.vue', () => ({
  default: {
    name: 'ChatInlineBranchEditor',
    props: ['content', 'attachmentNames', 'skills', 'busy'],
    emits: ['submit', 'cancel'],
    template:
      '<div class="stub-inline-editor"><button data-submit @click="$emit(\'submit\', \'revised\')" /><button data-cancel @click="$emit(\'cancel\')" /></div>',
  },
}))
vi.mock('@/components/chat/AttachmentsMessage.vue', () => ({
  default: { name: 'AttachmentsMessage', template: '<div />' },
}))
vi.mock('@/components/chat/AssistantAvatar.vue', () => ({
  default: { name: 'AssistantAvatar', template: '<div />' },
}))
vi.mock('@/components/chat/MessageActions.vue', () => ({
  default: { name: 'MessageActions', template: '<div />' },
}))
vi.mock('@/components/chat/ThinkingBlock.vue', () => ({
  default: { name: 'ThinkingBlock', template: '<div />' },
}))
vi.mock('@/components/chat/ToolCallCard.vue', () => ({
  default: { name: 'ToolCallCard', template: '<div />' },
}))
vi.mock('@/components/skills/SkillChip.vue', () => ({
  default: { name: 'SkillChip', template: '<div />' },
}))
vi.mock('@/components/MarkdownContent.vue', () => ({
  default: {
    name: 'MarkdownContent',
    props: { content: { type: String, default: '' } },
    template: '<div data-testid="markdown-content">{{ content }}</div>',
  },
}))

const internalError = 'AgentTaskRunner出错: 调用语言模型失败, 已达到最大重试次数(3)'
const friendlyError = '模型服务暂时不可用。请检查模型配置、账户余额或网络连接后重试。'

const errorItem: TimelineItem = {
  kind: 'error',
  id: 'error-1',
  error: internalError,
  timeLabel: '15:14',
}

describe('ChatMessage reply failure recovery', () => {
  it('shows a friendly recoverable state without exposing the internal error', () => {
    const wrapper = shallowMount(ChatMessage, {
      props: {
        item: errorItem,
        showRecoveryActions: true,
      },
    })

    expect(wrapper.text()).toContain('本次回复未完成')
    expect(wrapper.text()).not.toContain('回复异常')
    expect(wrapper.getComponent(MarkdownContent).props('content')).toBe(friendlyError)
    expect(wrapper.getComponent(MarkdownContent).props('content')).not.toContain(internalError)
  })

  it('maps reply regeneration and task restart to the existing recovery modes', async () => {
    const wrapper = shallowMount(ChatMessage, {
      props: {
        item: errorItem,
        showRecoveryActions: true,
      },
    })

    const buttons = wrapper.findAll('.task-recovery-button')
    expect(buttons).toHaveLength(2)
    expect(buttons[0].text()).toBe('重新生成回复')
    expect(buttons[1].text()).toBe('重新执行任务')

    await buttons[0].trigger('click')
    await buttons[1].trigger('click')

    expect(wrapper.emitted('recoverTask')).toEqual([['continue'], ['restart']])
  })

  it('hides recovery actions for historical errors and disables them while recovering', () => {
    const historical = shallowMount(ChatMessage, {
      props: {
        item: errorItem,
        showRecoveryActions: false,
      },
    })
    expect(historical.findAll('.task-recovery-button')).toHaveLength(0)

    const recovering = shallowMount(ChatMessage, {
      props: {
        item: errorItem,
        showRecoveryActions: true,
        recoveryBusy: true,
      },
    })
    for (const button of recovering.findAll('.task-recovery-button')) {
      expect(button.attributes('disabled')).toBeDefined()
    }
  })
})

describe('ChatMessage inline branch editing', () => {
  const userItem = {
    kind: 'user',
    id: 'user-1',
    sourceEventId: 'event-user-1',
    timeLabel: '11:00',
    data: {
      role: 'user',
      message: 'original question',
      attachments: [
        {
          file_id: 'file-1',
          filename: 'brief.pdf',
          size: 12,
        },
      ],
      skills: [{ source: 'bundled', name: 'browser' }],
    },
  } as TimelineItem

  it('replaces only the target user bubble with the inline editor', () => {
    const wrapper = shallowMount(ChatMessage, {
      props: {
        item: userItem,
        editing: true,
        editBusy: true,
      },
    })

    expect(wrapper.find('.user-bubble').exists()).toBe(false)
    const editor = wrapper.getComponent(ChatInlineBranchEditor)
    expect(editor.props('content')).toBe('original question')
    expect(editor.props('attachmentNames')).toEqual(['brief.pdf'])
    expect(editor.props('skills')).toEqual([
      { source: 'bundled', name: 'browser' },
    ])
    expect(editor.props('busy')).toBe(true)
    expect(wrapper.findComponent({ name: 'MessageActions' }).exists()).toBe(false)
    expect(wrapper.text()).toContain('11:00')
  })

  it('forwards inline submit and cancel while normal messages keep actions', async () => {
    const editing = shallowMount(ChatMessage, {
      props: {
        item: userItem,
        editing: true,
      },
    })
    editing.getComponent(ChatInlineBranchEditor).vm.$emit('submit', 'revised')
    editing.getComponent(ChatInlineBranchEditor).vm.$emit('cancel')
    expect(editing.emitted('editSubmit')).toEqual([['revised']])
    expect(editing.emitted('editCancel')).toHaveLength(1)

    const normal = shallowMount(ChatMessage, {
      props: {
        item: userItem,
        editing: false,
      },
    })
    expect(normal.find('.user-bubble').exists()).toBe(true)
    expect(normal.findComponent({ name: 'MessageActions' }).exists()).toBe(true)
  })
})
