<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { PanelLeftOpen, Plus, Upload } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import SkillEditor from '@/components/skills/SkillEditor.vue'
import SkillListItem from '@/components/skills/SkillListItem.vue'
import { useSidebar } from '@/composables/useSidebar'
import { useAuthStore } from '@/stores/auth'
import { useSkillsStore } from '@/stores/skills'
import type { PublishedSkill } from '@/types/skill'

const route = useRoute()
const router = useRouter()
const sidebar = useSidebar()
const auth = useAuthStore()
const store = useSkillsStore()
const draftId = ref('')
const importFile = ref<File | null>(null)
const importName = ref('')
const busy = ref(false)
const formError = ref('')
const draft = reactive({ name: '', display_name: '', description: '' })

const action = ref(typeof route.query.action === 'string' ? route.query.action : '')
watch(() => route.query.action, (value) => { action.value = typeof value === 'string' ? value : '' })

function closeAction(): void {
  action.value = ''
  void router.replace({ name: 'skills' })
}

async function createDraft(): Promise<void> {
  busy.value = true
  formError.value = ''
  try {
    const created = await store.createDraft(draft)
    draftId.value = created.draft_id
    closeAction()
  } catch (cause) {
    formError.value = cause instanceof Error ? cause.message : '创建失败'
  } finally {
    busy.value = false
  }
}

function pickImport(event: Event): void {
  importFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function importSkill(): Promise<void> {
  if (!importFile.value) return
  busy.value = true
  formError.value = ''
  try {
    const published = await store.importSkill(importFile.value, importName.value || undefined)
    closeAction()
    await router.push({ name: 'skill-detail', params: { skillId: published.skill.id } })
  } catch (cause) {
    formError.value = cause instanceof Error ? cause.message : '导入失败'
  } finally {
    busy.value = false
  }
}

function handlePublished(published: PublishedSkill): void {
  draftId.value = ''
  void router.push({ name: 'skill-detail', params: { skillId: published.skill.id } })
}

onMounted(async () => {
  store.resetForUser(auth.user?.id ?? null)
  try { await store.loadSkills() } catch { /* rendered by store */ }
})
</script>

<template>
  <div class="skills-view">
    <header class="skills-view-header">
      <button v-if="sidebar.mobile.value && !sidebar.open.value" type="button" aria-label="打开侧边栏" @click="sidebar.openSidebar('skills')"><PanelLeftOpen :size="18" /></button>
      <div><h1>Skills</h1><p>管理可复用的标准 Skill 包，以及 Agent 的启用与自动识别策略。</p></div>
      <button type="button" @click="action = 'import'"><Upload :size="16" />导入标准包</button>
      <button class="primary" type="button" @click="action = 'new'"><Plus :size="16" />新建 Skill</button>
    </header>

    <section v-if="action" class="skill-action-card">
      <form v-if="action === 'new'" @submit.prevent="createDraft">
        <h2>新建 Skill 草稿</h2>
        <label>名称 <input v-model="draft.name" required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="report-writer"></label>
        <label>显示名称 <input v-model="draft.display_name" required></label>
        <label>说明 <input v-model="draft.description" required></label>
        <button type="button" @click="closeAction">取消</button><button class="primary" type="submit" :disabled="busy">创建并编辑</button>
      </form>
      <form v-else @submit.prevent="importSkill">
        <h2>导入标准 Skill 包</h2>
        <label>Skill 压缩包 <input type="file" required accept=".zip,.skill" @change="pickImport"></label>
        <label>显示名称（可选） <input v-model="importName"></label>
        <button type="button" @click="closeAction">取消</button><button class="primary" type="submit" :disabled="busy || !importFile">导入</button>
      </form>
      <p v-if="formError" class="form-error">{{ formError }}</p>
    </section>

    <SkillEditor v-if="draftId" :draft-id="draftId" @published="handlePublished" />
    <template v-else>
      <div v-if="store.loading" class="page-state">正在加载 Skills…</div>
      <div v-else-if="store.error" class="page-state"><strong>加载失败</strong><span>{{ store.error }}</span><button type="button" @click="store.loadSkills">重试</button></div>
      <div v-else-if="store.skills.length === 0" class="page-state"><strong>还没有 Skill</strong><span>新建草稿，或导入兼容的标准 Skill 包。</span></div>
      <div v-else class="skills-grid">
        <SkillListItem v-for="skill in store.skills" :key="skill.id" :skill="skill" @enabled="store.setEnabled(skill.id, $event)" @auto-invoke="store.setAutoInvoke(skill.id, $event)" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.skills-view { display: flex; flex-direction: column; gap: 18px; height: 100%; padding: 24px 28px; overflow: auto; }
.skills-view-header { display: flex; align-items: center; gap: 10px; }
.skills-view-header > div { margin-right: auto; }
h1, h2, p { margin: 0; }
h1 { color: var(--text-primary); font-size: 24px; }
.skills-view-header p { margin-top: 4px; color: var(--text-secondary); font-size: 13px; }
button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 36px; padding: 0 11px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--surface-primary); color: var(--text-secondary); cursor: pointer; }
button.primary { border-color: var(--accent-primary); background: var(--accent-primary); color: var(--accent-contrast); }
.skills-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.skill-action-card { padding: 16px; border: 1px solid var(--border-light); border-radius: var(--radius-lg); background: var(--surface-primary); }
.skill-action-card form { display: grid; grid-template-columns: repeat(3, minmax(140px, 1fr)) auto auto; align-items: end; gap: 10px; }
.skill-action-card h2 { grid-column: 1 / -1; font-size: 16px; }
.skill-action-card label { display: grid; gap: 5px; color: var(--text-secondary); font-size: 12px; }
.skill-action-card input { min-height: 36px; padding: 0 9px; border: 1px solid var(--border-light); border-radius: 6px; background: var(--surface-primary); color: var(--text-primary); }
.form-error { margin-top: 8px; color: var(--status-error); font-size: 12px; }
</style>
