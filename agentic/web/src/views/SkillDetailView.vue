<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ArrowLeft, Archive } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { useSkillsStore } from '@/stores/skills'

const route = useRoute()
const router = useRouter()
const store = useSkillsStore()
const skillId = String(route.params.skillId)
const editing = ref(false)
const busy = ref(false)
const error = ref('')
const form = reactive({ display_name: '', description: '' })

async function load(): Promise<void> {
  error.value = ''
  try {
    const detail = await store.loadSkill(skillId, true)
    form.display_name = detail.skill.display_name
    form.description = detail.skill.description
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '加载失败'
  }
}

async function save(): Promise<void> {
  busy.value = true
  try {
    await store.updateSkill(skillId, form)
    editing.value = false
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '保存失败' }
  finally { busy.value = false }
}

async function archive(): Promise<void> {
  if (!window.confirm('归档后将不再自动选择此 Skill。确定继续吗？')) return
  busy.value = true
  try { await store.archiveSkill(skillId); await router.push({ name: 'skills' }) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '归档失败' }
  finally { busy.value = false }
}

onMounted(() => void load())
</script>

<template>
  <div class="skill-detail-view">
    <header><RouterLink to="/skills"><ArrowLeft :size="17" />Skills</RouterLink><button type="button" :disabled="busy" @click="archive"><Archive :size="16" />归档</button></header>
    <div v-if="error" class="page-state"><strong>无法加载 Skill</strong><span>{{ error }}</span></div>
    <section v-else-if="store.details[skillId]" class="skill-detail-card">
      <template v-if="editing">
        <label>显示名称<input v-model="form.display_name"></label>
        <label>说明<textarea v-model="form.description" /></label>
        <div><button type="button" @click="editing = false">取消</button><button class="primary" type="button" :disabled="busy" @click="save">保存</button></div>
      </template>
      <template v-else>
        <h1>{{ store.details[skillId].skill.display_name }}</h1>
        <code>{{ store.details[skillId].skill.name }}</code>
        <p>{{ store.details[skillId].skill.description }}</p>
        <dl><dt>状态</dt><dd>{{ store.details[skillId].skill.status }}</dd><dt>版本</dt><dd>{{ store.details[skillId].version?.version ?? '—' }}</dd><dt>包 SHA-256</dt><dd>{{ store.details[skillId].version?.package_sha256 ?? '—' }}</dd><dt>文件数</dt><dd>{{ store.details[skillId].version?.file_count ?? '—' }}</dd></dl>
        <button class="primary" type="button" @click="editing = true">编辑资料</button>
      </template>
    </section>
    <div v-else class="page-state">正在加载…</div>
  </div>
</template>

<style scoped>
.skill-detail-view { height: 100%; padding: 24px 28px; overflow: auto; }
header { display: flex; justify-content: space-between; margin-bottom: 20px; }
header a, button { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 0 11px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--surface-primary); color: var(--text-secondary); cursor: pointer; text-decoration: none; }
.skill-detail-card { display: grid; gap: 15px; max-width: 760px; padding: 24px; border: 1px solid var(--border-light); border-radius: var(--radius-lg); background: var(--surface-primary); }
h1, p { margin: 0; } code { color: var(--text-tertiary); } p { color: var(--text-secondary); }
dl { display: grid; grid-template-columns: 120px 1fr; gap: 8px; } dt { color: var(--text-tertiary); } dd { margin: 0; overflow-wrap: anywhere; color: var(--text-primary); }
label { display: grid; gap: 6px; color: var(--text-secondary); font-size: 13px; }
input, textarea { min-height: 38px; padding: 9px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--surface-primary); color: var(--text-primary); } textarea { min-height: 120px; resize: vertical; }
button.primary { border-color: var(--accent-primary); background: var(--accent-primary); color: var(--accent-contrast); }
</style>
