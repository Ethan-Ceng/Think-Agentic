<script setup lang="ts">
import { computed } from 'vue'
import {
  ChevronLeft,
  ChevronRight,
  GitFork,
  RefreshCw,
  X,
} from 'lucide-vue-next'
import type {
  BranchFamilyResponse,
  BranchFamilyVariant,
  BranchVersionOperation,
} from '@/lib/api/types'

const props = withDefaults(defineProps<{
  family: BranchFamilyResponse | null
  loading?: boolean
  error?: string
  lineageLabel?: string
  sourceSessionId?: string | null
  sourceSessionTitle?: string | null
  closable?: boolean
}>(), {
  loading: false,
  error: '',
  lineageLabel: '',
  sourceSessionId: null,
  sourceSessionTitle: null,
  closable: false,
})

const emit = defineEmits<{
  navigate: [sessionId: string]
  retry: []
  close: []
  'navigate-source': []
}>()

const operationLabels: Record<BranchVersionOperation, string> = {
  original: '原始版本',
  fork: '手工分支',
  edit: '编辑后的版本',
  regenerate: '重新生成的版本',
}

const currentIndex = computed(() => {
  if (!props.family) return -1
  const explicitIndex = props.family.variants.findIndex(
    variant => variant.session_id === props.family?.current_session_id,
  )
  if (explicitIndex >= 0) return explicitIndex
  return props.family.variants.findIndex(variant => variant.is_current)
})

const currentVariant = computed(
  () => props.family?.variants[currentIndex.value] ?? null,
)
const previousVariant = computed(
  () => props.family?.variants[currentIndex.value - 1] ?? null,
)
const nextVariant = computed(
  () => props.family?.variants[currentIndex.value + 1] ?? null,
)

function describeVariant(variant: BranchFamilyVariant, index: number): string {
  const archived = variant.archived_at ? ' · 已归档' : ''
  return `${index + 1}. ${operationLabels[variant.operation]} · ${variant.title}${archived}`
}

function navigate(sessionId?: string) {
  if (!sessionId || sessionId === props.family?.current_session_id) return
  emit('navigate', sessionId)
}

function handleSelect(event: Event) {
  navigate((event.target as HTMLSelectElement).value)
}
</script>

<template>
  <div
    class="branch-lineage-banner branch-version-navigator"
    role="region"
    aria-label="对话版本导航"
  >
    <GitFork :size="15" aria-hidden="true" />

    <div v-if="loading" class="branch-version-state" role="status">
      <span>正在加载此处的对话版本…</span>
      <small v-if="lineageLabel">{{ lineageLabel }}</small>
    </div>

    <div v-else-if="error" class="branch-version-state is-error" role="alert">
      <span>版本导航加载失败</span>
      <small>{{ error }}</small>
    </div>

    <template v-else-if="family && currentVariant">
      <div class="branch-version-summary">
        <span class="branch-version-operation">
          {{ operationLabels[currentVariant.operation] }}
        </span>
        <span class="branch-version-title" :title="currentVariant.title">
          {{ currentVariant.title }}
        </span>
        <span
          v-if="currentVariant.archived_at"
          class="branch-version-archive"
        >
          已归档
        </span>
      </div>

      <div class="branch-version-controls">
        <button
          class="branch-version-previous"
          type="button"
          aria-label="上一个对话版本"
          title="上一个对话版本"
          :disabled="!previousVariant"
          @click="navigate(previousVariant?.session_id)"
        >
          <ChevronLeft :size="15" aria-hidden="true" />
        </button>
        <span class="branch-version-count" aria-live="polite">
          {{ currentIndex + 1 }} / {{ family.variants.length }}
        </span>
        <button
          class="branch-version-next"
          type="button"
          aria-label="下一个对话版本"
          title="下一个对话版本"
          :disabled="!nextVariant"
          @click="navigate(nextVariant?.session_id)"
        >
          <ChevronRight :size="15" aria-hidden="true" />
        </button>
        <select
          :value="currentVariant.session_id"
          aria-label="选择对话版本"
          title="选择对话版本"
          @change="handleSelect"
        >
          <option
            v-for="(variant, index) in family.variants"
            :key="variant.session_id"
            :value="variant.session_id"
          >
            {{ describeVariant(variant, index) }}
          </option>
        </select>
      </div>
    </template>

    <div v-if="error" class="branch-version-recovery">
      <button
        v-if="sourceSessionId"
        type="button"
        data-action="source"
        @click="emit('navigate-source')"
      >
        返回{{ sourceSessionTitle ? `「${sourceSessionTitle}」` : '原对话' }}
      </button>
      <button type="button" data-action="retry" @click="emit('retry')">
        <RefreshCw :size="14" aria-hidden="true" />
        重试
      </button>
      <button
        v-if="closable"
        type="button"
        data-action="close"
        aria-label="关闭版本导航"
        title="关闭版本导航"
        @click="emit('close')"
      >
        <X :size="14" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>
