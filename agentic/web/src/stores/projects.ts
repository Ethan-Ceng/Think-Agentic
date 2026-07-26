import { defineStore } from 'pinia'
import { ref } from 'vue'
import { projectApi } from '@/lib/api/project'
import type { Project } from '@/lib/api/types'
import { useSessionsStore } from './sessions'

function sortProjects(projects: Project[]): Project[] {
  return [...projects].sort((left, right) => {
    const createdOrder =
      new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
    if (createdOrder !== 0) return createdOrder
    return right.id.localeCompare(left.id)
  })
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export const useProjectsStore = defineStore('projects', () => {
  const projects = ref<Project[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref<string | null>(null)

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const result = await projectApi.listProjects()
      projects.value = sortProjects(result.projects)
      loaded.value = true
    } catch (cause) {
      loaded.value = false
      error.value = errorMessage(cause, '获取项目列表失败')
      throw cause
    } finally {
      loading.value = false
    }
  }

  async function create(name: string): Promise<Project> {
    const created = await projectApi.createProject({ name: name.trim() })
    projects.value = sortProjects([
      ...projects.value.filter((project) => project.id !== created.id),
      created,
    ])
    return created
  }

  async function rename(projectId: string, name: string): Promise<Project> {
    const updated = await projectApi.renameProject(projectId, {
      name: name.trim(),
    })
    projects.value = sortProjects(
      projects.value.map((project) =>
        project.id === updated.id ? updated : project,
      ),
    )
    return updated
  }

  async function remove(projectId: string): Promise<void> {
    await projectApi.deleteProject(projectId)
    projects.value = projects.value.filter((project) => project.id !== projectId)
    useSessionsStore().unassignProject(projectId)
  }

  function clear(): void {
    projects.value = []
    loading.value = false
    loaded.value = false
    error.value = null
  }

  return {
    projects,
    loading,
    loaded,
    error,
    load,
    create,
    rename,
    remove,
    clear,
  }
})
