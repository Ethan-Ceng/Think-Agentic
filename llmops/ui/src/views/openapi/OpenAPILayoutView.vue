<script setup lang="ts">
import { useRoute } from 'vue-router'
import { ref } from 'vue'

const route = useRoute()
const create_api_key = ref(false)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col overflow-hidden bg-slate-50">
    <header
      class="sticky top-0 z-20 shrink-0 border-b border-slate-200/60 bg-white/85 px-6 pb-4 pt-6 shadow-sm shadow-slate-900/[0.03] backdrop-blur-md"
    >
      <div class="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div class="flex min-w-0 items-center gap-3">
          <div
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-violet-600 to-blue-600 text-white shadow-md shadow-violet-600/20 ring-1 ring-white/20"
          >
            <icon-link class="text-xl" />
          </div>
          <div class="min-w-0">
            <div class="text-xs font-medium uppercase tracking-wide text-slate-400">开发者</div>
            <h1 class="truncate text-lg font-semibold leading-tight text-slate-900">开放 API</h1>
            <p class="mt-0.5 truncate text-xs text-slate-500">
              利用开放 API 与企业业务、已发布的 Agent 能力对接
            </p>
          </div>
        </div>
      </div>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <nav
          class="inline-flex gap-0.5 rounded-full bg-slate-200/50 p-0.5 ring-1 ring-slate-200/60"
          aria-label="开放 API 导航"
        >
          <router-link
            to="/openapi"
            class="rounded-full px-3.5 py-1.5 text-sm text-slate-600 transition-colors hover:text-slate-900"
            exact-active-class="!bg-white !font-medium !text-blue-700 !shadow-sm"
          >
            快速开始
          </router-link>
          <router-link
            to="/openapi/api-keys"
            class="rounded-full px-3.5 py-1.5 text-sm text-slate-600 transition-colors hover:text-slate-900"
            active-class="!bg-white !font-medium !text-blue-700 !shadow-sm"
          >
            秘钥
          </router-link>
        </nav>
        <el-button
          v-if="route.path.startsWith('/openapi/api-keys')"
          type="primary"
          class="rounded-lg"
          @click="create_api_key = true"
        >
          <template #icon>
            <icon-plus />
          </template>
          新增秘钥
        </el-button>
      </div>
    </header>
    <div class="min-h-0 flex-1 overflow-hidden px-6 pb-6 pt-4">
      <router-view v-model:create_api_key="create_api_key" />
    </div>
  </div>
</template>

<style scoped></style>
