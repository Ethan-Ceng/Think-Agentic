<script setup lang="ts">
withDefaults(defineProps<{
  label: string
  title?: string
  variant?: 'default' | 'subtle' | 'danger'
  size?: 'tiny' | 'medium'
  active?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
}>(), {
  title: undefined,
  variant: 'default',
  size: 'medium',
  active: false,
  disabled: false,
  type: 'button',
})
</script>

<template>
  <button
    class="ui-icon-button icon-button"
    :class="[variant, { tiny: size === 'tiny', active }]"
    :type="type"
    :disabled="disabled"
    :aria-label="label"
    :aria-pressed="active || undefined"
    :title="title || label"
  >
    <slot />
  </button>
</template>
