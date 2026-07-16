<script setup lang="ts">
import { X } from 'lucide-vue-next'
import type { SkillRef } from '@/types/skill'

withDefaults(defineProps<{ skill: SkillRef; removable?: boolean }>(), { removable: false })
defineEmits<{ remove: [] }>()
</script>

<template>
  <span class="skill-chip">
    <span>$</span>{{ skill.name }}
    <button v-if="removable" type="button" :aria-label="`移除 ${skill.name}`" @click="$emit('remove')"><X :size="12" /></button>
  </span>
</template>

<style scoped>
.skill-chip { display: inline-flex; align-items: center; gap: 3px; min-height: 24px; padding: 0 7px; border: 1px solid color-mix(in srgb, var(--accent-primary) 25%, var(--border-light)); border-radius: 999px; background: color-mix(in srgb, var(--accent-primary) 8%, var(--surface-primary)); color: var(--accent-primary); font-size: 11px; font-weight: 650; }
.skill-chip > span { opacity: .7; }
button { display: inline-flex; padding: 1px; border: 0; border-radius: 50%; background: transparent; color: currentColor; cursor: pointer; }
</style>
