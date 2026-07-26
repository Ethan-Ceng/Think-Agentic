<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import LeftPanel from '@/components/LeftPanel.vue'
import { useSettingsModal } from '@/composables/useSettingsModal'
import { provideSidebar } from '@/composables/useSidebar'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'
import { useProjectsStore } from '@/stores/projects'
import type { SidebarSection } from '@/composables/useSidebar'

const SIDEBAR_STORAGE_KEY = 'agentic.sidebar.expanded'
const MOBILE_BREAKPOINT = 900
const storedSidebarState = window.localStorage.getItem(SIDEBAR_STORAGE_KEY)
const sidebarOpen = ref(storedSidebarState === null ? true : storedSidebarState === 'true')
const sidebarSection = ref<SidebarSection>('sessions')
const isMobile = ref(window.innerWidth <= MOBILE_BREAKPOINT)
const route = useRoute()
const authStore = useAuthStore()
const sessionsStore = useSessionsStore()
const projectsStore = useProjectsStore()
const settingsModal = useSettingsModal()
const settingsOpen = settingsModal.open
const SettingsModal = defineAsyncComponent(() => import('@/components/SettingsModal.vue'))
const authRoute = computed(() => route.name === 'auth')
let activeStoreUserId: string | null = null

provideSidebar({
  open: sidebarOpen,
  section: sidebarSection,
  mobile: isMobile,
  toggle: (section) => {
    if (section && (!sidebarOpen.value || sidebarSection.value !== section)) {
      sidebarSection.value = section
      sidebarOpen.value = true
      return
    }
    sidebarOpen.value = !sidebarOpen.value
  },
  close: () => {
    sidebarOpen.value = false
  },
  openSidebar: (section) => {
    if (section) sidebarSection.value = section
    sidebarOpen.value = true
  },
})

onMounted(async () => {
  if (isMobile.value) {
    sidebarOpen.value = false
  }
  window.addEventListener('resize', handleViewportResize)
  window.addEventListener('keydown', handleGlobalKeydown)
  await authStore.initialize()
  syncAuthenticatedStores()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleViewportResize)
  window.removeEventListener('keydown', handleGlobalKeydown)
  sessionsStore.stop()
})

function handleViewportResize() {
  const nextMobile = window.innerWidth <= MOBILE_BREAKPOINT
  if (nextMobile && !isMobile.value && sidebarOpen.value) {
    sidebarOpen.value = false
  }
  isMobile.value = nextMobile
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && window.innerWidth <= MOBILE_BREAKPOINT && sidebarOpen.value) {
    sidebarOpen.value = false
  }
}

function syncAuthenticatedStores() {
  if (!authStore.isAuthenticated) {
    sessionsStore.stop()
    projectsStore.clear()
    activeStoreUserId = null
    return
  }

  sessionsStore.start()
  const userId = authStore.user?.id ?? null
  if (userId && activeStoreUserId === userId) return
  activeStoreUserId = userId
  projectsStore.clear()
  void projectsStore.load().catch(() => {
    // The sidebar exposes a safe fallback and retry state.
  })
}

watch(sidebarOpen, (expanded) => {
  if (!isMobile.value) {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(expanded))
  }
})

watch(
  () => [authStore.isAuthenticated, authStore.user?.id] as const,
  syncAuthenticatedStores,
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
    <main class="app-main" :inert="isMobile && sidebarOpen">
      <RouterView />
    </main>
    <SettingsModal v-if="settingsOpen" />
  </div>
</template>
