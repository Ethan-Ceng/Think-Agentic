<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => (route.path.includes('llm-providers') ? '模型供应商' : '存储配置'))
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-slate-50 px-6">
    <header class="-mx-6 border-b border-slate-200/70 bg-white px-6 pb-4 pt-6">
      <div class="mb-4 flex items-center gap-3">
        <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-white">
          <icon-settings class="text-lg" />
        </div>
        <div>
          <div class="text-xs font-medium uppercase text-gray-400">配置管理</div>
          <h1 class="text-lg font-semibold text-gray-900">{{ title }}</h1>
        </div>
      </div>
      <nav class="inline-flex rounded-full bg-slate-200/60 p-0.5">
        <router-link
          to="/settings/storage"
          class="rounded-full px-4 py-1.5 text-sm text-gray-600"
          active-class="!bg-white !font-medium !text-blue-700 shadow-sm"
        >
          存储
        </router-link>
        <router-link
          to="/settings/llm-providers"
          class="rounded-full px-4 py-1.5 text-sm text-gray-600"
          active-class="!bg-white !font-medium !text-blue-700 shadow-sm"
        >
          模型供应商
        </router-link>
      </nav>
    </header>
    <main class="min-h-0 flex-1 overflow-auto py-5">
      <router-view />
    </main>
  </div>
</template>
