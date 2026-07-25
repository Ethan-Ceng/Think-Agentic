import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MarkdownContent from './MarkdownContent.vue'

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => toast,
}))

describe('MarkdownContent artifacts', () => {
  beforeEach(() => {
    toast.success.mockReset()
    toast.error.mockReset()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  it('keeps existing safe Markdown behavior when artifacts are disabled', () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        content: '# Title\n\n<script>alert(1)</script>\n\n```ts\nconst value = 1\n```',
      },
    })

    expect(wrapper.get('h1').text()).toBe('Title')
    expect(wrapper.find('.markdown-artifact').exists()).toBe(false)
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>alert(1)</script>')
    expect(wrapper.get('pre code').text()).toBe('const value = 1')
  })

  it('renders actions only for closed non-empty fences and emits the selected original block', async () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        artifactScope: 'event-7',
        enableArtifacts: true,
        content: [
          '```html',
          '<main data-value="a&b">Hello</main>',
          '```',
          '',
          '```ts',
          'const escaped = "<tag>"',
          '```',
          '',
          '```md',
          '   ',
          '```',
          '',
          '```python',
          'print("streaming")',
        ].join('\n'),
      },
    })

    const artifacts = wrapper.findAll('.markdown-artifact')
    expect(artifacts).toHaveLength(2)
    expect(artifacts[0].attributes('data-artifact-id')).toBe('event-7:fence:0')
    expect(artifacts[1].attributes('data-artifact-id')).toBe('event-7:fence:1')
    expect(artifacts[0].get('code').text()).toBe('<main data-value="a&b">Hello</main>')
    expect(artifacts[1].get('code').text()).toBe('const escaped = "<tag>"')
    expect(wrapper.text()).toContain('print("streaming")')

    await artifacts[1].get('[data-artifact-action="open"]').trigger('click')
    expect(wrapper.emitted('artifactOpen')).toEqual([[
      expect.objectContaining({
        id: 'event-7:fence:1',
        content: 'const escaped = "<tag>"\n',
        language: 'typescript',
        title: 'artifact-2.ts',
      }),
    ]])
  })

  it('copies the original content and reports success', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    const wrapper = mount(MarkdownContent, {
      props: {
        artifactScope: 'event-copy',
        enableArtifacts: true,
        content: '```json\n{"value":"<&>"}\n```',
      },
    })

    await wrapper.get('[data-artifact-action="copy"]').trigger('click')
    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith('{"value":"<&>"}\n'))
    expect(toast.success).toHaveBeenCalledWith('代码已复制')
  })

  it('preserves code text while retaining the existing CJK autolink behavior in prose', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    const wrapper = mount(MarkdownContent, {
      props: {
        artifactScope: 'event-url',
        enableArtifacts: true,
        content: '访问 https://example.com路径\n\n```text\nhttps://example.com路径\n```',
      },
    })

    expect(wrapper.get('p').text()).toBe('访问 https://example.com 路径')
    await wrapper.get('[data-artifact-action="copy"]').trigger('click')
    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith('https://example.com路径\n'))
  })

  it('reports a copy failure when neither clipboard path is available', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: undefined,
    })
    const originalExecCommand = document.execCommand
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: undefined,
    })
    const wrapper = mount(MarkdownContent, {
      props: {
        artifactScope: 'event-copy-error',
        enableArtifacts: true,
        content: '```text\ncannot copy\n```',
      },
    })

    await wrapper.get('[data-artifact-action="copy"]').trigger('click')
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith('复制失败'))
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: originalExecCommand,
    })
  })

  it('downloads the original content with a generated safe filename', async () => {
    const createObjectURL = vi.fn(() => 'blob:artifact')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const wrapper = mount(MarkdownContent, {
      props: {
        artifactScope: 'event-download',
        enableArtifacts: true,
        content: '```css\nbody { color: red; }\n```',
      },
    })

    await wrapper.get('[data-artifact-action="download"]').trigger('click')

    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(click).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:artifact')
    expect(toast.success).toHaveBeenCalledWith('已下载 artifact-1.css')
    click.mockRestore()
    vi.unstubAllGlobals()
  })
})
