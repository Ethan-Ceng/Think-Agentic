<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, Ban, CheckCircle2, Sparkles } from 'lucide-vue-next'
import type { TraceEventRecord } from '@/lib/api/types'
import type { RunSkill } from '@/types/skill'

const props = defineProps<{ skills: RunSkill[]; events: TraceEventRecord[] }>()

const skipped = computed(() => props.events.filter((event) => event.event_type === 'skill.skipped'))
const failures = computed(() => props.events.filter((event) => event.event_type === 'skill.selection.failed'))

function shortHash(value: string): string {
  return value.length > 12 ? value.slice(0, 12) : value
}

function sourceLabel(source: RunSkill['source']): string {
  return source === 'personal' ? '个人' : source === 'marketplace' ? '市场' : '内置'
}

function eventName(event: TraceEventRecord): string {
  const ref = event.payload.ref as { name?: string } | undefined
  return String(event.payload.name ?? ref?.name ?? event.payload.requested_key ?? '未知 Skill')
}
</script>

<template>
  <section class="run-skills-panel">
    <article v-for="skill in skills" :key="skill.id" class="run-skill-card">
      <header>
        <span class="run-skill-icon"><Sparkles :size="15" /></span>
        <div><strong>{{ skill.name }}</strong><small>{{ sourceLabel(skill.source) }}</small></div>
        <span class="decision-label">{{ skill.selection_mode === 'manual' ? '手动选择' : '自动识别' }}</span>
      </header>
      <dl>
        <dt>版本</dt><dd>{{ skill.skill_version_id || '随应用发布' }}</dd>
        <dt>内容哈希</dt><dd><code :title="skill.content_sha256">{{ shortHash(skill.content_sha256) }}</code></dd>
        <template v-if="skill.confidence != null"><dt>置信度</dt><dd>{{ Math.round(skill.confidence * 100) }}%</dd></template>
        <dt>原因</dt><dd>{{ skill.reason }}</dd>
        <dt>Sandbox</dt><dd><code>{{ skill.sandbox_path }}</code></dd>
      </dl>
      <footer><CheckCircle2 :size="13" />已物化并注入本次 Run</footer>
    </article>

    <article v-for="event in skipped" :key="event.id" class="run-skill-outcome skipped">
      <Ban :size="16" /><div><strong>{{ eventName(event) }} · {{ event.payload.code }}</strong><p>{{ event.payload.reason }}</p></div>
    </article>
    <article v-for="event in failures" :key="event.id" class="run-skill-outcome failed">
      <AlertTriangle :size="16" /><div><strong>{{ event.payload.error_type || 'Skill selection failed' }}</strong><p>{{ event.payload.message }}</p></div>
    </article>

    <div v-if="skills.length === 0 && skipped.length === 0 && failures.length === 0" class="run-skills-empty">
      本次 Run 没有选择 Skill。
    </div>
  </section>
</template>

<style scoped>
.run-skills-panel { display: grid; gap: 10px; }
.run-skill-card, .run-skill-outcome { padding: 12px; border: 1px solid var(--border-light); border-radius: var(--radius-md); background: var(--surface-primary); }
.run-skill-card header { display: flex; align-items: center; gap: 8px; }
.run-skill-icon { display: inline-flex; padding: 6px; border-radius: 7px; background: var(--surface-tertiary); color: var(--accent-primary); }
.run-skill-card header div { display: grid; gap: 2px; margin-right: auto; } header small { color: var(--text-tertiary); font-size: 10px; }
.decision-label { padding: 3px 7px; border-radius: 999px; background: var(--surface-tertiary); color: var(--text-secondary); font-size: 10px; font-weight: 650; }
dl { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 6px 10px; margin: 12px 0; font-size: 11px; } dt { color: var(--text-tertiary); } dd { margin: 0; overflow-wrap: anywhere; color: var(--text-secondary); } code { font-size: 10px; }
.run-skill-card footer { display: flex; align-items: center; gap: 5px; color: var(--status-success); font-size: 10px; }
.run-skill-outcome { display: flex; align-items: flex-start; gap: 8px; color: var(--status-warning); }
.run-skill-outcome.failed { color: var(--status-error); }
.run-skill-outcome div { display: grid; gap: 4px; } .run-skill-outcome strong { font-size: 11px; } .run-skill-outcome p { margin: 0; color: var(--text-secondary); font-size: 11px; }
.run-skills-empty { padding: 30px 12px; color: var(--text-tertiary); font-size: 12px; text-align: center; }
</style>
