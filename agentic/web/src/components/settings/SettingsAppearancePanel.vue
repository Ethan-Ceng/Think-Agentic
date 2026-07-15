<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Laptop, Moon, Sun } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { getThemePreference, saveThemePreference } from '@/lib/theme'
import type { ThemePreference } from '@/lib/theme'
import type { SettingsPanelEmits } from './types'

const emit = defineEmits<SettingsPanelEmits>()
const toast = useToast()
const initial = ref<ThemePreference>(getThemePreference())
const preference = ref<ThemePreference>(initial.value)
const dirty = computed(() => preference.value !== initial.value)

const options = [
  { value: 'system' as const, title: '跟随系统', description: '自动使用设备的浅色或深色外观', icon: Laptop },
  { value: 'light' as const, title: '浅色', description: '始终使用明亮背景与深色文字', icon: Sun },
  { value: 'dark' as const, title: '深色', description: '始终使用低亮度深色界面', icon: Moon },
]

watch(dirty, (value) => emit('dirty-change', value), { immediate: true })

async function save() {
  saveThemePreference(preference.value)
  initial.value = preference.value
  toast.success('外观偏好已保存')
  return true
}

function isDirty() { return dirty.value }
defineExpose({ isDirty, save })
</script>

<template>
  <section class="settings-list">
    <header class="settings-section-heading">
      <div><span>个人偏好</span><h3>外观</h3></div>
      <p>主题偏好保存在当前浏览器中，不会影响其他设备。</p>
    </header>
    <div class="settings-choice-grid" role="radiogroup" aria-label="界面主题">
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        role="radio"
        class="settings-choice-card"
        :class="{ active: preference === option.value }"
        :aria-checked="preference === option.value"
        @click="preference = option.value"
      >
        <span class="settings-choice-icon"><component :is="option.icon" :size="20" /></span>
        <span><strong>{{ option.title }}</strong><small>{{ option.description }}</small></span>
      </button>
    </div>
  </section>
</template>
