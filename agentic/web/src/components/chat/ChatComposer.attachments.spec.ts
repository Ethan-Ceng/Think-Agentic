import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { ComposerAttachmentFile } from '@/lib/composer-attachments'
import ChatComposer from './ChatComposer.vue'

const ElInputStub = defineComponent({
  name: 'ElInput',
  inheritAttrs: false,
  template: '<textarea />',
})

const SlotStub = defineComponent({
  inheritAttrs: false,
  template: '<div><slot /></div>',
})

function attachment(overrides: Partial<ComposerAttachmentFile> = {}): ComposerAttachmentFile {
  return {
    id: 'file-1',
    filename: 'report.pdf',
    extension: 'pdf',
    size: 1024,
    contentType: 'application/pdf',
    origin: 'library',
    uploadStatus: 'uploaded',
    progress: 100,
    ...overrides,
  }
}

function mountComposer(
  props: {
    files?: ComposerAttachmentFile[]
    disabled?: boolean
    uploading?: boolean
    sending?: boolean
  } = {},
) {
  return mount(ChatComposer, {
    attachTo: document.body,
    props: {
      modelValue: 'draft',
      files: props.files ?? [],
      disabled: props.disabled ?? false,
      uploading: props.uploading ?? false,
      sending: props.sending ?? false,
    },
    global: {
      stubs: {
        ElInput: ElInputStub,
        ElTooltip: SlotStub,
        ElProgress: true,
        SkillChip: true,
        SkillPicker: true,
      },
    },
  })
}

function transferEvent(
  type: 'dragenter' | 'dragover' | 'dragleave' | 'drop',
  files: File[],
  types: string[] = ['Files'],
): DragEvent {
  const event = new Event(type, {
    bubbles: true,
    cancelable: true,
  }) as DragEvent
  Object.defineProperty(event, 'dataTransfer', {
    value: {
      files,
      types,
      dropEffect: 'none',
    },
  })
  return event
}

function pasteEvent(files: File[]): ClipboardEvent {
  const event = new Event('paste', {
    bubbles: true,
    cancelable: true,
  }) as ClipboardEvent
  Object.defineProperty(event, 'clipboardData', {
    value: { files },
  })
  return event
}

describe('ChatComposer attachment interactions', () => {
  it('offers local upload and file-library actions with keyboard dismissal', async () => {
    const wrapper = mountComposer()
    const trigger = wrapper.get('[aria-label="添加附件"]')

    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[role="menu"]').isVisible()).toBe(true)

    await wrapper.get('[aria-label="上传本地文件"]').trigger('click')
    expect(wrapper.emitted('attach')).toEqual([[]])

    await trigger.trigger('click')
    await wrapper.get('[aria-label="从我的文件选择"]').trigger('click')
    expect(wrapper.emitted('openFileLibrary')).toEqual([[]])

    await trigger.trigger('click')
    await wrapper.get('[role="menu"]').trigger('keydown', { key: 'Escape' })
    await nextTick()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('keeps nested file drag transitions stable and drops into the existing file event', async () => {
    const wrapper = mountComposer()
    const composer = wrapper.get('.chat-composer')
    const file = new File(['image'], 'photo.png', { type: 'image/png' })

    const firstEnter = transferEvent('dragenter', [file])
    composer.element.dispatchEvent(firstEnter)
    composer.element.dispatchEvent(transferEvent('dragenter', [file]))
    await nextTick()

    expect(firstEnter.defaultPrevented).toBe(true)
    expect(wrapper.get('[data-testid="composer-drop-overlay"]').text()).toContain(
      '释放以上传文件',
    )

    composer.element.dispatchEvent(transferEvent('dragleave', [file]))
    await nextTick()
    expect(wrapper.find('[data-testid="composer-drop-overlay"]').exists()).toBe(true)

    const drop = transferEvent('drop', [file])
    composer.element.dispatchEvent(drop)
    await nextTick()

    expect(drop.defaultPrevented).toBe(true)
    expect(wrapper.find('[data-testid="composer-drop-overlay"]').exists()).toBe(false)
    expect(wrapper.emitted('pasteFiles')?.[0]?.[0]).toEqual([file])
    wrapper.unmount()
  })

  it('routes paste and drop through the same existing file event', async () => {
    const wrapper = mountComposer()
    const composer = wrapper.get('.chat-composer')
    const pasted = new File(['paste'], 'paste.txt', { type: 'text/plain' })
    const dropped = new File(['drop'], 'drop.txt', { type: 'text/plain' })

    composer.element.dispatchEvent(pasteEvent([pasted]))
    composer.element.dispatchEvent(transferEvent('drop', [dropped]))
    await nextTick()

    expect(wrapper.emitted('pasteFiles')).toEqual([
      [[pasted]],
      [[dropped]],
    ])
    wrapper.unmount()
  })

  it('does not intercept non-file drags or attachment input while disabled', async () => {
    const wrapper = mountComposer()
    const composer = wrapper.get('.chat-composer')
    const textDrag = transferEvent('dragenter', [], ['text/plain'])

    composer.element.dispatchEvent(textDrag)
    await nextTick()

    expect(textDrag.defaultPrevented).toBe(false)
    expect(wrapper.find('[data-testid="composer-drop-overlay"]').exists()).toBe(false)

    await wrapper.setProps({ disabled: true })
    const file = new File(['disabled'], 'disabled.txt', { type: 'text/plain' })
    const disabledDrop = transferEvent('drop', [file])
    composer.element.dispatchEvent(disabledDrop)
    composer.element.dispatchEvent(pasteEvent([file]))
    await nextTick()

    expect(disabledDrop.defaultPrevented).toBe(false)
    expect(wrapper.emitted('pasteFiles')).toBeUndefined()
    expect(wrapper.get('[aria-label="添加附件"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('does not intercept an empty file drop and clears drag state when leave types disappear', async () => {
    const wrapper = mountComposer()
    const composer = wrapper.get('.chat-composer')
    const file = new File(['drag'], 'drag.txt', { type: 'text/plain' })

    composer.element.dispatchEvent(transferEvent('dragenter', [file]))
    await nextTick()
    expect(wrapper.find('[data-testid="composer-drop-overlay"]').exists()).toBe(true)

    composer.element.dispatchEvent(transferEvent('dragleave', [], []))
    await nextTick()
    expect(wrapper.find('[data-testid="composer-drop-overlay"]').exists()).toBe(false)

    const emptyDrop = transferEvent('drop', [], ['Files'])
    composer.element.dispatchEvent(emptyDrop)
    await nextTick()

    expect(emptyDrop.defaultPrevented).toBe(false)
    expect(wrapper.emitted('pasteFiles')).toBeUndefined()
    wrapper.unmount()
  })

  it('shows safe raster previews and falls back to a file state when loading fails', async () => {
    const wrapper = mountComposer({
      files: [
        attachment({
          id: 'image-1',
          filename: 'photo.png',
          extension: 'png',
          contentType: 'image/png',
          previewUrl: 'blob:photo',
        }),
        attachment({
          id: 'svg-1',
          filename: 'unsafe.svg',
          extension: 'svg',
          contentType: 'image/svg+xml',
          previewUrl: 'blob:unsafe',
        }),
      ],
    })

    const preview = wrapper.get('img[alt="photo.png"]')
    expect(preview.attributes('src')).toBe('blob:photo')
    expect(wrapper.find('img[alt="unsafe.svg"]').exists()).toBe(false)

    await preview.trigger('error')
    expect(wrapper.find('img[alt="photo.png"]').exists()).toBe(false)
    expect(wrapper.findAll('.composer-upload-card .item-avatar')).toHaveLength(2)
    wrapper.unmount()
  })
})
