<script setup lang="ts">
import { CheckCircle2, CircleAlert } from 'lucide-vue-next'
import type { SkillValidationResult } from '@/types/skill'

defineProps<{ result: SkillValidationResult }>()
defineEmits<{ navigate: [path: string] }>()
</script>

<template>
  <section class="skill-validation" :class="{ valid: result.valid }">
    <header><CheckCircle2 v-if="result.valid" :size="16" /><CircleAlert v-else :size="16" />{{ result.valid ? '校验通过' : `${result.diagnostics.length} 个问题` }}</header>
    <button
      v-for="(diagnostic, index) in result.diagnostics"
      :key="`${diagnostic.file}-${diagnostic.code}-${index}`"
      :data-testid="`diagnostic-${index}`"
      type="button"
      @click="$emit('navigate', diagnostic.file)"
    >
      <strong>{{ diagnostic.file }}<template v-if="diagnostic.line">:{{ diagnostic.line }}</template></strong>
      <span>{{ diagnostic.message }}</span>
      <code>{{ diagnostic.code }}</code>
    </button>
  </section>
</template>

<style scoped>
.skill-validation { display: grid; gap: 6px; padding: 10px; border-top: 1px solid var(--border-light); color: var(--status-error); }
.skill-validation.valid { color: var(--status-success); }
header { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; }
button { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; width: 100%; padding: 7px 8px; border: 0; border-radius: 6px; background: var(--surface-tertiary); color: var(--text-secondary); cursor: pointer; font-size: 11px; text-align: left; }
code { color: var(--text-tertiary); }
</style>
