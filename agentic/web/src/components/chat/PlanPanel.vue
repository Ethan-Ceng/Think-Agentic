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
  <section v-if="steps.length > 0" class="plan-panel">
    <button v-if="!expanded" type="button" class="plan-collapsed" @click="expanded = true">
      <span class="plan-current">
        <Loader2 v-if="currentStep?.status === 'running'" :size="16" class="spin" />
        <AlertCircle v-else-if="currentStep?.status === 'failed'" :size="16" />
        <Clock v-else :size="16" />
        <span>{{ currentStep?.description || '暂无步骤' }}</span>
      </span>
      <span class="plan-count">{{ completedCount }} / {{ totalCount }}</span>
      <ChevronUp :size="16" />
    </button>

    <div v-else class="plan-expanded">
      <header>
        <strong>任务进度</strong>
        <span>{{ completedCount }} / {{ totalCount }}</span>
        <button class="icon-button subtle tiny" type="button" @click="expanded = false">
          <ChevronDown :size="16" />
        </button>
      </header>
      <div class="plan-steps">
        <div v-for="step in steps" :key="step.id" class="plan-step" :class="`status-${step.status}`">
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
