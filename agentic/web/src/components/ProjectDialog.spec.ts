import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { projectApi } from '@/lib/api/project'
import { ApiError } from '@/lib/api/fetch'
import ProjectDialog from './ProjectDialog.vue'

const DialogStub = defineComponent({
  props: {
    modelValue: Boolean,
    title: String,
  },
  emits: ['update:modelValue', 'opened', 'closed'],
  template:
    '<section v-if="modelValue" role="dialog" @keydown.esc="$emit(\'update:modelValue\', false); $emit(\'closed\')"><h2>{{ title }}</h2><button aria-label="关闭测试弹窗" @click="$emit(\'update:modelValue\', false); $emit(\'closed\')">Close</button><slot /><slot name="footer" /></section>',
})

function mountDialog(props: Record<string, unknown>) {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(ProjectDialog, {
    props: { open: true, ...props },
    global: {
      plugins: [pinia],
      stubs: { ElDialog: DialogStub },
    },
  })
}

describe('ProjectDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('trims a create name, prevents duplicate submits, and closes on success', async () => {
    let resolveCreate: ((value: {
      id: string
      name: string
      created_at: string
      updated_at: string
    }) => void) | undefined
    vi.spyOn(projectApi, 'createProject').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve
        }),
    )
    const wrapper = mountDialog({ mode: 'create' })

    await wrapper.get('input[name="project-name"]').setValue('  Research  ')
    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit')

    expect(projectApi.createProject).toHaveBeenCalledTimes(1)
    expect(projectApi.createProject).toHaveBeenCalledWith({ name: 'Research' })
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()

    resolveCreate?.({
      id: 'project-1',
      name: 'Research',
      created_at: '2026-07-26T10:00:00',
      updated_at: '2026-07-26T10:00:00',
    })
    await flushPromises()

    expect(wrapper.emitted('saved')?.[0]?.[0]).toMatchObject({
      id: 'project-1',
      name: 'Research',
    })
    expect(wrapper.emitted('update:open')).toContainEqual([false])
  })

  it('keeps the entered name and maps duplicate conflict without closing', async () => {
    vi.spyOn(projectApi, 'createProject').mockRejectedValue(
      new ApiError(409, '项目名称已存在'),
    )
    const wrapper = mountDialog({ mode: 'create' })

    await wrapper.get('input[name="project-name"]').setValue('Research')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('已存在同名项目')
    expect(
      (wrapper.get('input[name="project-name"]').element as HTMLInputElement).value,
    ).toBe('Research')
    expect(wrapper.emitted('update:open')).toBeUndefined()
  })

  it('uses the current name when renaming', async () => {
    vi.spyOn(projectApi, 'renameProject').mockResolvedValue({
      id: 'project-1',
      name: 'Renamed',
      created_at: '2026-07-26T10:00:00',
      updated_at: '2026-07-26T11:00:00',
    })
    const wrapper = mountDialog({
      mode: 'rename',
      project: {
        id: 'project-1',
        name: 'Research',
        created_at: '2026-07-26T10:00:00',
        updated_at: '2026-07-26T10:00:00',
      },
    })

    const input = wrapper.get('input[name="project-name"]')
    expect((input.element as HTMLInputElement).value).toBe('Research')
    await input.setValue(' Renamed ')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(projectApi.renameProject).toHaveBeenCalledWith('project-1', {
      name: 'Renamed',
    })
  })

  it('returns focus to the opening control after Escape', async () => {
    const Host = defineComponent({
      components: { ProjectDialog },
      setup() {
        return {
          open: ref(false),
          project: {
            id: 'project-1',
            name: 'Research',
            created_at: '2026-07-26T10:00:00',
            updated_at: '2026-07-26T10:00:00',
          },
        }
      },
      template:
        '<button id="project-opener" @click="open = true">Open</button><ProjectDialog v-model:open="open" mode="rename" :project="project" />',
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(Host, {
      attachTo: document.body,
      global: { plugins: [pinia], stubs: { ElDialog: DialogStub } },
    })
    const opener = wrapper.get('#project-opener')
    ;(opener.element as HTMLButtonElement).focus()
    await opener.trigger('click')
    await flushPromises()

    await wrapper.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(document.activeElement).toBe(opener.element)
    wrapper.unmount()
  })
})
