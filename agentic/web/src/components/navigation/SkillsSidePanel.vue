<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { Plus, RefreshCw, Upload } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import SkillListItem from '@/components/skills/SkillListItem.vue'
import { useAuthStore } from '@/stores/auth'
import { useSkillsStore } from '@/stores/skills'

defineEmits<{ close: [] }>()

const router = useRouter()
const auth = useAuthStore()
const store = useSkillsStore()

async function load(): Promise<void> {
  try {
    await store.loadSkills()
  } catch {
    // The store exposes the message in its error state.
  }
}

async function changeEnabled(skillId: string, enabled: boolean): Promise<void> {
  try {
    await store.setEnabled(skillId, enabled)
  } catch {
    // Optimistic state is rolled back by the store.
  }
}

async function changeAutoInvoke(skillId: string, enabled: boolean): Promise<void> {
  try {
    await store.setAutoInvoke(skillId, enabled)
  } catch {
    // Keep the backend state when the update fails.
  }
}

function openSkills(query?: Record<string, string>): void {
  void router.push({ name: 'skills', query })
}

watch(
  () => auth.user?.id ?? null,
  (userId, previousUserId) => {
    store.resetForUser(userId)
    if (userId && userId !== previousUserId) void load()
  },
)

onMounted(() => {
  store.resetForUser(auth.user?.id ?? null)
  if (auth.user) void load()
})
</script>

<template>
  <div class="sidebar-panel-body skills-side-panel">
    <div class="skills-panel-actions">
      <button type="button" @click="openSkills({ action: 'new' })"><Plus :size="15" />新建</button>
      <button type="button" @click="openSkills({ action: 'import' })"><Upload :size="15" />导入</button>
      <button type="button" aria-label="刷新 Skills" @click="load"><RefreshCw :size="15" /></button>
    </div>
    <div class="sidebar-section-heading"><span>我的 Skills</span><RouterLink to="/skills">管理</RouterLink></div>

    <div v-if="store.loading" data-testid="skills-loading" class="sidebar-empty-state">正在加载…</div>
    <div v-else-if="store.error" data-testid="skills-error" class="sidebar-empty-state">
      <p>加载失败</p><span>{{ store.error }}</span>
      <button data-testid="skills-retry" type="button" @click="load">重试</button>
    </div>
    <div v-else-if="store.skills.length === 0" data-testid="skills-empty" class="sidebar-empty-state">
      <p>还没有 Skill</p><span>导入标准包或创建一个草稿</span>
      <button data-testid="skills-retry" type="button" @click="load">刷新</button>
    </div>
    <div v-else class="skills-panel-list">
      <SkillListItem
        v-for="skill in store.skills"
        :key="skill.id"
        :skill="skill"
        @enabled="changeEnabled(skill.id, $event)"
        @auto-invoke="changeAutoInvoke(skill.id, $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.skills-side-panel { gap: 10px; }
.skills-panel-actions { display: flex; gap: 6px; }
.skills-panel-actions button, .sidebar-empty-state button { display: inline-flex; align-items: center; justify-content: center; gap: 5px; min-height: 34px; padding: 0 9px; border: 1px solid var(--border-light); border-radius: var(--radius-sm); background: var(--surface-primary); color: var(--text-secondary); cursor: pointer; font-size: 12px; }
.skills-panel-actions button:last-child { width: 34px; padding: 0; margin-left: auto; }
.sidebar-section-heading a { color: var(--accent-primary); text-decoration: none; text-transform: none; }
.skills-panel-list { display: flex; flex: 1; flex-direction: column; gap: 8px; min-height: 0; overflow-y: auto; }
</style>
