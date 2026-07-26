import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { projectApi } from '@/lib/api/project'
import { sessionApi } from '@/lib/api/session'
import type { Project, Session } from '@/lib/api/types'
import { useProjectsStore } from './projects'
import { useSessionsStore } from './sessions'

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'project-1',
    name: 'Research',
    created_at: '2026-07-24T10:00:00',
    updated_at: '2026-07-24T10:00:00',
    ...overrides,
  }
}

function session(overrides: Partial<Session> = {}): Session {
  return {
    session_id: 'session-1',
    title: 'Original',
    project_id: 'project-1',
    latest_message: 'latest',
    latest_message_at: '2026-07-24T10:00:00',
    status: 'completed',
    unread_message_count: 0,
    is_pinned: false,
    archived_at: null,
    has_next_message: false,
    ...overrides,
  }
}

describe('projects store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads projects in stable newest-first order and exposes retryable errors', async () => {
    vi.spyOn(projectApi, 'listProjects')
      .mockRejectedValueOnce(new Error('project offline'))
      .mockResolvedValueOnce({
        projects: [
          project({ id: 'older', created_at: '2026-07-23T10:00:00' }),
          project({ id: 'same-b', created_at: '2026-07-24T10:00:00' }),
          project({ id: 'same-a', created_at: '2026-07-24T10:00:00' }),
        ],
      })
    const store = useProjectsStore()

    await expect(store.load()).rejects.toThrow('project offline')
    expect(store.loading).toBe(false)
    expect(store.error).toBe('project offline')

    await store.load()
    expect(store.error).toBeNull()
    expect(store.loaded).toBe(true)
    expect(store.projects.map((item) => item.id)).toEqual([
      'same-b',
      'same-a',
      'older',
    ])
  })

  it('creates and renames with atomic local replacement', async () => {
    const store = useProjectsStore()
    vi.spyOn(projectApi, 'createProject').mockResolvedValue(
      project({ id: 'created', name: 'Created' }),
    )
    vi.spyOn(projectApi, 'renameProject').mockResolvedValue(
      project({ id: 'created', name: 'Renamed' }),
    )

    await store.create('  Created  ')
    expect(projectApi.createProject).toHaveBeenCalledWith({ name: 'Created' })
    expect(store.projects[0].name).toBe('Created')

    await store.rename('created', '  Renamed  ')
    expect(projectApi.renameProject).toHaveBeenCalledWith('created', {
      name: 'Renamed',
    })
    expect(store.projects[0].name).toBe('Renamed')
  })

  it('deletes only after API success and unassigns active and archived sessions', async () => {
    vi.spyOn(projectApi, 'listProjects').mockResolvedValue({
      projects: [project()],
    })
    vi.spyOn(projectApi, 'deleteProject')
      .mockRejectedValueOnce(new Error('delete failed'))
      .mockResolvedValueOnce()
    vi.spyOn(sessionApi, 'getSessions').mockImplementation(async (scope) => ({
      sessions:
        scope === 'archived'
          ? [
              session({
                session_id: 'archived-1',
                archived_at: '2026-07-25T10:00:00',
              }),
            ]
          : [session()],
    }))
    const projectsStore = useProjectsStore()
    const sessionsStore = useSessionsStore()
    await projectsStore.load()
    await sessionsStore.refresh()
    await sessionsStore.loadArchivedSessions()

    await expect(projectsStore.remove('project-1')).rejects.toThrow('delete failed')
    expect(projectsStore.projects).toHaveLength(1)
    expect(sessionsStore.sessions[0].project_id).toBe('project-1')

    await projectsStore.remove('project-1')
    expect(projectsStore.projects).toEqual([])
    expect(sessionsStore.sessions[0].project_id).toBeNull()
    expect(sessionsStore.archivedSessions[0].project_id).toBeNull()
    expect(sessionsStore.sessions[0].latest_message_at).toBe(
      '2026-07-24T10:00:00',
    )
  })

  it('clears all user-scoped state', async () => {
    vi.spyOn(projectApi, 'listProjects').mockResolvedValue({
      projects: [project()],
    })
    const store = useProjectsStore()
    await store.load()

    store.clear()

    expect(store.projects).toEqual([])
    expect(store.error).toBeNull()
    expect(store.loading).toBe(false)
    expect(store.loaded).toBe(false)
  })
})
