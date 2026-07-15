<script setup lang="ts">
import { Settings } from 'lucide-vue-next'
import { useSettingsModal } from '@/composables/useSettingsModal'

const settingsModal = useSettingsModal()
</script>

<template>
  <button
    class="icon-button settings-button"
    type="button"
    title="设置"
    aria-label="设置"
    @click="settingsModal.openSettings"
  >
    <Settings :size="18" />
  </button>
</template>
