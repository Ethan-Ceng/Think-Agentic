export type SkillSource = 'bundled' | 'personal' | 'marketplace'
export type SkillSelectionMode = 'manual' | 'automatic'
export type SkillScope = 'personal' | 'marketplace'
export type SkillStatus = 'draft' | 'active' | 'archived'
export type SkillVersionStatus = 'draft' | 'published'

export type SkillRef = {
  source: SkillSource
  skill_id?: string | null
  name: string
}

export type SkillManifest = {
  name: string
  description: string
  license?: string | null
  compatibility?: string | null
  metadata?: Record<string, string>
  'allowed-tools'?: string | null
}

export type SkillSummary = {
  id: string
  name: string
  display_name: string
  description: string
  scope: SkillScope
  status: SkillStatus
  enabled: boolean
  auto_invoke: boolean
  current_version_id: string | null
  forked_from_skill_id?: string | null
  forked_from_version_id?: string | null
  updated_at: string
  created_at: string
}

export type SkillVersion = {
  id: string
  skill_id: string
  version: number
  manifest: SkillManifest
  package_sha256: string
  package_size: number
  file_count: number
  status: SkillVersionStatus
  changelog: string
  created_at: string
}

export type SkillDetail = {
  skill: SkillSummary
  version: SkillVersion | null
}

export type PublishedSkill = {
  skill: SkillSummary
  version: SkillVersion
}

export type SkillDraft = {
  draft_id: string
  skill_name: string
  revision: string
}

export type MarketplaceInstallation = {
  pinned_version_id: string
  enabled: boolean
  auto_invoke: boolean
  auto_update: boolean
  installed_at: string
  updated_at: string
}

export type MarketplaceSkill = {
  id: string
  name: string
  display_name: string
  description: string
  latest_version: SkillVersion
  versions: SkillVersion[]
  installation: MarketplaceInstallation | null
  update_available: boolean
}

export type SkillDraftTreeEntry = {
  path: string
  kind: 'file' | 'directory'
  size?: number | null
}

export type SkillDraftTree = {
  tree: SkillDraftTreeEntry[]
  revision: string
}

export type SkillDraftFile = {
  path: string
  content: string
}

export type SkillValidationDiagnostic = {
  file: string
  line: number | null
  column: number | null
  code: string
  message: string
}

export type SkillValidationResult = {
  valid: boolean
  revision: string
  manifest: SkillManifest | null
  diagnostics: SkillValidationDiagnostic[]
}

export type RunSkill = {
  id: string
  run_id: string
  skill_id: string | null
  skill_version_id: string | null
  name: string
  source: SkillSource
  selection_mode: SkillSelectionMode
  content_sha256: string
  confidence: number | null
  reason: string
  sandbox_path: string
  created_at: string
}

export type SendMessageInput = {
  message: string
  attachmentIds: string[]
  skills: SkillRef[]
}
