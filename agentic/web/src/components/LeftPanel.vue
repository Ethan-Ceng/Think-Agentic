<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import SidebarPanel from '@/components/navigation/SidebarPanel.vue'
import SidebarRail from '@/components/navigation/SidebarRail.vue'
import { useSidebar } from '@/composables/useSidebar'

const MIN_PANEL_WIDTH = 224
const MAX_PANEL_WIDTH = 384
const WIDTH_STORAGE_KEY = 'agentic.sidebar.panel-width'

const router = useRouter()
const sidebar = useSidebar()
const panelWidth = ref(readPanelWidth())
let resizeFrame = 0

function readPanelWidth() {
  const stored = Number(window.localStorage.getItem(WIDTH_STORAGE_KEY))
  return Number.isFinite(stored)
    ? Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, stored))
    : 272
}

function savePanelWidth() {
  window.localStorage.setItem(WIDTH_STORAGE_KEY, String(panelWidth.value))
}

function createTask() {
  void router.push('/')
  if (window.innerWidth <= 900) sidebar.close()
}

function focusSearch() {
  void router.push('/search')
  if (window.innerWidth <= 900) sidebar.close()
}

function setPanelWidth(width: number) {
  panelWidth.value = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, width))
}

function handleResizePointerDown(event: PointerEvent) {
  if (window.innerWidth <= 900) return
  event.preventDefault()
  const startX = event.clientX
  const startWidth = panelWidth.value

  const handleMove = (moveEvent: PointerEvent) => {
    window.cancelAnimationFrame(resizeFrame)
    resizeFrame = window.requestAnimationFrame(() => {
      setPanelWidth(startWidth + moveEvent.clientX - startX)
    })
  }
  const handleUp = () => {
    window.removeEventListener('pointermove', handleMove)
    window.removeEventListener('pointerup', handleUp)
    document.body.classList.remove('is-resizing-sidebar')
    savePanelWidth()
  }

  document.body.classList.add('is-resizing-sidebar')
  window.addEventListener('pointermove', handleMove)
  window.addEventListener('pointerup', handleUp, { once: true })
}

function handleResizeKeydown(event: KeyboardEvent) {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  setPanelWidth(panelWidth.value + (event.key === 'ArrowRight' ? 16 : -16))
  savePanelWidth()
}

onBeforeUnmount(() => window.cancelAnimationFrame(resizeFrame))
</script>

<template>
  <aside
    class="left-panel"
    :class="{ collapsed: !sidebar.open.value }"
    :style="{ '--sidebar-panel-width': `${panelWidth}px` }"
  >
    <SidebarRail
      :expanded="sidebar.open.value"
      @toggle="sidebar.toggle"
      @search="focusSearch"
    />
    <SidebarPanel
      :expanded="sidebar.open.value"
      @create="createTask"
      @close="sidebar.close"
    />
    <div
      v-if="sidebar.open.value"
      class="sidebar-resizer"
      role="separator"
      aria-label="调整侧边栏宽度"
      aria-orientation="vertical"
      :aria-valuemin="MIN_PANEL_WIDTH"
      :aria-valuemax="MAX_PANEL_WIDTH"
      :aria-valuenow="panelWidth"
      tabindex="0"
      @pointerdown="handleResizePointerDown"
      @keydown="handleResizeKeydown"
    />
  </aside>
</template>
