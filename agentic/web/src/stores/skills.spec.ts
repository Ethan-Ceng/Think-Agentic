import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { skillsApi } from '@/lib/api/skills'
import type { SkillDetail, SkillSummary, SkillValidationResult } from '@/types/skill'
import { useSkillsStore } from './skills'

vi.mock('@/lib/api/skills', () => ({
  skillsApi: {
    list: vi.fn(),
    get: vi.fn(),
    setEnabled: vi.fn(),
    setAutoInvoke: vi.fn(),
    validateDraft: vi.fn(),
  },
}))

const summary: SkillSummary = {
  id: 'skill-1',
  name: 'report-writer',
  display_name: 'Report Writer',
  description: 'Write reports.',
  scope: 'personal',
  status: 'active',
  enabled: true,
  auto_invoke: true,
  current_version_id: 'version-1',
  updated_at: '2026-07-16T00:00:00Z',
  created_at: '2026-07-15T00:00:00Z',
}

const detail: SkillDetail = {
  skill: summary,
  version: {
    id: 'version-1',
    skill_id: 'skill-1',
    version: 1,
    manifest: { name: 'report-writer', description: 'Write reports.' },
    package_sha256: 'a'.repeat(64),
    package_size: 100,
    file_count: 2,
    status: 'published',
    changelog: '',
    created_at: '2026-07-16T00:00:00Z',
  },
}

describe('skills store', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
  })

  it('loads the personal skill list', async () => {
    vi.mocked(skillsApi.list).mockResolvedValue([summary])
    const store = useSkillsStore()

    await store.loadSkills()

    expect(store.skills).toEqual([summary])
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('caches detail requests', async () => {
    vi.mocked(skillsApi.get).mockResolvedValue(detail)
    const store = useSkillsStore()

    expect(await store.loadSkill('skill-1')).toEqual(detail)
    expect(await store.loadSkill('skill-1')).toEqual(detail)
    expect(skillsApi.get).toHaveBeenCalledTimes(1)
  })

  it('rolls back an optimistic enabled update when the backend fails', async () => {
    vi.mocked(skillsApi.list).mockResolvedValue([summary])
    vi.mocked(skillsApi.setEnabled).mockRejectedValue(new Error('offline'))
    const store = useSkillsStore()
    await store.loadSkills()

    await expect(store.setEnabled('skill-1', false)).rejects.toThrow('offline')
    expect(store.skills[0]?.enabled).toBe(true)
  })

  it('updates auto invoke state from the backend response', async () => {
    const updated: SkillDetail = {
      ...detail,
      skill: { ...summary, auto_invoke: false },
    }
    vi.mocked(skillsApi.list).mockResolvedValue([summary])
    vi.mocked(skillsApi.setAutoInvoke).mockResolvedValue(updated)
    const store = useSkillsStore()
    await store.loadSkills()

    await store.setAutoInvoke('skill-1', false)

    expect(store.skills[0]?.auto_invoke).toBe(false)
    expect(store.details['skill-1']).toEqual(updated)
  })

  it('stores validation diagnostics by draft', async () => {
    const validation: SkillValidationResult = {
      valid: false,
      revision: 'b'.repeat(64),
      manifest: null,
      diagnostics: [
        {
          file: 'SKILL.md',
          line: 2,
          column: 1,
          code: 'skill_invalid_manifest',
          message: 'description is required',
        },
      ],
    }
    vi.mocked(skillsApi.validateDraft).mockResolvedValue(validation)
    const store = useSkillsStore()

    await store.validateDraft('draft-1')

    expect(store.validations['draft-1']).toEqual(validation)
  })

  it('clears user-scoped state when the authenticated user changes', async () => {
    vi.mocked(skillsApi.list).mockResolvedValue([summary])
    const store = useSkillsStore()
    store.resetForUser('user-1')
    await store.loadSkills()

    store.resetForUser('user-2')

    expect(store.skills).toEqual([])
    expect(store.details).toEqual({})
    expect(store.validations).toEqual({})
  })
})
