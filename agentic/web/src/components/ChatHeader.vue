<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { PanelLeftOpen } from 'lucide-vue-next'
import { useSidebar } from '@/composables/useSidebar'

const sidebar = useSidebar()
</script>

<template>
  <header class="top-header">
    <div class="top-header-left">
      <button
        v-if="sidebar.mobile.value && !sidebar.open.value"
        class="icon-button"
        type="button"
        title="打开侧边栏"
        @click="sidebar.openSidebar()"
      >
        <PanelLeftOpen :size="18" />
      </button>
      <RouterLink class="brand-mark" to="/" aria-label="MoocManus 首页">MoocManus</RouterLink>
    </div>
  </header>
</template>
