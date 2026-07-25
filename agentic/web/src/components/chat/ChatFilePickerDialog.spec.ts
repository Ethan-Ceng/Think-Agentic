import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fileApi } from '@/lib/api/file'
import type { ManagedFile, ManagedFilesData } from '@/lib/api/types'
import ChatFilePickerDialog from './ChatFilePickerDialog.vue'

const DialogStub = defineComponent({
  props: {
    modelValue: Boolean,
    title: String,
  },
  emits: ['update:modelValue', 'closed'],
  template:
    '<section v-if="modelValue"><h2>{{ title }}</h2><button aria-label="关闭文件选择器" @click="$emit(\'update:modelValue\', false); $emit(\'closed\')">Close</button><slot /><slot name="footer" /></section>',
})

const PaginationStub = defineComponent({
  props: {
    currentPage: { type: Number, default: 1 },
    pageSize: { type: Number, default: 20 },
    total: { type: Number, default: 0 },
  },
  emits: ['update:currentPage', 'currentChange'],
  template:
    '<button v-if="total > pageSize" aria-label="下一页" @click="$emit(\'update:currentPage\', currentPage + 1); $emit(\'currentChange\', currentPage + 1)">Next</button>',
})

function managedFile(overrides: Partial<ManagedFile> = {}): ManagedFile {
  return {
    id: 'file-1',
    parent_id: null,
    type: 'file',
    name: 'report.pdf',
    filename: 'report.pdf',
    extension: 'pdf',
    mime_type: 'application/pdf',
    storage_provider: 'local',
    source_type: 'user_upload',
    status: 'available',
    size: 1024,
    preview_url: '/api/files/file-1/preview?token=secret',
    download_url: '/api/files/file-1/download?token=secret',
    created_at: 1,
    updated_at: 2,
    ...overrides,
  }
}

function folder(id: string, name: string, parentId: string | null = null): ManagedFile {
  return managedFile({
    id,
    parent_id: parentId,
    type: 'folder',
    name,
    filename: name,
    extension: '',
    mime_type: '',
    size: 0,
    preview_url: '',
    download_url: '',
  })
}

function page(
  list: ManagedFile[],
  currentPage = 1,
  totalRecord = list.length,
  pageSize = 20,
): ManagedFilesData {
  return {
    list,
    paginator: {
      current_page: currentPage,
      page_size: pageSize,
      total_page: totalRecord ? Math.ceil(totalRecord / pageSize) : 0,
      total_record: totalRecord,
    },
  }
}

function mountDialog(
  props: { modelValue?: boolean; selectedIds?: string[] } = {},
) {
  return mount(ChatFilePickerDialog, {
    attachTo: document.body,
    props: {
      modelValue: props.modelValue ?? true,
      selectedIds: props.selectedIds ?? [],
    },
    global: {
      stubs: {
        ElDialog: DialogStub,
        ElPagination: PaginationStub,
      },
    },
  })
}

describe('ChatFilePickerDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('loads the root, protects existing ids, and emits an exact safe selection', async () => {
    vi.spyOn(fileApi, 'listFiles').mockResolvedValue(
      page([
        managedFile(),
        managedFile({
          id: 'file-2',
          name: 'diagram.png',
          filename: 'diagram.png',
          extension: '.PNG',
          mime_type: 'image/png',
          source_type: 'agent_generated',
          size: 128,
        }),
      ]),
    )

    const wrapper = mountDialog({ selectedIds: ['file-1'] })
    await flushPromises()

    expect(fileApi.listFiles).toHaveBeenCalledWith({
      parent_id: undefined,
      search_word: undefined,
      file_kind: 'all',
      source_type: 'all',
      current_page: 1,
      page_size: 20,
    })
    expect(wrapper.get('[aria-label="选择文件：report.pdf"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('已添加')

    await wrapper.get('[aria-label="选择文件：diagram.png"]').setValue(true)
    await wrapper.get('[aria-label="添加 1 个文件"]').trigger('click')

    expect(wrapper.emitted('confirm')).toEqual([
      [[{
        id: 'file-2',
        filename: 'diagram.png',
        extension: 'png',
        size: 128,
        mimeType: 'image/png',
        sourceType: 'agent_generated',
      }]],
    ])
    expect(JSON.stringify(wrapper.emitted('confirm'))).not.toContain('secret')
    expect(wrapper.emitted('update:modelValue')).toContainEqual([false])
  })

  it('navigates folders and applies current-directory query, type, source, and page', async () => {
    const listFiles = vi.spyOn(fileApi, 'listFiles')
      .mockResolvedValueOnce(page([folder('folder-1', 'Research')]))
      .mockResolvedValueOnce(page([
        managedFile({
          id: 'nested-1',
          parent_id: 'folder-1',
          name: 'notes.md',
          filename: 'notes.md',
          extension: 'md',
          mime_type: 'text/markdown',
        }),
      ]))
      .mockResolvedValue(page([], 2, 21))

    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[aria-label="打开文件夹：Research"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('全部文件')
    expect(wrapper.text()).toContain('Research')
    expect(listFiles).toHaveBeenLastCalledWith(expect.objectContaining({
      parent_id: 'folder-1',
      current_page: 1,
    }))

    vi.useFakeTimers()
    await wrapper.get('[aria-label="搜索当前目录"]').setValue('diagram')
    await wrapper.get('[aria-label="文件类型"]').setValue('image')
    await wrapper.get('[aria-label="文件来源"]').setValue('agent_generated')
    await vi.advanceTimersByTimeAsync(320)
    await flushPromises()

    expect(listFiles).toHaveBeenLastCalledWith({
      parent_id: 'folder-1',
      search_word: 'diagram',
      file_kind: 'image',
      source_type: 'agent_generated',
      current_page: 1,
      page_size: 20,
    })
  })

  it('preserves selections across folders and pagination without duplicates', async () => {
    vi.spyOn(fileApi, 'listFiles')
      .mockResolvedValueOnce(page([
        managedFile({ id: 'file-a', name: 'a.txt', filename: 'a.txt' }),
        folder('folder-1', 'Folder'),
      ], 1, 21))
      .mockResolvedValueOnce(page([
        managedFile({
          id: 'file-b',
          parent_id: 'folder-1',
          name: 'b.txt',
          filename: 'b.txt',
        }),
      ]))

    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[aria-label="选择文件：a.txt"]').setValue(true)
    await wrapper.get('[aria-label="打开文件夹：Folder"]').trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="选择文件：b.txt"]').setValue(true)

    expect(wrapper.find('[aria-label="添加 2 个文件"]').exists()).toBe(true)
    await wrapper.get('[aria-label="添加 2 个文件"]').trigger('click')

    expect(
      (wrapper.emitted('confirm')?.[0]?.[0] as Array<{ id: string }>).map((file) => file.id),
    ).toEqual(['file-a', 'file-b'])
  })

  it('preserves first-page selections when moving to the next page', async () => {
    vi.spyOn(fileApi, 'listFiles')
      .mockResolvedValueOnce(page([
        managedFile({ id: 'page-1', name: 'first.txt', filename: 'first.txt' }),
      ], 1, 21))
      .mockResolvedValueOnce(page([
        managedFile({ id: 'page-2', name: 'second.txt', filename: 'second.txt' }),
      ], 2, 21))

    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[aria-label="选择文件：first.txt"]').setValue(true)
    await wrapper.get('[aria-label="下一页"]').trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="选择文件：second.txt"]').setValue(true)
    await wrapper.get('[aria-label="添加 2 个文件"]').trigger('click')

    expect(
      (wrapper.emitted('confirm')?.[0]?.[0] as Array<{ id: string }>).map((file) => file.id),
    ).toEqual(['page-1', 'page-2'])
  })

  it('keeps the dialog open on load failure and retries', async () => {
    const listFiles = vi.spyOn(fileApi, 'listFiles')
      .mockRejectedValueOnce(new Error('files offline'))
      .mockResolvedValueOnce(page([managedFile()]))

    const wrapper = mountDialog()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('files offline')
    await wrapper.get('[aria-label="重试加载文件"]').trigger('click')
    await flushPromises()

    expect(listFiles).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('report.pdf')
  })

  it('ignores a stale search response that resolves after the latest query', async () => {
    vi.useFakeTimers()
    let resolveOld!: (value: ManagedFilesData) => void
    let resolveNew!: (value: ManagedFilesData) => void
    const oldRequest = new Promise<ManagedFilesData>((resolve) => { resolveOld = resolve })
    const newRequest = new Promise<ManagedFilesData>((resolve) => { resolveNew = resolve })
    vi.spyOn(fileApi, 'listFiles')
      .mockResolvedValueOnce(page([]))
      .mockReturnValueOnce(oldRequest)
      .mockReturnValueOnce(newRequest)

    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[aria-label="搜索当前目录"]').setValue('old')
    await vi.advanceTimersByTimeAsync(320)
    await wrapper.get('[aria-label="搜索当前目录"]').setValue('new')
    await vi.advanceTimersByTimeAsync(320)

    resolveNew(page([managedFile({ id: 'new', name: 'new.txt', filename: 'new.txt' })]))
    await flushPromises()
    resolveOld(page([managedFile({ id: 'old', name: 'old.txt', filename: 'old.txt' })]))
    await flushPromises()

    expect(wrapper.text()).toContain('new.txt')
    expect(wrapper.text()).not.toContain('old.txt')
  })

  it('cancels without changing attachments and restores focus to the opener', async () => {
    vi.spyOn(fileApi, 'listFiles').mockResolvedValue(page([managedFile()]))
    const Host = defineComponent({
      components: { ChatFilePickerDialog },
      setup() {
        return { open: ref(false) }
      },
      template:
        '<button id="file-picker-opener" @click="open = true">Open</button><ChatFilePickerDialog v-model="open" :selected-ids="[]" />',
    })
    const wrapper = mount(Host, {
      attachTo: document.body,
      global: {
        stubs: {
          ElDialog: DialogStub,
          ElPagination: PaginationStub,
        },
      },
    })
    const opener = wrapper.get('#file-picker-opener')
    ;(opener.element as HTMLButtonElement).focus()
    await opener.trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="选择文件：report.pdf"]').setValue(true)
    await wrapper.get('[aria-label="取消选择文件"]').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(ChatFilePickerDialog).emitted('confirm')).toBeUndefined()
    expect(document.activeElement).toBe(opener.element)

    await opener.trigger('click')
    await flushPromises()
    expect(wrapper.get('[aria-label="添加文件"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
