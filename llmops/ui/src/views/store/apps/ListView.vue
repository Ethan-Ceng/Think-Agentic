<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import {
  useAddBuiltinAppToSpace,
  useGetBuiltinAppCategories,
  useGetBuiltinApps,
} from '@/hooks/use-builtin-app'
import moment from 'moment/moment'

const category = ref('all')
const search_word = ref('')
const { categories, loadBuiltinAppCategories } = useGetBuiltinAppCategories()
const { loading: getBuiltinAppsLoading, apps, loadBuiltinApps } = useGetBuiltinApps()
const { handleAddBuiltinAppToSpace } = useAddBuiltinAppToSpace()
const filterApps = computed(() => {
  return apps.value.filter((item) => {
    const matchCategory = category.value === 'all' || item.category === category.value
    const matchSearchWord =
      search_word.value === '' || item.name.toLowerCase().includes(search_word.value.toLowerCase())

    return matchCategory && matchSearchWord
  })
})

onMounted(() => {
  loadBuiltinAppCategories()
  loadBuiltinApps()
})
</script>

<template>
  <div v-loading="getBuiltinAppsLoading" class="flex h-full min-h-0 flex-col bg-slate-50">
    <header
      class="sticky top-0 z-10 shrink-0 border-b border-slate-200/60 bg-white/85 px-6 pb-4 pt-6 shadow-sm shadow-slate-900/[0.03] backdrop-blur-md"
    >
      <div class="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div class="flex min-w-0 items-center gap-3">
          <div
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-sky-600 to-blue-700 text-white shadow-md shadow-blue-600/20 ring-1 ring-white/20"
          >
            <icon-apps class="text-xl" />
          </div>
          <div class="min-w-0">
            <div class="text-xs font-medium uppercase tracking-wide text-slate-400">模板中心</div>
            <h1 class="truncate text-lg font-semibold leading-tight text-slate-900">应用广场</h1>
            <p class="mt-0.5 truncate text-xs text-slate-500">浏览内置 Agent，一键添加到工作区</p>
          </div>
        </div>
      </div>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <nav
          class="inline-flex max-w-full flex-wrap gap-0.5 rounded-full bg-slate-200/50 p-0.5 ring-1 ring-slate-200/60"
          aria-label="应用分类"
        >
          <button
            type="button"
            class="rounded-full px-3.5 py-1.5 text-sm transition-colors"
            :class="
              category === 'all'
                ? '!bg-white font-medium !text-blue-700 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            "
            @click="category = 'all'"
          >
            全部
          </button>
          <button
            v-for="item in categories"
            :key="item.category"
            type="button"
            class="rounded-full px-3.5 py-1.5 text-sm transition-colors"
            :class="
              category === item.category
                ? '!bg-white font-medium !text-blue-700 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            "
            @click="category = item.category"
          >
            {{ item.name }}
          </button>
        </nav>
        <el-input
          v-model="search_word"
          clearable
          placeholder="按应用名称筛选…"
          class="store-search-input w-full min-w-[200px] max-w-[280px]"
        >
          <template #suffix>
            <el-icon class="text-slate-400" :size="16">
              <Search />
            </el-icon>
          </template>
        </el-input>
      </div>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto px-6 pb-6 pt-4 scrollbar-y-sleek">
      <el-row :gutter="20" class="flex-1">
        <el-col v-for="app in filterApps" :key="app.id" :span="6" class="mb-5">
          <el-card
            shadow="hover"
            class="cursor-pointer rounded-xl border border-slate-200/50 transition-shadow hover:border-slate-200 hover:shadow-md"
          >
            <div class="mb-3 flex items-center gap-3">
              <el-avatar :size="40" shape="square" class="ring-1 ring-slate-100" :src="app.icon" />
              <div class="flex flex-1 justify-between">
                <div class="flex min-w-0 flex-col">
                  <div class="truncate text-base font-bold text-slate-900">{{ app.name }}</div>
                  <div class="line-clamp-1 text-xs text-slate-500">
                    {{ app.model_config.provider }} · {{ app.model_config.model }}
                  </div>
                </div>
                <el-dropdown placement="bottom-end">
                  <el-button type="text" size="small" class="rounded-lg !text-slate-600">
                    <template #icon>
                      <icon-more />
                    </template>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item @click="async () => await handleAddBuiltinAppToSpace(app.id)">
                        添加到工作区
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
            <div class="mb-2 line-clamp-4 h-[72px] break-all text-sm leading-[18px] text-slate-600">
              {{ app.description }}
            </div>
            <div class="flex items-center gap-1.5">
              <el-avatar :size="18" class="bg-blue-700">
                <icon-user />
              </el-avatar>
              <div class="text-xs text-slate-400">
                慕课 · 发布时间
                {{ moment(app.created_at * 1000).format('MM-DD HH:mm') }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col v-if="filterApps.length === 0" :span="24">
          <el-empty
            description="没有可用的内置Agent智能体"
            class="flex h-[400px] flex-col items-center justify-center"
          />
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<style scoped>
.store-search-input :deep(.el-input__wrapper) {
  border-radius: 9999px;
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.06);
}
</style>
