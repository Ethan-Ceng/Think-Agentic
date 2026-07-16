<script setup lang="ts">
import { FileText, Folder } from 'lucide-vue-next'
import type { SkillDraftTreeEntry } from '@/types/skill'

defineProps<{ entries: SkillDraftTreeEntry[]; activePath: string }>()
defineEmits<{ select: [path: string] }>()
</script>

<template>
  <nav class="skill-file-tree" aria-label="Skill 文件">
    <button
      v-for="entry in entries"
      :key="entry.path"
      type="button"
      :class="{ active: entry.path === activePath }"
      :disabled="entry.kind === 'directory'"
      :style="{ paddingLeft: `${10 + entry.path.split('/').length * 8}px` }"
      @click="entry.kind === 'file' && $emit('select', entry.path)"
    >
      <Folder v-if="entry.kind === 'directory'" :size="14" />
      <FileText v-else :size="14" />
      <span>{{ entry.path.split('/').at(-1) }}</span>
    </button>
  </nav>
</template>

<style scoped>
.skill-file-tree { display: flex; flex-direction: column; min-width: 190px; padding: 8px; border-right: 1px solid var(--border-light); overflow: auto; }
button { display: flex; align-items: center; gap: 6px; min-height: 32px; border: 0; border-radius: 6px; background: transparent; color: var(--text-secondary); cursor: pointer; text-align: left; }
button:disabled { opacity: 1; cursor: default; }
button.active { background: var(--surface-hover); color: var(--text-primary); font-weight: 650; }
</style>
