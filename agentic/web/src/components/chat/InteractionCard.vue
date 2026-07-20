<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, Check, CircleHelp, Loader2, ShieldAlert, X } from 'lucide-vue-next'
import type { InteractionEvent, ResolveInteractionParams } from '@/lib/api/types'

const props = withDefaults(defineProps<{
  interaction: InteractionEvent
  busy?: boolean
  error?: string
}>(), {
  busy: false,
  error: '',
})

const emit = defineEmits<{
  resolve: [actionId: string, params: ResolveInteractionParams]
}>()

const selectedValues = ref<string[]>([])
const answer = ref('')

watch(
  () => props.interaction.action_id,
  () => {
    selectedValues.value = [...(props.interaction.selected_values || [])]
    answer.value = props.interaction.answer || ''
  },
  { immediate: true },
)

const isPending = computed(() => props.interaction.status === 'pending')
const canAnswer = computed(
  () =>
    isPending.value &&
    !props.busy &&
    (selectedValues.value.length > 0 ||
      (props.interaction.allow_text && answer.value.trim().length > 0)),
)
const optionLabels = computed(() => {
  const labels = new Map(props.interaction.options.map((option) => [option.value, option.label]))
  return (props.interaction.selected_values || []).map((value) => labels.get(value) || value)
})

function toggleOption(value: string) {
  if (!isPending.value || props.busy) return
  if (!props.interaction.allow_multiple) {
    selectedValues.value = [value]
    return
  }
  selectedValues.value = selectedValues.value.includes(value)
    ? selectedValues.value.filter((selected) => selected !== value)
    : [...selectedValues.value, value]
}

function submitAnswer() {
  if (!canAnswer.value) return
  emit('resolve', props.interaction.action_id, {
    decision: 'answer',
    ...(answer.value.trim() ? { answer: answer.value.trim() } : {}),
    selected_values: selectedValues.value,
  })
}

function submitApproval(decision: 'approve' | 'reject') {
  if (!isPending.value || props.busy) return
  emit('resolve', props.interaction.action_id, { decision })
}

function redact(value: unknown, key = ''): unknown {
  if (/token|secret|password|api[_-]?key|authorization/i.test(key)) return '••••••'
  if (Array.isArray(value)) return value.map((item) => redact(item))
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([entryKey, entryValue]) => [
        entryKey,
        redact(entryValue, entryKey),
      ]),
    )
  }
  return value
}

const argumentsPreview = computed(() =>
  JSON.stringify(redact(props.interaction.function_args), null, 2),
)
</script>

<template>
  <article
    class="interaction-card"
    :class="[`is-${interaction.interaction_type}`, { 'is-resolved': !isPending }]"
    :aria-busy="busy"
  >
    <header class="interaction-header">
      <span class="interaction-icon">
        <CircleHelp v-if="interaction.interaction_type === 'ask_user'" :size="18" />
        <ShieldAlert v-else :size="18" />
      </span>
      <div>
        <strong>{{ interaction.interaction_type === 'ask_user' ? '需要你的回答' : '需要执行确认' }}</strong>
        <span>{{ isPending ? 'Agent 已暂停，等待你处理' : '此交互已处理' }}</span>
      </div>
      <span v-if="interaction.risk_level" class="risk-badge" :class="`risk-${interaction.risk_level}`">
        {{ interaction.risk_level === 'high' ? '高风险' : interaction.risk_level === 'medium' ? '中风险' : '低风险' }}
      </span>
    </header>

    <div class="interaction-body">
      <h3>{{ interaction.prompt }}</h3>
      <p v-if="interaction.description" class="interaction-description">{{ interaction.description }}</p>

      <template v-if="interaction.interaction_type === 'ask_user'">
        <div v-if="interaction.options.length" class="interaction-options" role="group" :aria-label="interaction.prompt">
          <button
            v-for="option in interaction.options"
            :key="option.value"
            type="button"
            class="interaction-option"
            :class="{ selected: selectedValues.includes(option.value) }"
            :disabled="!isPending || busy"
            @click="toggleOption(option.value)"
          >
            <span class="option-check"><Check v-if="selectedValues.includes(option.value)" :size="13" /></span>
            <span><strong>{{ option.label }}</strong><small v-if="option.description">{{ option.description }}</small></span>
          </button>
        </div>
        <textarea
          v-if="interaction.allow_text && isPending"
          v-model="answer"
          class="interaction-textarea"
          :placeholder="interaction.placeholder || '输入你的回答…'"
          :disabled="busy"
          rows="3"
          @keydown.ctrl.enter="submitAnswer"
          @keydown.meta.enter="submitAnswer"
        />
        <div v-if="isPending" class="interaction-actions">
          <button class="interaction-button primary" type="button" :disabled="!canAnswer" @click="submitAnswer">
            <Loader2 v-if="busy" class="spin" :size="15" />
            <Check v-else :size="15" />
            提交回答
          </button>
        </div>
        <div v-else class="resolved-summary">
          <Check :size="16" />
          <span>已回答：{{ [...optionLabels, interaction.answer].filter(Boolean).join('、') }}</span>
        </div>
      </template>

      <template v-else>
        <div class="tool-summary">
          <div><span>工具</span><strong>{{ interaction.function_name }}</strong></div>
          <pre>{{ argumentsPreview }}</pre>
        </div>
        <div v-if="isPending" class="interaction-actions approval-actions">
          <button class="interaction-button danger" type="button" :disabled="busy" @click="submitApproval('reject')">
            <X :size="15" />拒绝
          </button>
          <button class="interaction-button primary" type="button" :disabled="busy" @click="submitApproval('approve')">
            <Loader2 v-if="busy" class="spin" :size="15" />
            <Check v-else :size="15" />批准并继续
          </button>
        </div>
        <div v-else class="resolved-summary" :class="{ rejected: interaction.decision === 'reject' }">
          <AlertTriangle v-if="interaction.decision === 'reject'" :size="16" />
          <Check v-else :size="16" />
          <span>{{ interaction.decision === 'reject' ? '已拒绝执行' : '已批准执行' }}</span>
        </div>
      </template>

      <p v-if="error" class="interaction-error" role="alert">{{ error }}</p>
    </div>
  </article>
</template>

<style scoped>
.interaction-card { width: min(100%, 720px); margin-left: 44px; overflow: hidden; border: 1px solid #dbe4f0; border-radius: 16px; background: var(--bg-primary, #fff); box-shadow: 0 12px 30px rgba(15, 23, 42, .08); }
.interaction-card.is-tool_approval { border-color: #fed7aa; }
.interaction-card.is-resolved { opacity: .82; box-shadow: none; }
.interaction-header { display: flex; align-items: center; gap: 10px; padding: 13px 15px; border-bottom: 1px solid #e8eef6; background: #f8fafc; }
.interaction-icon { display: grid; width: 34px; height: 34px; place-items: center; border-radius: 10px; background: #eef2ff; color: #4f46e5; }
.is-tool_approval .interaction-icon { background: #fff7ed; color: #c2410c; }
.interaction-header > div { display: flex; flex: 1; flex-direction: column; gap: 2px; }
.interaction-header strong { color: var(--text-primary, #0f172a); font-size: 13px; }
.interaction-header span { color: var(--text-tertiary, #64748b); font-size: 12px; }
.risk-badge { padding: 3px 8px; border-radius: 999px; font-weight: 700; }
.risk-high { background: #fee2e2; color: #b91c1c !important; }
.risk-medium { background: #fef3c7; color: #92400e !important; }
.risk-low { background: #dcfce7; color: #166534 !important; }
.interaction-body { display: flex; flex-direction: column; gap: 13px; padding: 16px; }
.interaction-body h3 { margin: 0; color: var(--text-primary, #0f172a); font-size: 15px; line-height: 1.55; }
.interaction-description { margin: -5px 0 0; color: var(--text-secondary, #475569); font-size: 13px; line-height: 1.6; }
.interaction-options { display: grid; gap: 8px; }
.interaction-option { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid #dbe4f0; border-radius: 11px; background: transparent; color: var(--text-primary, #0f172a); cursor: pointer; text-align: left; }
.interaction-option.selected { border-color: #6366f1; background: #eef2ff; }
.interaction-option:disabled { cursor: default; }
.option-check { display: grid; width: 18px; height: 18px; flex: 0 0 auto; place-items: center; border: 1px solid #cbd5e1; border-radius: 5px; color: #fff; }
.selected .option-check { border-color: #4f46e5; background: #4f46e5; }
.interaction-option > span:last-child { display: flex; flex-direction: column; gap: 2px; }
.interaction-option small { color: #64748b; font-size: 12px; }
.interaction-textarea { resize: vertical; min-height: 76px; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 10px; background: var(--bg-primary, #fff); color: var(--text-primary, #0f172a); font: inherit; line-height: 1.5; }
.interaction-textarea:focus { border-color: #6366f1; outline: 2px solid rgba(99, 102, 241, .15); }
.interaction-actions { display: flex; justify-content: flex-end; gap: 9px; }
.interaction-button { display: inline-flex; min-height: 36px; align-items: center; justify-content: center; gap: 6px; padding: 0 13px; border: 1px solid #cbd5e1; border-radius: 9px; background: #fff; color: #334155; cursor: pointer; font-weight: 700; }
.interaction-button.primary { border-color: #4f46e5; background: #4f46e5; color: #fff; }
.interaction-button.danger { border-color: #fecaca; color: #b91c1c; }
.interaction-button:disabled { cursor: not-allowed; opacity: .55; }
.tool-summary { overflow: hidden; border: 1px solid #e2e8f0; border-radius: 10px; }
.tool-summary > div { display: flex; gap: 9px; padding: 9px 11px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }
.tool-summary > div span { color: #64748b; }
.tool-summary pre { max-height: 220px; margin: 0; overflow: auto; padding: 11px; background: #0f172a; color: #dbeafe; font-size: 12px; line-height: 1.5; }
.resolved-summary { display: flex; align-items: center; gap: 7px; color: #166534; font-size: 13px; font-weight: 650; }
.resolved-summary.rejected { color: #b45309; }
.interaction-error { margin: 0; color: #b91c1c; font-size: 12px; }
.spin { animation: interaction-spin 1s linear infinite; }
@keyframes interaction-spin { to { transform: rotate(360deg); } }
@media (max-width: 640px) { .interaction-card { width: 100%; margin-left: 0; } .approval-actions { display: grid; grid-template-columns: 1fr 1fr; } }
</style>
