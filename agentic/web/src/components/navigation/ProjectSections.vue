<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'
import {
  Archive,
  ChevronDown,
  ChevronRight,
  Folder,
  FolderOpen,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import ArchivedSessionsDialog from '@/components/ArchivedSessionsDialog.vue'
import MoveSessionProjectDialog from '@/components/MoveSessionProjectDialog.vue'
import ProjectDialog from '@/components/ProjectDialog.vue'
import SessionList from '@/components/SessionList.vue'
import { useSidebar } from '@/composables/useSidebar'
import { useToast } from '@/composables/useToast'
import type { Project, Session } from '@/lib/api/types'
import { useProjectsStore } from '@/stores/projects'
import { useSessionsStore } from '@/stores/sessions'

const EXPANSION_STORAGE_KEY = 'agentic.projects.expanded'
const UNASSIGNED_KEY = 'unassigned'

withDefaults(
  defineProps<{
    query?: string
  }>(),
  {
    query: '',
  },
)

const router = useRouter()
const sidebar = useSidebar()
const toast = useToast()
const projectsStore = useProjectsStore()
const sessionsStore = useSessionsStore()
const storedExpansion = window.localStorage.getItem(EXPANSION_STORAGE_KEY)
let hasStoredExpansion = storedExpansion !== null
const expandedIds = ref(new Set<string>(readExpandedIds(storedExpansion)))
const projectDialogOpen = ref(false)
const projectDialogMode = ref<'create' | 'rename'>('create')
const selectedProject = ref<Project | null>(null)
const moveDialogOpen = ref(false)
const moveTarget = ref<Session | null>(null)
const archivedDialogOpen = ref(false)

const knownProjectIds = computed(
  () => new Set(projectsStore.projects.map((project) => project.id)),
)
const projectGroups = computed(() =>
  projectsStore.projects.map((project) => ({
    project,
    sessions: sessionsStore.sessions.filter(
      (session) => session.project_id === project.id,
    ),
  })),
)
const unassignedSessions = computed(() =>
  sessionsStore.sessions.filter(
    (session) =>
      session.project_id === null ||
      !knownProjectIds.value.has(session.project_id),
  ),
)
const safeFallbackActive = computed(
  () => projectsStore.loading || Boolean(projectsStore.error),
)

watch(
  () =>
    [
      projectsStore.loaded,
      projectsStore.projects.map((project) => project.id),
    ] as const,
  ([loaded, projectIds]) => {
    if (!loaded) return
    const validIds = new Set([...projectIds, UNASSIGNED_KEY])
    if (!hasStoredExpansion) {
      expandedIds.value = new Set(validIds)
      hasStoredExpansion = true
    } else {
      expandedIds.value = new Set(
        [...expandedIds.value].filter((id) => validIds.has(id)),
      )
    }
    saveExpandedIds()
  },
  { immediate: true },
)

function readExpandedIds(raw: string | null): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === 'string')
      : []
  } catch {
    return []
  }
}

function saveExpandedIds(): void {
  window.localStorage.setItem(
    EXPANSION_STORAGE_KEY,
    JSON.stringify([...expandedIds.value]),
  )
}

function isExpanded(id: string): boolean {
  return expandedIds.value.has(id)
}

function toggleExpanded(id: string): void {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
  saveExpandedIds()
}

function openCreateDialog(): void {
  projectDialogMode.value = 'create'
  selectedProject.value = null
  projectDialogOpen.value = true
}

function openRenameDialog(project: Project): void {
  projectDialogMode.value = 'rename'
  selectedProject.value = project
  projectDialogOpen.value = true
}

function handleProjectSaved(project: Project): void {
  const next = new Set(expandedIds.value)
  next.add(project.id)
  expandedIds.value = next
  saveExpandedIds()
}

function startProjectTask(project: Project): void {
  void router.push({ path: '/', query: { project: project.id } })
  if (window.innerWidth <= 900) sidebar.close()
}

async function requestProjectDelete(project: Project): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '项目内任务将移到未分组且不会删除，运行状态和聊天内容都将保留。',
      `删除项目「${project.name}」吗？`,
      {
        confirmButtonText: '删除项目',
        cancelButtonText: '取消',
        type: 'warning',
        distinguishCancelAndClose: true,
      },
    )
  } catch {
    return
  }

  try {
    await projectsStore.remove(project.id)
    toast.success(`已删除项目「${project.name}」，任务已移到未分组`)
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '删除项目失败，请重试')
  }
}

function handleProjectCommand(command: string | number | object, project: Project) {
  if (command === 'create-task') startProjectTask(project)
  else if (command === 'rename') openRenameDialog(project)
  else if (command === 'delete') void requestProjectDelete(project)
}

function openMoveDialog(session: Session): void {
  moveTarget.value = session
  moveDialogOpen.value = true
}

function handleMoved(session: Session): void {
  toast.success(
    session.project_id
      ? '任务已移动到目标项目'
      : '任务已移动到未分组',
  )
}

async function retryProjects(): Promise<void> {
  try {
    await projectsStore.load()
  } catch {
    // Store retains the safe fallback and retryable error.
  }
}
</script>

<template>
  <div class="project-sections">
    <div class="sidebar-section-heading project-section-heading">
      <span>项目</span>
      <div class="project-heading-actions">
        <span class="sidebar-status-dot" title="会话流已连接" />
        <button
          type="button"
          class="icon-button subtle tiny"
          data-testid="create-project"
          aria-label="新建项目"
          title="新建项目"
          @click="openCreateDialog"
        >
          <Plus :size="15" />
        </button>
      </div>
    </div>

    <section
      v-if="safeFallbackActive"
      class="project-section project-safe-fallback expanded"
      data-project-section="safe-fallback"
    >
      <div
        v-if="projectsStore.error"
        class="project-load-state"
        role="alert"
      >
        <span>项目加载失败：{{ projectsStore.error }}</span>
        <button type="button" class="link-button" @click="retryProjects">
          重试
        </button>
      </div>
      <div v-else class="project-load-state" role="status">
        正在加载项目，任务暂时显示在安全列表中…
      </div>
      <SessionList
        :items="sessionsStore.sessions"
        query=""
        flat
        :show-empty="true"
        :show-archived-entry="false"
        @move="openMoveDialog"
      />
    </section>

    <template v-else>
      <section
        v-for="group in projectGroups"
        :key="group.project.id"
        class="project-section"
        :class="{ expanded: isExpanded(group.project.id) }"
        :data-project-section="group.project.id"
      >
        <div class="project-row">
          <button
            type="button"
            class="project-row-main"
            :aria-expanded="isExpanded(group.project.id)"
            :title="group.project.name"
            @click="toggleExpanded(group.project.id)"
          >
            <ChevronDown
              v-if="isExpanded(group.project.id)"
              :size="14"
              aria-hidden="true"
            />
            <ChevronRight v-else :size="14" aria-hidden="true" />
            <FolderOpen
              v-if="isExpanded(group.project.id)"
              :size="16"
              aria-hidden="true"
            />
            <Folder v-else :size="16" aria-hidden="true" />
            <span class="project-row-name">{{ group.project.name }}</span>
            <span class="project-row-count">{{ group.sessions.length }}</span>
          </button>
          <ElDropdown
            trigger="click"
            placement="bottom-end"
            teleported
            popper-class="project-action-dropdown"
            @command="handleProjectCommand($event, group.project)"
          >
            <button
              type="button"
              class="icon-button subtle tiny project-menu-button"
              :aria-label="`项目操作：${group.project.name}`"
              @click.stop
            >
              <MoreHorizontal :size="15" />
            </button>
            <template #dropdown>
              <ElDropdownMenu>
                <ElDropdownItem command="create-task">
                  <Plus :size="14" />
                  <span>在此项目中新建任务</span>
                </ElDropdownItem>
                <ElDropdownItem command="rename">
                  <Pencil :size="14" />
                  <span>重命名</span>
                </ElDropdownItem>
                <ElDropdownItem command="delete" class="danger">
                  <Trash2 :size="14" />
                  <span>删除项目</span>
                </ElDropdownItem>
              </ElDropdownMenu>
            </template>
          </ElDropdown>
        </div>

        <div v-if="isExpanded(group.project.id)" class="project-session-list">
          <SessionList
            v-if="group.sessions.length"
            :items="group.sessions"
            :query="query"
            flat
            :show-empty="false"
            :show-archived-entry="false"
            @move="openMoveDialog"
          />
          <div v-else class="project-empty-state">
            <span>暂无任务</span>
            <button
              type="button"
              class="link-button"
              :data-testid="`create-task-${group.project.id}`"
              @click="startProjectTask(group.project)"
            >
              新建任务
            </button>
          </div>
        </div>
      </section>

      <section
        class="project-section"
        :class="{ expanded: isExpanded(UNASSIGNED_KEY) }"
        data-project-section="unassigned"
      >
        <div class="project-row">
          <button
            type="button"
            class="project-row-main"
            :aria-expanded="isExpanded(UNASSIGNED_KEY)"
            @click="toggleExpanded(UNASSIGNED_KEY)"
          >
            <ChevronDown
              v-if="isExpanded(UNASSIGNED_KEY)"
              :size="14"
              aria-hidden="true"
            />
            <ChevronRight v-else :size="14" aria-hidden="true" />
            <FolderOpen
              v-if="isExpanded(UNASSIGNED_KEY)"
              :size="16"
              aria-hidden="true"
            />
            <Folder v-else :size="16" aria-hidden="true" />
            <span class="project-row-name">未分组</span>
            <span class="project-row-count">{{ unassignedSessions.length }}</span>
          </button>
        </div>
        <div v-if="isExpanded(UNASSIGNED_KEY)" class="project-session-list">
          <SessionList
            :items="unassignedSessions"
            :query="query"
            flat
            :show-empty="true"
            :show-archived-entry="false"
            @move="openMoveDialog"
          />
        </div>
      </section>
    </template>

    <button
      type="button"
      class="archived-sessions-entry project-archive-entry"
      @click="archivedDialogOpen = true"
    >
      <Archive :size="14" />
      查看已归档任务
    </button>
  </div>

  <ProjectDialog
    v-model:open="projectDialogOpen"
    :mode="projectDialogMode"
    :project="selectedProject"
    @saved="handleProjectSaved"
  />
  <MoveSessionProjectDialog
    v-if="moveTarget"
    v-model:open="moveDialogOpen"
    :session="moveTarget"
    @moved="handleMoved"
  />
  <ArchivedSessionsDialog v-model:open="archivedDialogOpen" />
</template>
