<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { FolderPlus, Loader2 } from 'lucide-vue-next'
import { ApiError } from '@/lib/api/fetch'
import type { Project } from '@/lib/api/types'
import { useProjectsStore } from '@/stores/projects'

const props = withDefaults(
  defineProps<{
    open: boolean
    mode?: 'create' | 'rename'
    project?: Project | null
  }>(),
  {
    mode: 'create',
    project: null,
  },
)

const emit = defineEmits<{
  'update:open': [value: boolean]
  saved: [project: Project]
}>()

const projectsStore = useProjectsStore()
const name = ref('')
const busy = ref(false)
const error = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
let previouslyFocusedElement: HTMLElement | null = null

const dialogOpen = computed({
  get: () => props.open,
  set: (value: boolean) => emit('update:open', value),
})
const dialogTitle = computed(() =>
  props.mode === 'rename' ? '重命名项目' : '新建项目',
)
const submitLabel = computed(() =>
  props.mode === 'rename' ? '保存名称' : '创建项目',
)
const normalizedName = computed(() => name.value.trim())
const canSubmit = computed(
  () => !busy.value && normalizedName.value.length > 0,
)

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    previouslyFocusedElement =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    name.value = props.mode === 'rename' ? props.project?.name ?? '' : ''
    error.value = ''
    await nextTick()
    inputRef.value?.focus()
  },
  { immediate: true },
)

function restoreOpeningFocus(): void {
  previouslyFocusedElement?.focus()
  previouslyFocusedElement = null
}

function mapError(cause: unknown): string {
  if (cause instanceof ApiError && cause.code === 409) {
    return '已存在同名项目，请换一个名称'
  }
  return cause instanceof Error ? cause.message : '保存项目失败，请重试'
}

async function submit(): Promise<void> {
  if (busy.value) return
  if (!normalizedName.value) {
    error.value = '请输入项目名称'
    return
  }

  busy.value = true
  error.value = ''
  try {
    const saved =
      props.mode === 'rename' && props.project
        ? await projectsStore.rename(props.project.id, normalizedName.value)
        : await projectsStore.create(normalizedName.value)
    emit('saved', saved)
    dialogOpen.value = false
  } catch (cause) {
    error.value = mapError(cause)
    await nextTick()
    inputRef.value?.focus()
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ElDialog
    v-model="dialogOpen"
    :title="dialogTitle"
    width="min(390px, calc(100vw - 24px))"
    append-to-body
    align-center
    destroy-on-close
    class="project-dialog"
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    @opened="inputRef?.focus()"
    @closed="restoreOpeningFocus"
  >
    <form class="project-form" @submit.prevent="submit">
      <div class="project-dialog-intro">
        <span class="project-dialog-icon" aria-hidden="true">
          <FolderPlus :size="18" />
        </span>
        <p>项目只用于整理任务，不会改变对话上下文。</p>
      </div>

      <label class="project-name-field">
        <span>项目名称</span>
        <input
          ref="inputRef"
          v-model="name"
          name="project-name"
          type="text"
          maxlength="100"
          autocomplete="off"
          :disabled="busy"
          aria-describedby="project-name-hint project-dialog-error"
          placeholder="例如：产品发布"
        />
      </label>
      <div id="project-name-hint" class="project-field-hint">
        {{ normalizedName.length }}/100
      </div>

      <p
        v-if="error"
        id="project-dialog-error"
        class="project-dialog-error"
        role="alert"
      >
        {{ error }}
      </p>

      <footer class="project-dialog-actions">
        <button
          type="button"
          class="button"
          :disabled="busy"
          @click="dialogOpen = false"
        >
          取消
        </button>
        <button
          type="submit"
          class="button primary"
          :disabled="!canSubmit"
          :aria-busy="busy || undefined"
        >
          <Loader2 v-if="busy" :size="15" class="spin" aria-hidden="true" />
          <span>{{ busy ? '正在保存…' : submitLabel }}</span>
        </button>
      </footer>
    </form>
  </ElDialog>
</template>
