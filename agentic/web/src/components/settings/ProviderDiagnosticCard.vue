<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Activity, AlertTriangle, CheckCircle2, RotateCcw } from 'lucide-vue-next'
import {
  providerDiagnosticsApi,
  type ProviderDiagnosticResult,
  type ProviderDiagnosticType,
} from '@/lib/api/provider-diagnostics'

const props = withDefaults(defineProps<{
  providerType: ProviderDiagnosticType
  targetId?: string | null
  disabled?: boolean
  resetKey?: string | number | boolean
  buttonLabel?: string
  description?: string
}>(), {
  targetId: null,
  disabled: false,
  resetKey: '',
  buttonLabel: '测试已保存配置',
  description: '',
})

const testing = ref(false)
const result = ref<ProviderDiagnosticResult | null>(null)
const error = ref('')
let configurationGeneration = 0

const statusLabel = computed(() => {
  if (
    result.value?.status === 'healthy'
    && result.value.check_kind === 'configuration'
  ) return '配置有效'
  if (result.value?.status === 'healthy') return '正常'
  if (result.value?.status === 'degraded') return '暂时降级'
  return '诊断失败'
})
const statusType = computed(() => {
  if (result.value?.status === 'healthy') return 'success'
  if (result.value?.status === 'degraded') return 'warning'
  return 'danger'
})
const checkKindLabel = computed(() => {
  if (result.value?.check_kind === 'inference') return '最小模型请求'
  if (result.value?.check_kind === 'discovery') return '能力发现'
  return '配置校验'
})

watch(
  () => props.resetKey,
  () => {
    configurationGeneration += 1
    result.value = null
    error.value = ''
  },
)

async function runDiagnostic() {
  if (testing.value || props.disabled) return
  const startedGeneration = configurationGeneration
  testing.value = true
  result.value = null
  error.value = ''
  try {
    const nextResult = await providerDiagnosticsApi.test({
      provider_type: props.providerType,
      target_id: props.targetId,
    })
    if (startedGeneration === configurationGeneration) {
      result.value = nextResult
    }
  } catch (cause) {
    if (startedGeneration === configurationGeneration) {
      result.value = null
      error.value = cause instanceof Error ? cause.message : 'Provider 诊断请求失败。'
    }
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <section class="provider-diagnostic" aria-live="polite">
    <div class="provider-diagnostic-action">
      <div>
        <strong>Provider 诊断</strong>
        <p v-if="description">{{ description }}</p>
      </div>
      <ElButton
        class="provider-diagnostic-button"
        size="small"
        :loading="testing"
        :disabled="disabled || testing"
        @click="runDiagnostic"
      >
        <Activity :size="14" />{{ buttonLabel }}
      </ElButton>
    </div>

    <div v-if="error" class="provider-diagnostic-error" role="alert">
      <AlertTriangle :size="15" />
      <span>{{ error }}</span>
      <ElButton text size="small" :disabled="testing" @click="runDiagnostic">
        <RotateCcw :size="13" />重试
      </ElButton>
    </div>

    <div
      v-else-if="result"
      class="provider-diagnostic-result"
      :class="`is-${result.status}`"
    >
      <div class="provider-diagnostic-result-heading">
        <CheckCircle2 v-if="result.status === 'healthy'" :size="16" />
        <AlertTriangle v-else :size="16" />
        <strong>{{ statusLabel }}</strong>
        <ElTag size="small" effect="plain" :type="statusType">{{ checkKindLabel }}</ElTag>
      </div>
      <p>{{ result.message }}</p>
      <div class="provider-diagnostic-meta">
        <span>耗时 {{ result.latency_ms }} ms</span>
        <span v-if="result.capability_count != null">发现 {{ result.capability_count }} 项能力</span>
        <span v-if="result.snapshot_state">快照 {{ result.snapshot_state }}</span>
      </div>
      <small v-if="result.failure">{{ result.failure.code }} · 调试参考 {{ result.failure.debug_id }}</small>
    </div>
  </section>
</template>

<style scoped>
.provider-diagnostic {
  display: grid;
  gap: 10px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.provider-diagnostic-action,
.provider-diagnostic-result-heading,
.provider-diagnostic-error,
.provider-diagnostic-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.provider-diagnostic-action {
  justify-content: space-between;
}

.provider-diagnostic-action p,
.provider-diagnostic-result p {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.provider-diagnostic-result,
.provider-diagnostic-error {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-lighter);
}

.provider-diagnostic-result.is-healthy {
  border-color: var(--el-color-success-light-5);
}

.provider-diagnostic-result.is-degraded {
  border-color: var(--el-color-warning-light-5);
}

.provider-diagnostic-result.is-unhealthy,
.provider-diagnostic-error {
  border-color: var(--el-color-danger-light-5);
}

.provider-diagnostic-result-heading {
  flex-wrap: wrap;
}

.provider-diagnostic-meta {
  flex-wrap: wrap;
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.provider-diagnostic-result small {
  display: block;
  margin-top: 6px;
  color: var(--el-text-color-placeholder);
}

.provider-diagnostic-error span {
  flex: 1;
  font-size: 12px;
}

@media (max-width: 640px) {
  .provider-diagnostic-action {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
