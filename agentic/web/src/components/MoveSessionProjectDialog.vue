<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Check, Folder, FolderOpen, Loader2, Search } from 'lucide-vue-next'
import type { Project, Session } from '@/lib/api/types'
import { useProjectsStore } from '@/stores/projects'
import { useSessionsStore } from '@/stores/sessions'

const props = defineProps<{
  open: boolean
  session: Session
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  moved: [session: Session]
}>()

const projectsStore = useProjectsStore()
const sessionsStore = useSessionsStore()
const query = ref('')
const selectedProjectId = ref<string | null>(null)
const busy = ref(false)
const moveError = ref('')
const searchRef = ref<HTMLInputElement | null>(null)
let previouslyFocusedElement: HTMLElement | null = null

const dialogOpen = computed({
  get: () => props.open,
  set: (value: boolean) => emit('update:open', value),
})
const normalizedQuery = computed(() => query.value.trim().toLocaleLowerCase())
const filteredProjects = computed(() => {
  if (!normalizedQuery.value) return projectsStore.projects
  return projectsStore.projects.filter((project) =>
    project.name.toLocaleLowerCase().includes(normalizedQuery.value),
  )
})
const currentProjectId = computed(() => props.session.project_id ?? null)
const selectionChanged = computed(
  () => selectedProjectId.value !== currentProjectId.value,
)

watch(
  () => [props.open, props.session.session_id, props.session.project_id] as const,
  async ([open]) => {
    if (!open) return
    previouslyFocusedElement =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    query.value = ''
    moveError.value = ''
    selectedProjectId.value = currentProjectId.value
    await nextTick()
    searchRef.value?.focus()
    if (!projectsStore.loaded && !projectsStore.loading) {
      void loadProjects()
    }
  },
  { immediate: true },
)

async function loadProjects(): Promise<void> {
  try {
    await projectsStore.load()
  } catch {
    // Store exposes the retryable error in the dialog.
  }
}

function restoreOpeningFocus(): void {
  previouslyFocusedElement?.focus()
  previouslyFocusedElement = null
}

function selectProject(projectId: string | null): void {
  if (busy.value) return
  selectedProjectId.value = projectId
  moveError.value = ''
}

function isSelected(projectId: string | null): boolean {
  return selectedProjectId.value === projectId
}

function optionLabel(project: Project): string {
  return project.id === currentProjectId.value
    ? `${project.name}（当前）`
    : project.name
}

async function confirmMove(): Promise<void> {
  if (busy.value || !selectionChanged.value) return
  busy.value = true
  moveError.value = ''
  try {
    const updated = await sessionsStore.updateOrganization(
      props.session.session_id,
      { project_id: selectedProjectId.value },
    )
    emit('moved', updated)
    dialogOpen.value = false
  } catch (cause) {
    moveError.value =
      cause instanceof Error ? cause.message : '移动任务失败，请重试'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ElDialog
    v-model="dialogOpen"
    title="移动到项目"
    width="min(420px, calc(100vw - 24px))"
    append-to-body
    align-center
    destroy-on-close
    class="project-dialog move-project-dialog"
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    @opened="searchRef?.focus()"
    @closed="restoreOpeningFocus"
  >
    <form class="project-form" @submit.prevent="confirmMove">
      <label class="project-search-field">
        <Search :size="16" aria-hidden="true" />
        <span class="sr-only">搜索项目</span>
        <input
          ref="searchRef"
          v-model="query"
          type="search"
          autocomplete="off"
          placeholder="搜索项目"
          :disabled="busy"
        />
      </label>

      <div class="project-option-list" role="radiogroup" aria-label="目标项目">
        <button
          type="button"
          class="project-option"
          data-project-id="unassigned"
          role="radio"
          :aria-checked="isSelected(null)"
          :class="{ selected: isSelected(null) }"
          :disabled="busy"
          @click="selectProject(null)"
        >
          <FolderOpen :size="17" aria-hidden="true" />
          <span class="project-option-name">未分组</span>
          <span
            v-if="currentProjectId === null"
            class="project-option-current"
          >
            当前
          </span>
          <Check v-if="isSelected(null)" :size="16" aria-hidden="true" />
        </button>

        <div
          v-if="projectsStore.loading"
          class="project-dialog-state"
          role="status"
        >
          <Loader2 :size="17" class="spin" aria-hidden="true" />
          <span>正在加载项目…</span>
        </div>

        <div
          v-else-if="projectsStore.error"
          class="project-dialog-state error"
          role="alert"
        >
          <span>{{ projectsStore.error }}</span>
          <button
            type="button"
            class="button small"
            data-testid="retry-projects"
            @click="loadProjects"
          >
            重试
          </button>
        </div>

        <template v-else>
          <button
            v-for="project in filteredProjects"
            :key="project.id"
            type="button"
            class="project-option"
            :data-project-id="project.id"
            role="radio"
            :aria-checked="isSelected(project.id)"
            :class="{ selected: isSelected(project.id) }"
            :disabled="busy"
            :title="project.name"
            @click="selectProject(project.id)"
          >
            <Folder :size="17" aria-hidden="true" />
            <span class="project-option-name">{{ optionLabel(project) }}</span>
            <Check
              v-if="isSelected(project.id)"
              :size="16"
              aria-hidden="true"
            />
          </button>
          <div
            v-if="filteredProjects.length === 0"
            class="project-dialog-state"
            role="status"
          >
            <span>
              {{ projectsStore.projects.length ? '没有匹配的项目' : '还没有项目' }}
            </span>
          </div>
        </template>
      </div>

      <p v-if="moveError" class="project-dialog-error" role="alert">
        {{ moveError }}
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
          :disabled="busy || !selectionChanged"
          :aria-busy="busy || undefined"
        >
          <Loader2 v-if="busy" :size="15" class="spin" aria-hidden="true" />
          <span>{{ busy ? '正在移动…' : '确认移动' }}</span>
        </button>
      </footer>
    </form>
  </ElDialog>
</template>
