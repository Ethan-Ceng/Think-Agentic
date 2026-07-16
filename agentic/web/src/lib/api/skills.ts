import { del, get, patch, post, put } from './fetch'
import type {
  PublishedSkill,
  MarketplaceSkill,
  SkillDetail,
  SkillDraft,
  SkillDraftFile,
  SkillDraftTree,
  SkillSummary,
  SkillValidationResult,
} from '@/types/skill'

function encodePath(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/')
}

export const skillsApi = {
  list(): Promise<SkillSummary[]> {
    return get('/skills')
  },

  listMarketplace(): Promise<MarketplaceSkill[]> {
    return get('/skills/marketplace')
  },

  getMarketplace(skillId: string): Promise<MarketplaceSkill> {
    return get(`/skills/marketplace/${encodeURIComponent(skillId)}`)
  },

  installMarketplace(skillId: string, versionId?: string): Promise<MarketplaceSkill> {
    return post(`/skills/marketplace/${encodeURIComponent(skillId)}/install`, {
      version_id: versionId,
    })
  },

  updateMarketplace(skillId: string, versionId?: string): Promise<MarketplaceSkill> {
    return post(`/skills/marketplace/${encodeURIComponent(skillId)}/update`, {
      version_id: versionId,
    })
  },

  uninstallMarketplace(skillId: string): Promise<Record<string, never>> {
    return del(`/skills/marketplace/${encodeURIComponent(skillId)}/install`)
  },

  forkMarketplace(skillId: string, versionId?: string): Promise<SkillDraft> {
    return post(`/skills/marketplace/${encodeURIComponent(skillId)}/fork`, {
      version_id: versionId,
    })
  },

  import(file: File, displayName?: string, changelog = ''): Promise<PublishedSkill> {
    const form = new FormData()
    form.append('file', file)
    if (displayName) form.append('display_name', displayName)
    form.append('changelog', changelog)
    return post('/skills/import', form)
  },

  get(skillId: string): Promise<SkillDetail> {
    return get(`/skills/${encodeURIComponent(skillId)}`)
  },

  update(
    skillId: string,
    changes: { display_name?: string; description?: string },
  ): Promise<SkillDetail> {
    return patch(`/skills/${encodeURIComponent(skillId)}`, changes)
  },

  archive(skillId: string): Promise<Record<string, never>> {
    return del(`/skills/${encodeURIComponent(skillId)}`)
  },

  setEnabled(skillId: string, enabled: boolean): Promise<SkillDetail> {
    const action = enabled ? 'enable' : 'disable'
    return post(`/skills/${encodeURIComponent(skillId)}/${action}`)
  },

  setAutoInvoke(skillId: string, enabled: boolean): Promise<SkillDetail> {
    return post(`/skills/${encodeURIComponent(skillId)}/auto-invoke`, { enabled })
  },

  createDraft(input: {
    name: string
    display_name: string
    description: string
  }): Promise<SkillDraft> {
    return post('/skill-drafts', input)
  },

  getDraftTree(draftId: string): Promise<SkillDraftTree> {
    return get(`/skill-drafts/${encodeURIComponent(draftId)}/tree`)
  },

  readDraftFile(draftId: string, path: string): Promise<SkillDraftFile> {
    return get(`/skill-drafts/${encodeURIComponent(draftId)}/files/${encodePath(path)}`)
  },

  writeDraftFile(draftId: string, path: string, content: string): Promise<{ path: string }> {
    return put(`/skill-drafts/${encodeURIComponent(draftId)}/files/${encodePath(path)}`, { content })
  },

  validateDraft(draftId: string): Promise<SkillValidationResult> {
    return post(`/skill-drafts/${encodeURIComponent(draftId)}/validate`)
  },

  publishDraft(draftId: string, expectedRevision: string, changelog = ''): Promise<PublishedSkill> {
    return post(`/skill-drafts/${encodeURIComponent(draftId)}/publish`, {
      expected_revision: expectedRevision,
      changelog,
    })
  },
}
