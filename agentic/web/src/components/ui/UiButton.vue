<script setup lang="ts">
import { Loader2 } from 'lucide-vue-next'

withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'small' | 'medium'
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
}>(), {
  variant: 'secondary',
  size: 'medium',
  loading: false,
  disabled: false,
  type: 'button',
})
</script>

<template>
  <button
    class="ui-button button"
    :class="[variant, { small: size === 'small', 'is-loading': loading }]"
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <Loader2 v-if="loading" :size="15" class="spin" aria-hidden="true" />
    <slot v-else name="icon" />
    <span class="ui-button-label"><slot /></span>
  </button>
</template>
