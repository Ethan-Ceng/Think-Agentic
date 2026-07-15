<script setup lang="ts">
import { computed, ref } from 'vue'
import { AlertCircle, Check, ChevronDown, ChevronUp, Clock, Loader2 } from 'lucide-vue-next'
import type { PlanStep } from '@/lib/api/types'

const props = withDefaults(defineProps<{
  steps?: PlanStep[]
}>(), {
  steps: () => [],
})

const expanded = ref(false)
const completedCount = computed(() => props.steps.filter((step) => step.status === 'completed').length)
const totalCount = computed(() => props.steps.length)
const progressPercentage = computed(() =>
  totalCount.value ? Math.round((completedCount.value / totalCount.value) * 100) : 0,
)
const currentStep = computed(
  () =>
    props.steps.find((step) => step.status === 'running') ||
    props.steps.find((step) => step.status === 'pending') ||
    props.steps.find((step) => step.status === 'failed') ||
    props.steps[0],
)

function getStepStatusLabel(step: PlanStep): string {
  switch (step.status) {
    case 'completed':
      return '已完成'
    case 'running':
      return '进行中'
    case 'failed':
      return '失败'
    default:
      return '等待中'
  }
}
</script>

<template>
  <section v-if="steps.length > 0" class="plan-panel" aria-label="任务执行计划">
    <button
      v-if="!expanded"
      type="button"
      class="plan-collapsed"
      aria-expanded="false"
      @click="expanded = true"
    >
      <span class="plan-current">
        <Loader2 v-if="currentStep?.status === 'running'" :size="16" class="spin" />
        <AlertCircle v-else-if="currentStep?.status === 'failed'" :size="16" />
        <Clock v-else :size="16" />
        <span>{{ currentStep?.description || '暂无步骤' }}</span>
      </span>
      <span class="plan-progress-compact" aria-hidden="true">
        <i :style="{ width: `${progressPercentage}%` }" />
      </span>
      <span class="plan-count">{{ completedCount }} / {{ totalCount }}</span>
      <ChevronUp :size="16" />
    </button>

    <div v-else class="plan-expanded">
      <header>
        <div class="plan-heading">
          <strong>任务执行计划</strong>
          <span>已完成 {{ completedCount }} / {{ totalCount }} 步</span>
        </div>
        <span class="plan-percentage">{{ progressPercentage }}%</span>
        <button class="icon-button subtle tiny" type="button" aria-label="收起任务计划" aria-expanded="true" @click="expanded = false">
          <ChevronDown :size="16" />
        </button>
      </header>
      <div
        class="plan-progress-track"
        role="progressbar"
        aria-label="任务完成进度"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-valuenow="progressPercentage"
      >
        <i :style="{ width: `${progressPercentage}%` }" />
      </div>
      <div class="plan-steps" role="list">
        <div v-for="(step, index) in steps" :key="step.id" class="plan-step" :class="`status-${step.status}`" role="listitem">
          <b class="plan-step-index">{{ index + 1 }}</b>
          <Check v-if="step.status === 'completed'" :size="16" />
          <Loader2 v-else-if="step.status === 'running'" :size="16" class="spin" />
          <AlertCircle v-else-if="step.status === 'failed'" :size="16" />
          <Clock v-else :size="16" />
          <span>{{ step.description }}</span>
          <small>{{ getStepStatusLabel(step) }}</small>
        </div>
      </div>
    </div>
  </section>
</template>
