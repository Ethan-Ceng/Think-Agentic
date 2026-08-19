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
    props: {
      content: { type: String, default: '' },
      artifactScope: { type: String, default: '' },
      enableArtifacts: Boolean,
    },
    emits: ['artifactOpen'],
    template:
      '<div data-testid="markdown-content">{{ content }}<button class="stub-open-artifact" @click="$emit(\'artifactOpen\', { id: artifactScope + \':fence:0\', scope: artifactScope, index: 0, title: \'artifact-1.html\', language: \'html\', content: \'<main>demo</main>\\n\', kind: \'html\', availableViews: [\'source\', \'preview\'] })" /></div>',
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

const providerErrorItem: TimelineItem = {
  kind: 'error',
  id: 'provider-error-1',
  error: '外部工具服务通信异常。',
  failure: {
    code: 'PROVIDER_PROTOCOL_ERROR',
    category: 'provider',
    scope: 'operation',
    source: 'mcp',
    message: '外部工具服务通信异常。',
    retryable: true,
    recovery_actions: ['retry', 'choose_provider'],
    provider_id: 'mcp.github',
    debug_id: 'debug-provider-1',
  },
  timeLabel: '15:15',
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

  it('shows provider failures as provider errors instead of model configuration errors', () => {
    const wrapper = shallowMount(ChatMessage, {
      props: {
        item: providerErrorItem,
        showRecoveryActions: true,
      },
    })

    expect(wrapper.text()).toContain('外部工具服务暂时不可用')
    expect(wrapper.getComponent(MarkdownContent).props('content')).toBe(
      '外部工具服务通信异常。',
    )
    expect(wrapper.getComponent(MarkdownContent).props('content')).not.toContain(
      '模型配置',
    )
    expect(wrapper.getComponent(MarkdownContent).props('content')).not.toContain(
      '账户余额',
    )
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

describe('ChatMessage inline artifacts', () => {
  it('enables artifacts only for assistant content and forwards the selected block', async () => {
    const assistantItem = {
      kind: 'assistant',
      id: 'assistant-1',
      sourceEventId: 'event-assistant-1',
      data: {
        role: 'assistant',
        message: '```html\n<main>demo</main>\n```',
      },
    } as TimelineItem
    const wrapper = shallowMount(ChatMessage, {
      props: { item: assistantItem },
    })

    const markdown = wrapper.getComponent(MarkdownContent)
    expect(markdown.props('enableArtifacts')).toBe(true)
    expect(markdown.props('artifactScope')).toBe('event-assistant-1')
    markdown.vm.$emit('artifactOpen', {
      id: 'event-assistant-1:fence:0',
      scope: 'event-assistant-1',
      index: 0,
      title: 'artifact-1.html',
      language: 'html',
      content: '<main>demo</main>\n',
      kind: 'html',
      availableViews: ['source', 'preview'],
    })
    expect(wrapper.emitted('artifactOpen')).toEqual([[
      expect.objectContaining({
        id: 'event-assistant-1:fence:0',
        content: '<main>demo</main>\n',
      }),
    ]])

    const error = shallowMount(ChatMessage, {
      props: {
        item: errorItem,
        showRecoveryActions: true,
      },
    })
    expect(error.getComponent(MarkdownContent).props('enableArtifacts')).toBe(false)
  })

  it('falls back to the timeline item id when an assistant event id is unavailable', () => {
    const wrapper = shallowMount(ChatMessage, {
      props: {
        item: {
          kind: 'assistant',
          id: 'assistant-local-1',
          data: { role: 'assistant', message: 'answer' },
        } as TimelineItem,
      },
    })

    expect(wrapper.getComponent(MarkdownContent).props('artifactScope')).toBe(
      'assistant-local-1',
    )
  })

  it('renders streaming markdown but withholds final-message actions', () => {
    const wrapper = shallowMount(ChatMessage, {
      props: {
        item: {
          kind: 'assistant',
          id: 'assistant-stream-stream-1',
          streaming: true,
          streamId: 'stream-1',
          data: { role: 'assistant', message: '**partial**' },
        } as TimelineItem,
      },
    })

    expect(wrapper.getComponent(MarkdownContent).props('content')).toBe('**partial**')
    expect(wrapper.findComponent({ name: 'MessageActions' }).exists()).toBe(false)
    expect(wrapper.find('.assistant-empty-card').exists()).toBe(false)
  })
})
