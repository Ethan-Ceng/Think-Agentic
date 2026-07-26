import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { FilePickerSelection } from '@/lib/composer-attachments'
import ChatInput from './ChatInput.vue'

const mocks = vi.hoisted(() => ({
  uploadFile: vi.fn(),
  previewFile: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@/lib/api/file', () => ({
  fileApi: {
    uploadFile: mocks.uploadFile,
    previewFile: mocks.previewFile,
  },
}))

vi.mock('@/lib/api/skills', () => ({
  skillsApi: { list: vi.fn().mockResolvedValue([]) },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    error: mocks.toastError,
    success: vi.fn(),
    info: vi.fn(),
  }),
}))

vi.mock('./ChatComposer.vue', () => ({
  default: defineComponent({
    name: 'ChatComposer',
    inheritAttrs: false,
    props: {
      modelValue: { type: String, default: '' },
      files: { type: Array, default: () => [] },
      uploading: Boolean,
      sending: Boolean,
      disabled: Boolean,
      isRunning: Boolean,
    },
    emits: [
      'update:modelValue',
      'attach',
      'openFileLibrary',
      'removeFile',
      'retryFile',
      'pasteFiles',
      'send',
      'stop',
      'selectSkill',
      'removeSkill',
    ],
    setup(_, { expose }) {
      expose({ focus: vi.fn() })
      return () => h('div', { class: 'chat-composer-stub' })
    },
  }),
}))

vi.mock('./ChatFilePickerDialog.vue', () => ({
  default: defineComponent({
    name: 'ChatFilePickerDialog',
    props: {
      modelValue: Boolean,
      selectedIds: { type: Array, default: () => [] },
    },
    emits: ['update:modelValue', 'confirm'],
    setup: () => () => h('div', { class: 'chat-file-picker-dialog-stub' }),
  }),
}))

function selection(
  id: string,
  filename = 'notes.pdf',
  mimeType = 'application/pdf',
): FilePickerSelection {
  return {
    id,
    filename,
    extension: filename.split('.').pop() || '',
    size: 128,
    mimeType,
    sourceType: 'user_upload',
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function mountInput(
  sessionId = 'session-1',
  onSend = vi.fn().mockResolvedValue(undefined),
) {
  return mount(ChatInput, {
    props: { sessionId, onSend },
  })
}

function composer(wrapper: ReturnType<typeof mountInput>) {
  return wrapper.getComponent({ name: 'ChatComposer' })
}

function dialog(wrapper: ReturnType<typeof mountInput>) {
  return wrapper.getComponent({ name: 'ChatFilePickerDialog' })
}

describe('ChatInput attachment integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    setActivePinia(createPinia())
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:preview'),
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    })
  })

  it('opens the library, deduplicates selections, and sends IDs without uploading again', async () => {
    const onSend = vi.fn().mockResolvedValue(undefined)
    const wrapper = mountInput('session-1', onSend)

    composer(wrapper).vm.$emit('openFileLibrary')
    await nextTick()
    expect(dialog(wrapper).props('modelValue')).toBe(true)

    const file = selection('library-1')
    dialog(wrapper).vm.$emit('confirm', [file, file])
    await flushPromises()

    expect(composer(wrapper).props('files')).toEqual([
      expect.objectContaining({
        id: 'library-1',
        origin: 'library',
        uploadStatus: 'uploaded',
      }),
    ])
    expect(dialog(wrapper).props('selectedIds')).toEqual(['library-1'])
    expect(mocks.uploadFile).not.toHaveBeenCalled()

    composer(wrapper).vm.$emit('update:modelValue', 'summarize this')
    composer(wrapper).vm.$emit('send')
    await flushPromises()

    expect(onSend).toHaveBeenCalledWith(
      expect.objectContaining({ attachmentIds: ['library-1'] }),
      [{
        id: 'library-1',
        filename: 'notes.pdf',
        extension: 'pdf',
        size: 128,
        contentType: 'application/pdf',
      }],
    )
  })

  it('creates a local image preview and revokes it when the uploaded file is removed', async () => {
    mocks.uploadFile.mockResolvedValue({
      id: 'uploaded-1',
      filename: 'photo.png',
      extension: 'png',
      size: 5,
      content_type: 'image/png',
    })
    vi.mocked(URL.createObjectURL).mockReturnValue('blob:local')
    const wrapper = mountInput()
    const file = new File(['image'], 'photo.png', { type: 'image/png' })

    composer(wrapper).vm.$emit('pasteFiles', [file])
    await flushPromises()

    expect(mocks.uploadFile).toHaveBeenCalledOnce()
    expect(composer(wrapper).props('files')).toEqual([
      expect.objectContaining({
        id: 'uploaded-1',
        previewUrl: 'blob:local',
        origin: 'upload',
      }),
    ])

    composer(wrapper).vm.$emit('removeFile', 'uploaded-1')
    await nextTick()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:local')
    expect(composer(wrapper).props('files')).toEqual([])
  })

  it('loads a library image preview lazily and revokes it on unmount', async () => {
    mocks.previewFile.mockResolvedValue(new Blob(['image'], { type: 'image/png' }))
    vi.mocked(URL.createObjectURL).mockReturnValue('blob:library')
    const wrapper = mountInput()

    dialog(wrapper).vm.$emit(
      'confirm',
      [selection('library-image', 'chart.png', 'image/png')],
    )
    await flushPromises()

    expect(mocks.previewFile).toHaveBeenCalledWith('library-image')
    expect(composer(wrapper).props('files')).toEqual([
      expect.objectContaining({ id: 'library-image', previewUrl: 'blob:library' }),
    ])

    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:library')
  })

  it('ignores a late library preview after the attachment is removed', async () => {
    const preview = deferred<Blob>()
    mocks.previewFile.mockReturnValue(preview.promise)
    const wrapper = mountInput()

    dialog(wrapper).vm.$emit(
      'confirm',
      [selection('library-image', 'chart.png', 'image/png')],
    )
    await nextTick()
    composer(wrapper).vm.$emit('removeFile', 'library-image')
    preview.resolve(new Blob(['late'], { type: 'image/png' }))
    await flushPromises()

    expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(composer(wrapper).props('files')).toEqual([])
  })

  it('revokes local previews and ignores late upload completion after a session switch', async () => {
    const upload = deferred<{
      id: string
      filename: string
      extension: string
      size: number
      content_type: string
    }>()
    mocks.uploadFile.mockReturnValue(upload.promise)
    vi.mocked(URL.createObjectURL).mockReturnValue('blob:session-1')
    const wrapper = mountInput('session-1')

    composer(wrapper).vm.$emit(
      'pasteFiles',
      [new File(['image'], 'photo.png', { type: 'image/png' })],
    )
    await nextTick()
    await wrapper.setProps({ sessionId: 'session-2' })
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:session-1')

    upload.resolve({
      id: 'late-upload',
      filename: 'photo.png',
      extension: 'png',
      size: 5,
      content_type: 'image/png',
    })
    await flushPromises()

    expect(composer(wrapper).props('files')).toEqual([])
  })

  it('keeps the new session attachments when an earlier send finishes late', async () => {
    const send = deferred<void>()
    const onSend = vi.fn().mockReturnValue(send.promise)
    const wrapper = mountInput('session-1', onSend)

    dialog(wrapper).vm.$emit('confirm', [selection('session-1-file')])
    composer(wrapper).vm.$emit('update:modelValue', 'first session')
    composer(wrapper).vm.$emit('send')
    await flushPromises()

    await wrapper.setProps({ sessionId: 'session-2' })
    dialog(wrapper).vm.$emit('confirm', [selection('session-2-file')])
    await nextTick()
    send.resolve()
    await flushPromises()

    expect(composer(wrapper).props('files')).toEqual([
      expect.objectContaining({ id: 'session-2-file' }),
    ])
  })

  it('retains attachments and previews when sending fails', async () => {
    mocks.previewFile.mockResolvedValue(new Blob(['image'], { type: 'image/png' }))
    vi.mocked(URL.createObjectURL).mockReturnValue('blob:retry')
    const onSend = vi.fn().mockRejectedValue(new Error('queue conflict'))
    const wrapper = mountInput('session-1', onSend)

    dialog(wrapper).vm.$emit(
      'confirm',
      [selection('retry-image', 'retry.png', 'image/png')],
    )
    await flushPromises()
    composer(wrapper).vm.$emit('update:modelValue', 'retry later')
    composer(wrapper).vm.$emit('send')
    await flushPromises()

    expect(composer(wrapper).props('files')).toEqual([
      expect.objectContaining({ id: 'retry-image', previewUrl: 'blob:retry' }),
    ])
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
  })
})
