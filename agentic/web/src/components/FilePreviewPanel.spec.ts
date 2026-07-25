import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AttachmentFile } from '@/lib/session-events'
import FilePreviewPanel from './FilePreviewPanel.vue'

const mocks = vi.hoisted(() => ({
  downloadFile: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('@/lib/api/file', () => ({
  fileApi: {
    downloadFile: mocks.downloadFile,
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    success: mocks.success,
    error: mocks.error,
    info: vi.fn(),
  }),
}))

function file(
  overrides: Partial<AttachmentFile> = {},
): AttachmentFile {
  return {
    id: 'file-1',
    filename: 'report.md',
    extension: 'md',
    size: 128,
    ...overrides,
  }
}

function installUrlMocks() {
  const createObjectURL = vi.fn(() => 'blob:file-preview')
  const revokeObjectURL = vi.fn()
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL,
    revokeObjectURL,
  })
  return { createObjectURL, revokeObjectURL }
}

describe('FilePreviewPanel', () => {
  beforeEach(() => {
    mocks.downloadFile.mockReset()
    mocks.success.mockReset()
    mocks.error.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads Markdown once, defaults to safe preview, and reuses the Blob for source and download', async () => {
    const blob = new Blob(['# Report\n\n<script>alert(1)</script>'], {
      type: 'text/markdown',
    })
    mocks.downloadFile.mockResolvedValue(blob)
    const { createObjectURL, revokeObjectURL } = installUrlMocks()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const wrapper = mount(FilePreviewPanel, {
      attachTo: document.body,
      props: { file: file() },
    })
    await flushPromises()

    expect(mocks.downloadFile).toHaveBeenCalledOnce()
    expect(wrapper.get('[role="tab"][data-view="preview"]').attributes('aria-selected')).toBe(
      'true',
    )
    expect(wrapper.get('.file-markdown-preview h1').text()).toBe('Report')
    expect(wrapper.find('.file-markdown-preview script').exists()).toBe(false)

    await wrapper.get('[role="tab"][data-view="preview"]').trigger('keydown', {
      key: 'ArrowLeft',
    })
    await flushPromises()
    expect(document.activeElement).toBe(
      wrapper.get('[role="tab"][data-view="source"]').element,
    )
    expect(wrapper.get('.file-source-code').text()).toContain('# Report')
    expect(mocks.downloadFile).toHaveBeenCalledOnce()

    await wrapper.get('[aria-label="下载文件"]').trigger('click')
    expect(mocks.downloadFile).toHaveBeenCalledOnce()
    expect(createObjectURL).toHaveBeenCalledWith(blob)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:file-preview')
    expect(mocks.success).toHaveBeenCalledWith('已下载「report.md」')
    wrapper.unmount()
    click.mockRestore()
  })

  it('renders HTML and SVG only inside the safe sandbox', async () => {
    mocks.downloadFile.mockResolvedValue(
      new Blob(['<svg><script>alert(1)</script><text>demo</text></svg>']),
    )
    const wrapper = mount(FilePreviewPanel, {
      props: {
        file: file({
          filename: 'diagram.svg',
          extension: 'svg',
        }),
      },
    })
    await flushPromises()

    const iframe = wrapper.get('iframe')
    expect(iframe.attributes('sandbox')).toBe('')
    expect(iframe.attributes('srcdoc')).toContain("script-src 'none'")
    expect(iframe.attributes('srcdoc')).toContain('<svg>')
  })

  it('shows source-only code without redundant tabs', async () => {
    mocks.downloadFile.mockResolvedValue(new Blob(['const value = 1\n']))
    const wrapper = mount(FilePreviewPanel, {
      props: {
        file: file({
          filename: 'source.ts',
          extension: 'ts',
        }),
      },
    })
    await flushPromises()

    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)
    expect(wrapper.get('.file-source-code').text()).toBe('const value = 1')
  })

  it('revokes image URLs and ignores stale file responses after a rapid switch', async () => {
    let resolveFirst!: (blob: Blob) => void
    let resolveSecond!: (blob: Blob) => void
    const first = new Promise<Blob>((resolve) => {
      resolveFirst = resolve
    })
    const second = new Promise<Blob>((resolve) => {
      resolveSecond = resolve
    })
    mocks.downloadFile.mockImplementation((fileId: string) =>
      fileId === 'image-1' ? first : second,
    )
    const { createObjectURL, revokeObjectURL } = installUrlMocks()
    createObjectURL
      .mockReturnValueOnce('blob:image-2')
      .mockReturnValueOnce('blob:stale-image-1')

    const wrapper = mount(FilePreviewPanel, {
      props: {
        file: file({
          id: 'image-1',
          filename: 'first.png',
          extension: 'png',
        }),
      },
    })
    await wrapper.setProps({
      file: file({
        id: 'image-2',
        filename: 'second.png',
        extension: 'png',
      }),
    })

    resolveSecond(new Blob(['second'], { type: 'image/png' }))
    await flushPromises()
    expect(wrapper.get('img').attributes('src')).toBe('blob:image-2')

    resolveFirst(new Blob(['first'], { type: 'image/png' }))
    await flushPromises()
    expect(wrapper.get('img').attributes('src')).toBe('blob:image-2')
    expect(createObjectURL).toHaveBeenCalledOnce()

    wrapper.unmount()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:image-2')
  })

  it('does not fetch unsupported files until download is requested', async () => {
    const blob = new Blob(['binary'])
    mocks.downloadFile.mockResolvedValue(blob)
    const { createObjectURL } = installUrlMocks()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const wrapper = mount(FilePreviewPanel, {
      props: {
        file: file({
          filename: 'archive.zip',
          extension: 'zip',
        }),
      },
    })
    await flushPromises()

    expect(mocks.downloadFile).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂不支持预览此文件类型')
    const downloadButtons = wrapper.findAll('button').filter((button) =>
      button.text().includes('下载文件'),
    )
    await downloadButtons[0].trigger('click')
    await flushPromises()

    expect(mocks.downloadFile).toHaveBeenCalledOnce()
    expect(createObjectURL).toHaveBeenCalledWith(blob)
    click.mockRestore()
  })

  it('shows current errors and retries without letting stale errors replace the next file', async () => {
    mocks.downloadFile
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValueOnce(new Blob(['recovered']))
    const wrapper = mount(FilePreviewPanel, {
      props: {
        file: file({
          filename: 'notes.txt',
          extension: 'txt',
        }),
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('network unavailable')
    expect(mocks.error).toHaveBeenCalledWith('network unavailable')
    const retry = wrapper.findAll('button').find((button) =>
      button.text().includes('重新加载'),
    )
    expect(retry).toBeDefined()
    await retry?.trigger('click')
    await flushPromises()

    expect(wrapper.get('.file-source-code').text()).toBe('recovered')
    expect(mocks.downloadFile).toHaveBeenCalledTimes(2)
  })
})
