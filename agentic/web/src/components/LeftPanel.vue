<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Files, PanelLeftClose, PanelLeftOpen, Plus } from 'lucide-vue-next'
import SessionList from '@/components/SessionList.vue'
import { useSidebar } from '@/composables/useSidebar'

const router = useRouter()
const sidebar = useSidebar()

function createTask() {
  void router.push('/')
}
</script>

<template>
  <aside class="left-panel" :class="{ collapsed: !sidebar.open.value }">
    <header class="left-panel-header">
      <button class="icon-button" type="button" title="切换侧边栏" @click="sidebar.toggle">
        <PanelLeftClose v-if="sidebar.open.value" :size="18" />
        <PanelLeftOpen v-else :size="18" />
      </button>
    </header>

    <div class="left-panel-content">
      <button class="button new-task-button" type="button" @click="createTask">
        <Plus :size="16" />
        <span>新建任务</span>
        <kbd class="kbd">Ctrl</kbd>
        <kbd class="kbd">K</kbd>
      </button>

      <button class="button left-nav-button" :class="{ active: router.currentRoute.value.name === 'files' }" type="button" @click="router.push('/files')">
        <Files :size="16" />
        <span>文件</span>
      </button>

      <SessionList />
    </div>
  </aside>
</template>
