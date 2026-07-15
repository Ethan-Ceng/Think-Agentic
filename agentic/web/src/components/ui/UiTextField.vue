<script setup lang="ts">
import { ref } from 'vue'

defineOptions({ inheritAttrs: false })

withDefaults(defineProps<{
  label: string
  type?: 'text' | 'search' | 'email' | 'password' | 'url'
  placeholder?: string
  disabled?: boolean
  compact?: boolean
}>(), {
  type: 'text',
  placeholder: '',
  disabled: false,
  compact: false,
})

const model = defineModel<string>({ default: '' })
const input = ref<HTMLInputElement | null>(null)

function focus() { input.value?.focus() }
defineExpose({ focus })
</script>

<template>
  <label class="ui-text-field" :class="{ compact, disabled }">
    <span v-if="$slots.leading" class="ui-text-field-leading" aria-hidden="true"><slot name="leading" /></span>
    <input
      ref="input"
      v-model="model"
      v-bind="$attrs"
      :type="type"
      :placeholder="placeholder"
      :disabled="disabled"
      :aria-label="label"
    >
    <span v-if="$slots.trailing" class="ui-text-field-trailing"><slot name="trailing" /></span>
  </label>
</template>
