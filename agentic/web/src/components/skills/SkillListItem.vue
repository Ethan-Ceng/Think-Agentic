<script setup lang="ts">
import type { SkillSummary } from '@/types/skill'

defineProps<{ skill: SkillSummary }>()

const emit = defineEmits<{
  enabled: [value: boolean]
  autoInvoke: [value: boolean]
}>()
</script>

<template>
  <article class="skill-list-item">
    <div class="skill-list-heading">
      <RouterLink :to="`/skills/${skill.id}`">{{ skill.display_name }}</RouterLink>
      <span>{{ skill.scope === 'personal' ? '个人' : '市场' }}</span>
      <span>{{ skill.status === 'active' ? '已发布' : skill.status === 'draft' ? '草稿' : '已归档' }}</span>
    </div>
    <p>{{ skill.description }}</p>
    <div class="skill-switches">
      <label>
        <input
          :data-testid="`enabled-${skill.id}`"
          type="checkbox"
          :checked="skill.enabled"
          @change="emit('enabled', ($event.target as HTMLInputElement).checked)"
        >
        启用
      </label>
      <label>
        <input
          :data-testid="`auto-${skill.id}`"
          type="checkbox"
          :checked="skill.auto_invoke"
          :disabled="!skill.enabled"
          @change="emit('autoInvoke', ($event.target as HTMLInputElement).checked)"
        >
        自动识别
      </label>
    </div>
  </article>
</template>

<style scoped>
.skill-list-item { display: grid; gap: 8px; padding: 12px; border: 1px solid var(--border-light); border-radius: var(--radius-md); background: var(--surface-primary); }
.skill-list-heading { display: flex; align-items: center; gap: 6px; min-width: 0; }
.skill-list-heading a { min-width: 0; margin-right: auto; overflow: hidden; color: var(--text-primary); font-size: 13px; font-weight: 700; text-overflow: ellipsis; text-decoration: none; white-space: nowrap; }
.skill-list-heading span { padding: 2px 5px; border-radius: 999px; background: var(--surface-tertiary); color: var(--text-tertiary); font-size: 10px; white-space: nowrap; }
p { margin: 0; overflow: hidden; color: var(--text-secondary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.skill-switches { display: flex; gap: 12px; color: var(--text-secondary); font-size: 11px; }
.skill-switches label { display: inline-flex; align-items: center; gap: 5px; cursor: pointer; }
</style>
