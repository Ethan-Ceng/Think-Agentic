<script setup lang="ts">
import { CircleAlert, Inbox, Loader2 } from 'lucide-vue-next'

withDefaults(defineProps<{
  kind?: 'loading' | 'empty' | 'error'
  title?: string
  description?: string
  compact?: boolean
}>(), {
  kind: 'empty',
  title: '',
  description: '',
  compact: false,
})
</script>

<template>
  <div
    class="ui-state"
    :class="[`is-${kind}`, { compact }]"
    :role="kind === 'error' ? 'alert' : 'status'"
    :aria-live="kind === 'loading' ? 'polite' : undefined"
  >
    <span class="ui-state-icon" aria-hidden="true">
      <Loader2 v-if="kind === 'loading'" :size="22" class="spin" />
      <CircleAlert v-else-if="kind === 'error'" :size="24" />
      <slot v-else name="icon"><Inbox :size="24" /></slot>
    </span>
    <div class="ui-state-copy">
      <strong v-if="title">{{ title }}</strong>
      <p v-if="description">{{ description }}</p>
      <slot />
    </div>
    <div v-if="$slots.actions" class="ui-state-actions"><slot name="actions" /></div>
  </div>
</template>
