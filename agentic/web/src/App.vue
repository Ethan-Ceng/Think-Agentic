<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import LeftPanel from '@/components/LeftPanel.vue'
import { useSettingsModal } from '@/composables/useSettingsModal'
import { provideSidebar } from '@/composables/useSidebar'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'

const sidebarOpen = ref(true)
const route = useRoute()
const authStore = useAuthStore()
const sessionsStore = useSessionsStore()
const settingsModal = useSettingsModal()
const settingsOpen = settingsModal.open
const SettingsModal = defineAsyncComponent(() => import('@/components/SettingsModal.vue'))
const authRoute = computed(() => route.name === 'auth')

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

onMounted(async () => {
  if (window.innerWidth <= 900) {
    sidebarOpen.value = false
  }
  await authStore.initialize()
  if (authStore.isAuthenticated) {
    sessionsStore.start()
  }
})

onBeforeUnmount(() => {
  sessionsStore.stop()
})

watch(
  () => authStore.isAuthenticated,
  (authenticated) => {
    if (authenticated) {
      sessionsStore.start()
    } else {
      sessionsStore.stop()
    }
  },
)
</script>

<template>
  <RouterView v-if="authRoute" />
  <div v-else class="app-shell" :class="{ 'sidebar-collapsed': !sidebarOpen }">
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
