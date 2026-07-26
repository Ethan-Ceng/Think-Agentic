import { del, get, patch, post } from './fetch'
import type { Project, ProjectNameParams, ProjectsData } from './types'

export const projectApi = {
  listProjects: (): Promise<ProjectsData> => {
    return get<ProjectsData>('/projects')
  },

  createProject: (params: ProjectNameParams): Promise<Project> => {
    return post<Project>('/projects', params)
  },

  renameProject: (
    projectId: string,
    params: ProjectNameParams,
  ): Promise<Project> => {
    return patch<Project>(`/projects/${projectId}`, params)
  },

  deleteProject: (projectId: string): Promise<void> => {
    return del<void>(`/projects/${projectId}`)
  },
}
