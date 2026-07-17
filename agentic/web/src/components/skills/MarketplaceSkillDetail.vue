<script setup lang="ts">
import { Download, GitFork, RefreshCw, Trash2 } from 'lucide-vue-next'
import type { MarketplaceSkill } from '@/types/skill'

defineProps<{ skill: MarketplaceSkill; busy?: boolean }>()
const emit = defineEmits<{ install: []; update: []; uninstall: []; fork: [] }>()

function uninstall(): void {
  if (window.confirm('卸载后，此 Skill 将不再出现在手动选择和自动调用目录中。确定继续吗？')) {
    emit('uninstall')
  }
}
</script>

<template>
  <aside class="marketplace-detail" aria-live="polite">
    <div class="detail-heading">
      <div><h2>{{ skill.display_name }}</h2><code>{{ skill.name }}</code></div>
      <span v-if="skill.installation" class="installed">已安装</span>
    </div>
    <p>{{ skill.description }}</p>
    <dl>
      <dt>最新版本</dt><dd>v{{ skill.latest_version.version }}</dd>
      <dt>文件数</dt><dd>{{ skill.latest_version.file_count }}</dd>
      <dt>SHA-256</dt><dd><code>{{ skill.latest_version.package_sha256 }}</code></dd>
      <template v-if="skill.installation">
        <dt>当前固定版本</dt><dd>{{ skill.installation.pinned_version_id }}</dd>
        <dt>自动更新</dt><dd>关闭（更新需显式执行）</dd>
      </template>
    </dl>
    <p v-if="skill.update_available" class="update-note">已有新版本；当前安装和历史 Run 不会自动变化。</p>
    <div class="detail-actions">
      <button
        v-if="!skill.installation"
        type="button"
        data-testid="marketplace-install"
        :disabled="busy"
        @click="$emit('install')"
      ><Download :size="15" />安装</button>
      <button
        v-if="skill.installation && skill.update_available"
        type="button"
        data-testid="marketplace-update"
        :disabled="busy"
        @click="$emit('update')"
      ><RefreshCw :size="15" />更新</button>
      <button
        v-if="skill.installation"
        type="button"
        data-testid="marketplace-uninstall"
        :disabled="busy"
        @click="uninstall"
      ><Trash2 :size="15" />卸载</button>
      <button
        type="button"
        data-testid="marketplace-fork"
        :disabled="busy"
        @click="$emit('fork')"
      ><GitFork :size="15" />Fork 并编辑</button>
    </div>
  </aside>
</template>

<style scoped>
.marketplace-detail { display: grid; align-content: start; gap: 15px; padding: 20px; border: 1px solid var(--border-light); border-radius: var(--radius-lg); background: var(--surface-primary); }
.detail-heading { display: flex; align-items: start; justify-content: space-between; gap: 12px; }
h2, p { margin: 0; } h2 { margin-bottom: 4px; font-size: 19px; } p { color: var(--text-secondary); line-height: 1.5; }
.installed { padding: 4px 7px; border-radius: 999px; background: color-mix(in srgb, var(--accent-primary) 12%, transparent); color: var(--accent-primary); font-size: 12px; }
dl { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 8px; margin: 0; font-size: 12px; } dt { color: var(--text-tertiary); } dd { margin: 0; overflow-wrap: anywhere; color: var(--text-primary); }
.update-note { padding: 9px; border-radius: 7px; background: var(--surface-secondary); font-size: 12px; }
.detail-actions { display: flex; flex-wrap: wrap; gap: 8px; }
button { display: inline-flex; align-items: center; gap: 5px; min-height: 36px; padding: 0 11px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--surface-primary); color: var(--text-secondary); cursor: pointer; }
button:first-child { border-color: var(--accent-primary); background: var(--accent-primary); color: var(--accent-contrast); } button:disabled { cursor: wait; opacity: .6; }
</style>
