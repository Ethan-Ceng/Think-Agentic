import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { skillsApi } from '@/lib/api/skills'
import type {
  PublishedSkill,
  SkillDetail,
  SkillDraft,
  SkillDraftFile,
  SkillDraftTree,
  SkillSummary,
  SkillValidationResult,
} from '@/types/skill'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Skill request failed'
}

export const useSkillsStore = defineStore('skills', () => {
  const skills = ref<SkillSummary[]>([])
  const details = ref<Record<string, SkillDetail>>({})
  const validations = ref<Record<string, SkillValidationResult>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)
  const ownerUserId = ref<string | null>(null)

  const activeSkills = computed(() => skills.value.filter((skill) => skill.status === 'active'))

  function resetForUser(userId: string | null): void {
    if (ownerUserId.value === userId) return
    ownerUserId.value = userId
    skills.value = []
    details.value = {}
    validations.value = {}
    error.value = null
    loading.value = false
  }

  function mergeDetail(detail: SkillDetail): SkillDetail {
    details.value[detail.skill.id] = detail
    const index = skills.value.findIndex((skill) => skill.id === detail.skill.id)
    if (index === -1) skills.value.push(detail.skill)
    else skills.value[index] = detail.skill
    return detail
  }

  async function loadSkills(): Promise<SkillSummary[]> {
    loading.value = true
    error.value = null
    try {
      skills.value = await skillsApi.list()
      return skills.value
    } catch (cause) {
      error.value = errorMessage(cause)
      throw cause
    } finally {
      loading.value = false
    }
  }

  async function loadSkill(skillId: string, force = false): Promise<SkillDetail> {
    if (!force && details.value[skillId]) return details.value[skillId]
    const detail = await skillsApi.get(skillId)
    return mergeDetail(detail)
  }

  async function setEnabled(skillId: string, enabled: boolean): Promise<SkillDetail> {
    const previousSkill = skills.value.find((skill) => skill.id === skillId)
    const previousDetail = details.value[skillId]
    const previousListValue = previousSkill?.enabled
    const previousDetailValue = previousDetail?.skill.enabled
    if (previousSkill) previousSkill.enabled = enabled
    if (previousDetail) previousDetail.skill.enabled = enabled
    try {
      return mergeDetail(await skillsApi.setEnabled(skillId, enabled))
    } catch (cause) {
      if (previousSkill && previousListValue !== undefined) previousSkill.enabled = previousListValue
      if (previousDetail && previousDetailValue !== undefined) {
        previousDetail.skill.enabled = previousDetailValue
      }
      throw cause
    }
  }

  async function setAutoInvoke(skillId: string, enabled: boolean): Promise<SkillDetail> {
    return mergeDetail(await skillsApi.setAutoInvoke(skillId, enabled))
  }

  async function updateSkill(
    skillId: string,
    changes: { display_name?: string; description?: string },
  ): Promise<SkillDetail> {
    return mergeDetail(await skillsApi.update(skillId, changes))
  }

  async function archiveSkill(skillId: string): Promise<void> {
    await skillsApi.archive(skillId)
    skills.value = skills.value.filter((skill) => skill.id !== skillId)
    delete details.value[skillId]
  }

  async function importSkill(
    file: File,
    displayName?: string,
    changelog = '',
  ): Promise<PublishedSkill> {
    const published = await skillsApi.import(file, displayName, changelog)
    mergeDetail(published)
    return published
  }

  async function createDraft(input: {
    name: string
    display_name: string
    description: string
  }): Promise<SkillDraft> {
    return skillsApi.createDraft(input)
  }

  async function getDraftTree(draftId: string): Promise<SkillDraftTree> {
    return skillsApi.getDraftTree(draftId)
  }

  async function readDraftFile(draftId: string, path: string): Promise<SkillDraftFile> {
    return skillsApi.readDraftFile(draftId, path)
  }

  async function writeDraftFile(draftId: string, path: string, content: string): Promise<void> {
    await skillsApi.writeDraftFile(draftId, path, content)
  }

  async function validateDraft(draftId: string): Promise<SkillValidationResult> {
    const result = await skillsApi.validateDraft(draftId)
    validations.value[draftId] = result
    return result
  }

  async function publishDraft(
    draftId: string,
    expectedRevision: string,
    changelog = '',
  ): Promise<PublishedSkill> {
    const published = await skillsApi.publishDraft(draftId, expectedRevision, changelog)
    mergeDetail(published)
    return published
  }

  return {
    skills,
    activeSkills,
    details,
    validations,
    loading,
    error,
    resetForUser,
    loadSkills,
    loadSkill,
    setEnabled,
    setAutoInvoke,
    updateSkill,
    archiveSkill,
    importSkill,
    createDraft,
    getDraftTree,
    readDraftFile,
    writeDraftFile,
    validateDraft,
    publishDraft,
  }
})
