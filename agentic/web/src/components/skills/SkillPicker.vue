<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Sparkles } from 'lucide-vue-next'
import type { SkillRef, SkillSummary } from '@/types/skill'

const props = withDefaults(defineProps<{
  skills: SkillSummary[]
  query: string
  selected: SkillRef[]
  max?: number
}>(), { max: 5 })

const emit = defineEmits<{ select: [skill: SkillSummary]; close: [] }>()
const activeIndex = ref(0)

const matches = computed(() => {
  const query = props.query.trim().toLowerCase()
  return props.skills.filter((skill) =>
    skill.enabled &&
    skill.status === 'active' &&
    (!query || `${skill.name} ${skill.display_name} ${skill.description}`.toLowerCase().includes(query)),
  )
})

function keyFor(ref: SkillRef): string {
  return `${ref.source}:${ref.skill_id ?? ref.name}`
}

function refFor(skill: SkillSummary): SkillRef {
  return { source: skill.scope === 'marketplace' ? 'marketplace' : 'personal', skill_id: skill.id, name: skill.name }
}

function isSelected(skill: SkillSummary): boolean {
  const target = keyFor(refFor(skill))
  return props.selected.some((selected) => keyFor(selected) === target)
}

function choose(skill: SkillSummary): boolean {
  if (props.selected.length >= props.max || isSelected(skill)) return false
  emit('select', skill)
  return true
}

function handleKeydown(event: KeyboardEvent): boolean {
  if (event.key === 'Escape') { event.preventDefault(); emit('close'); return true }
  if (event.key === 'ArrowDown') { event.preventDefault(); activeIndex.value = Math.min(activeIndex.value + 1, matches.value.length - 1); return true }
  if (event.key === 'ArrowUp') { event.preventDefault(); activeIndex.value = Math.max(activeIndex.value - 1, 0); return true }
  if (event.key === 'Enter' && matches.value[activeIndex.value]) {
    event.preventDefault()
    choose(matches.value[activeIndex.value])
    return true
  }
  return false
}

watch(() => [props.query, matches.value.length], () => { activeIndex.value = 0 })
defineExpose({ handleKeydown })
</script>

<template>
  <div class="skill-picker" role="listbox" tabindex="-1" @keydown="handleKeydown">
    <header><Sparkles :size="14" />选择 Skill <span>{{ selected.length }}/{{ max }}</span></header>
    <p v-if="selected.length >= max" class="skill-picker-limit">最多选择 {{ max }} 个</p>
    <p v-if="matches.length === 0" class="skill-picker-empty">没有匹配的已启用 Skill；输入内容将保留为普通文本。</p>
    <button
      v-for="(skill, index) in matches"
      :key="skill.id"
      type="button"
      role="option"
      :aria-selected="isSelected(skill)"
      :class="{ active: index === activeIndex, selected: isSelected(skill) }"
      :disabled="isSelected(skill) || selected.length >= max"
      @mouseenter="activeIndex = index"
      @click="choose(skill)"
    >
      <span><strong>{{ skill.display_name }}</strong><small>${{ skill.name }}</small></span>
      <Check v-if="isSelected(skill)" :size="14" />
    </button>
  </div>
</template>

<style scoped>
.skill-picker { position: absolute; z-index: 20; right: 12px; bottom: calc(100% - 8px); width: min(360px, calc(100% - 24px)); max-height: 280px; padding: 7px; border: 1px solid var(--border-light); border-radius: var(--radius-md); background: var(--surface-primary); box-shadow: var(--shadow-lg); overflow: auto; }
header { display: flex; align-items: center; gap: 6px; padding: 5px 7px 8px; color: var(--text-secondary); font-size: 11px; font-weight: 700; } header span { margin-left: auto; }
.skill-picker > button { display: flex; align-items: center; justify-content: space-between; width: 100%; min-height: 44px; padding: 6px 9px; border: 0; border-radius: 7px; background: transparent; color: var(--text-secondary); cursor: pointer; text-align: left; }
.skill-picker > button.active { background: var(--surface-hover); color: var(--text-primary); }
.skill-picker > button:disabled { cursor: default; opacity: .55; }
.skill-picker > button span { display: grid; gap: 2px; } strong { font-size: 12px; } small { color: var(--text-tertiary); font-size: 10px; }
.skill-picker-limit, .skill-picker-empty { margin: 0; padding: 8px; color: var(--text-tertiary); font-size: 11px; }
</style>
