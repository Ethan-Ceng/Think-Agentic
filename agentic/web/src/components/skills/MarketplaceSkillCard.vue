<script setup lang="ts">
import { PackageCheck } from 'lucide-vue-next'
import type { MarketplaceSkill } from '@/types/skill'

defineProps<{ skill: MarketplaceSkill; selected?: boolean }>()
defineEmits<{ select: [] }>()
</script>

<template>
  <button
    type="button"
    data-testid="marketplace-card"
    class="marketplace-card"
    :class="{ selected }"
    @click="$emit('select')"
  >
    <span class="card-heading">
      <strong>{{ skill.display_name }}</strong>
      <span v-if="skill.installation" class="installed"><PackageCheck :size="14" />已安装</span>
    </span>
    <code>{{ skill.name }}</code>
    <span class="description">{{ skill.description }}</span>
    <span class="version-row">
      <span>v{{ skill.latest_version.version }}</span>
      <span v-if="skill.update_available" class="update">有可用更新</span>
    </span>
  </button>
</template>

<style scoped>
.marketplace-card { display: grid; gap: 9px; width: 100%; padding: 16px; border: 1px solid var(--border-light); border-radius: var(--radius-lg); background: var(--surface-primary); color: var(--text-primary); cursor: pointer; text-align: left; }
.marketplace-card:hover, .marketplace-card.selected { border-color: var(--accent-primary); box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent-primary) 22%, transparent); }
.card-heading, .version-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.installed, .update { display: inline-flex; align-items: center; gap: 4px; color: var(--accent-primary); font-size: 12px; }
code { color: var(--text-tertiary); font-size: 12px; }
.description { min-height: 36px; color: var(--text-secondary); font-size: 13px; line-height: 1.45; }
.version-row { color: var(--text-tertiary); font-size: 12px; }
</style>
