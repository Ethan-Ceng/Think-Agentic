<script setup lang="ts">
import { defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterView } from 'vue-router'
import LeftPanel from '@/components/LeftPanel.vue'
import { useSettingsModal } from '@/composables/useSettingsModal'
import { provideSidebar } from '@/composables/useSidebar'
import { useSessionsStore } from '@/stores/sessions'

const sidebarOpen = ref(true)
const sessionsStore = useSessionsStore()
const settingsModal = useSettingsModal()
const settingsOpen = settingsModal.open
const SettingsModal = defineAsyncComponent(() => import('@/components/SettingsModal.vue'))

provideSidebar({
  open: sidebarOpen,
  toggle: () => {
    sidebarOpen.value = !sidebarOpen.value
  },
  close: () => {
    sidebarOpen.value = false
  },
  openSidebar: () => {
    sidebarOpen.value = true
  },
})

onMounted(() => {
  if (window.innerWidth <= 900) {
    sidebarOpen.value = false
  }
  sessionsStore.start()
})

onBeforeUnmount(() => {
  sessionsStore.stop()
})
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': !sidebarOpen }">
    <LeftPanel />
    <button
      v-if="sidebarOpen"
      class="mobile-sidebar-backdrop"
      type="button"
      aria-label="关闭侧边栏"
      @click="sidebarOpen = false"
    />
    <main class="app-main">
      <RouterView />
    </main>
    <SettingsModal v-if="settingsOpen" />
  </div>
</template>
