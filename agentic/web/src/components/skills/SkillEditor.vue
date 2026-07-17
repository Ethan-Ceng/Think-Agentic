<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import SkillFileTree from './SkillFileTree.vue'
import SkillValidationPanel from './SkillValidationPanel.vue'
import { useSkillsStore } from '@/stores/skills'
import type {
  PublishedSkill,
  SkillDraftTreeEntry,
  SkillValidationResult,
} from '@/types/skill'

const props = withDefaults(defineProps<{ draftId: string; handoff?: boolean }>(), {
  handoff: false,
})
const emit = defineEmits<{ published: [skill: PublishedSkill] }>()
const store = useSkillsStore()

const entries = ref<SkillDraftTreeEntry[]>([])
const activePath = ref('')
const content = ref('')
const savedContent = ref('')
const validation = ref<SkillValidationResult | null>(null)
const loading = ref(true)
const saving = ref(false)
const validating = ref(false)
const publishing = ref(false)
const error = ref<string | null>(null)
const changelog = ref('')
const dirty = computed(() => content.value !== savedContent.value)
const canPublish = computed(() => validation.value?.valid === true && !dirty.value && !publishing.value)

function message(cause: unknown): string {
  return cause instanceof Error ? cause.message : '操作失败'
}

async function loadTree(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const result = await store.getDraftTree(props.draftId)
    entries.value = result.tree
    const preferred = result.tree.find((entry) => entry.path === 'SKILL.md' && entry.kind === 'file')
    const firstFile = result.tree.find((entry) => entry.kind === 'file')
    if (preferred || firstFile) await selectFile((preferred ?? firstFile)!.path)
  } catch (cause) {
    error.value = message(cause)
  } finally {
    loading.value = false
  }
}

async function selectFile(path: string): Promise<void> {
  if (path === activePath.value) return
  error.value = null
  try {
    const file = await store.readDraftFile(props.draftId, path)
    activePath.value = file.path
    content.value = file.content
    savedContent.value = file.content
  } catch (cause) {
    error.value = message(cause)
  }
}

async function save(): Promise<void> {
  if (!activePath.value || !dirty.value) return
  saving.value = true
  error.value = null
  try {
    await store.writeDraftFile(props.draftId, activePath.value, content.value)
    savedContent.value = content.value
    validation.value = null
  } catch (cause) {
    error.value = message(cause)
  } finally {
    saving.value = false
  }
}

async function validate(): Promise<void> {
  if (dirty.value) await save()
  validating.value = true
  error.value = null
  try {
    validation.value = await store.validateDraft(props.draftId)
  } catch (cause) {
    error.value = message(cause)
  } finally {
    validating.value = false
  }
}

async function publish(): Promise<void> {
  if (!validation.value?.valid) return
  publishing.value = true
  error.value = null
  try {
    const published = await store.publishDraft(
      props.draftId,
      validation.value.revision,
      changelog.value,
    )
    emit('published', published)
  } catch (cause) {
    error.value = message(cause)
  } finally {
    publishing.value = false
  }
}

watch(() => props.draftId, () => void loadTree())
onMounted(() => void loadTree())
</script>

<template>
  <section class="skill-editor">
    <p v-if="handoff" class="creator-handoff">AI 已交接此草稿。请检查文件变更并重新校验；只有你可以点击发布。</p>
    <header class="skill-editor-toolbar">
      <strong data-testid="active-path">{{ activePath || '未选择文件' }}</strong>
      <span v-if="dirty" data-testid="dirty-indicator">未保存</span>
      <button data-testid="save-skill-file" type="button" :disabled="!dirty || saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
      <button data-testid="validate-skill" type="button" :disabled="validating" @click="validate">{{ validating ? '校验中…' : '校验' }}</button>
      <input v-model="changelog" type="text" placeholder="版本说明（可选）">
      <button data-testid="publish-skill" type="button" :disabled="!canPublish" @click="publish">{{ publishing ? '发布中…' : '发布' }}</button>
    </header>
    <p v-if="error" class="skill-editor-error">{{ error }}</p>
    <div v-if="loading" class="page-state">正在打开工作区…</div>
    <div v-else class="skill-editor-workspace">
      <SkillFileTree :entries="entries" :active-path="activePath" @select="selectFile" />
      <textarea
        v-model="content"
        data-testid="skill-content"
        :aria-label="activePath || 'Skill 文件内容'"
        spellcheck="false"
      />
    </div>
    <SkillValidationPanel v-if="validation" :result="validation" @navigate="selectFile" />
  </section>
</template>

<style scoped>
.skill-editor { display: flex; flex: 1; flex-direction: column; min-height: 0; border: 1px solid var(--border-light); border-radius: var(--radius-lg); background: var(--surface-primary); overflow: hidden; }
.skill-editor-toolbar { display: flex; align-items: center; gap: 8px; min-height: 48px; padding: 7px 10px; border-bottom: 1px solid var(--border-light); }
.skill-editor-toolbar strong { margin-right: auto; color: var(--text-primary); font-size: 13px; }
.skill-editor-toolbar span { color: var(--status-warning); font-size: 11px; }
.skill-editor-toolbar button, .skill-editor-toolbar input { min-height: 32px; padding: 0 9px; border: 1px solid var(--border-light); border-radius: 6px; background: var(--surface-primary); color: var(--text-secondary); }
.skill-editor-toolbar button { cursor: pointer; }
.skill-editor-toolbar button:disabled { cursor: not-allowed; opacity: .45; }
.skill-editor-toolbar input { width: 160px; }
.skill-editor-workspace { display: flex; flex: 1; min-height: 300px; }
textarea { flex: 1; min-width: 0; padding: 18px; border: 0; outline: 0; resize: none; background: var(--surface-primary); color: var(--text-primary); font: 13px/1.65 var(--font-mono, monospace); }
.skill-editor-error { margin: 0; padding: 8px 12px; background: var(--status-error-soft); color: var(--status-error); font-size: 12px; }
.creator-handoff { margin: 0; padding: 9px 12px; border-bottom: 1px solid var(--border-light); background: var(--accent-soft); color: var(--text-secondary); font-size: 12px; }
</style>
