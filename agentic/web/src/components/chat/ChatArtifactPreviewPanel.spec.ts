import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { InlineChatArtifact } from '@/lib/chat-artifacts'
import ChatArtifactPreviewPanel from './ChatArtifactPreviewPanel.vue'

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => toast,
}))

function artifact(
  overrides: Partial<InlineChatArtifact> = {},
): InlineChatArtifact {
  return {
    id: 'message-1:fence:0',
    scope: 'message-1',
    index: 0,
    title: 'artifact-1.html',
    language: 'html',
    content: '<main>Hello</main>\n',
    kind: 'html',
    availableViews: ['source', 'preview'],
    ...overrides,
  }
}

describe('ChatArtifactPreviewPanel', () => {
  beforeEach(() => {
    toast.success.mockReset()
    toast.error.mockReset()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  it('defaults previewable artifacts to preview and switches to source accessibly', async () => {
    const wrapper = mount(ChatArtifactPreviewPanel, {
      props: { artifact: artifact() },
    })

    expect(wrapper.get('[role="tablist"]').attributes('aria-label')).toBe('Artifact 视图')
    expect(wrapper.get('[role="tab"][data-view="preview"]').attributes('aria-selected')).toBe(
      'true',
    )
    expect(wrapper.find('iframe').exists()).toBe(true)

    await wrapper.get('[role="tab"][data-view="source"]').trigger('click')
    expect(wrapper.get('[role="tab"][data-view="source"]').attributes('aria-selected')).toBe(
      'true',
    )
    expect(wrapper.get('.artifact-source-code').text()).toBe('<main>Hello</main>')
    expect(wrapper.find('iframe').exists()).toBe(false)

    await wrapper.get('[role="tab"][data-view="source"]').trigger('keydown', {
      key: 'ArrowRight',
    })
    expect(wrapper.get('[role="tab"][data-view="preview"]').attributes('aria-selected')).toBe(
      'true',
    )
  })

  it('does not show meaningless tabs for source-only code', () => {
    const wrapper = mount(ChatArtifactPreviewPanel, {
      props: {
        artifact: artifact({
          id: 'message-1:fence:1',
          title: 'artifact-2.ts',
          language: 'typescript',
          content: 'const value = 1\n',
          kind: 'code',
          availableViews: ['source'],
        }),
      },
    })

    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)
    expect(wrapper.get('.artifact-source-code').text()).toBe('const value = 1')
  })

  it('resets the default view when a different artifact is selected', async () => {
    const wrapper = mount(ChatArtifactPreviewPanel, {
      props: {
        artifact: artifact({
          id: 'message-1:fence:1',
          title: 'artifact-2.ts',
          language: 'typescript',
          content: 'const value = 1\n',
          kind: 'code',
          availableViews: ['source'],
        }),
      },
    })

    await wrapper.setProps({ artifact: artifact({ id: 'message-1:fence:2' }) })

    expect(wrapper.get('[role="tab"][data-view="preview"]').attributes('aria-selected')).toBe(
      'true',
    )
    expect(wrapper.find('iframe').exists()).toBe(true)
  })

  it('renders Markdown safely without recursively enabling artifact actions', () => {
    const wrapper = mount(ChatArtifactPreviewPanel, {
      props: {
        artifact: artifact({
          title: 'artifact-1.md',
          language: 'markdown',
          content: '# Preview\n\n<script>alert(1)</script>\n\n```js\nalert(1)\n```',
          kind: 'markdown',
        }),
      },
    })

    expect(wrapper.get('.artifact-markdown-preview h1').text()).toBe('Preview')
    expect(wrapper.find('.artifact-markdown-preview script').exists()).toBe(false)
    expect(wrapper.find('.artifact-markdown-preview .markdown-artifact').exists()).toBe(false)
  })

  it('copies, downloads and closes without backend calls', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    const createObjectURL = vi.fn(() => 'blob:artifact-panel')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const selected = artifact()
    const wrapper = mount(ChatArtifactPreviewPanel, {
      props: { artifact: selected },
    })

    await wrapper.get('[aria-label="复制 Artifact"]').trigger('click')
    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith(selected.content))
    expect(toast.success).toHaveBeenCalledWith('代码已复制')

    await wrapper.get('[aria-label="下载 Artifact"]').trigger('click')
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:artifact-panel')
    expect(toast.success).toHaveBeenCalledWith('已下载 artifact-1.html')

    await wrapper.get('[aria-label="关闭 Artifact 预览"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)

    click.mockRestore()
    vi.unstubAllGlobals()
  })
})
