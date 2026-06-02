<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import moment from 'moment'
import { apiPrefix, typeMap } from '@/config'
import { useGetBuiltinTools, useGetCategories } from '@/hooks/use-builtin-tool'

const { categories, loadCategories } = useGetCategories()
const { loading: getBuiltinToolsLoading, builtin_tools, loadBuiltinTools } = useGetBuiltinTools()
const category = ref<string>('all')
const search_word = ref<string>('')
const showIdx = ref<number>(-1)
const filterBuiltinTools = computed(() => {
  return builtin_tools.value.filter((item: any) => {
    const matchCategory = category.value === 'all' || item.category === category.value
    const matchSearchWord =
      search_word.value === '' || item.label.toLowerCase().includes(search_word.value.toLowerCase())

    return matchCategory && matchSearchWord
  })
})

onMounted(() => {
  loadCategories()
  loadBuiltinTools()
})
</script>

<template>
  <div v-loading="getBuiltinToolsLoading" class="flex h-full min-h-0 flex-col bg-slate-50">
    <header
      class="sticky top-0 z-10 shrink-0 border-b border-slate-200/60 bg-white/85 px-6 pb-4 pt-6 shadow-sm shadow-slate-900/[0.03] backdrop-blur-md"
    >
      <div class="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div class="flex min-w-0 items-center gap-3">
          <div
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-amber-500 to-orange-600 text-white shadow-md shadow-orange-500/25 ring-1 ring-white/20"
          >
            <icon-tool class="text-xl" />
          </div>
          <div class="min-w-0">
            <div class="text-xs font-medium uppercase tracking-wide text-slate-400">模板中心</div>
            <h1 class="truncate text-lg font-semibold leading-tight text-slate-900">插件广场</h1>
            <p class="mt-0.5 truncate text-xs text-slate-500">内置工具提供方与能力说明</p>
          </div>
        </div>
        <router-link :to="{ name: 'space-tools-list', query: { create_type: 'tool' } }">
          <el-button type="primary" class="rounded-lg">
            <template #icon>
              <icon-plus />
            </template>
            创建自定义插件
          </el-button>
        </router-link>
      </div>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <nav
          class="inline-flex max-w-full flex-wrap gap-0.5 rounded-full bg-slate-200/50 p-0.5 ring-1 ring-slate-200/60"
          aria-label="插件分类"
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
          placeholder="按插件名称筛选…"
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
        <el-col
          v-for="(builtinTool, idx) in filterBuiltinTools"
          :key="builtinTool.name"
          :span="6"
          class="mb-5"
        >
          <el-card
            shadow="hover"
            class="cursor-pointer rounded-xl border border-slate-200/50 transition-shadow hover:border-slate-200 hover:shadow-md"
            @click="showIdx = Number(idx)"
          >
            <div class="mb-3 flex items-center gap-3">
              <el-avatar
                :size="40"
                shape="square"
                class="ring-1 ring-slate-100"
                :style="{ backgroundColor: builtinTool.background }"
              >
                <img
                  :src="`${apiPrefix}/builtin-tools/${builtinTool.name}/icon`"
                  :alt="builtinTool.name"
                />
              </el-avatar>
              <div class="flex min-w-0 flex-col">
                <div class="truncate text-base font-bold text-slate-900">{{ builtinTool.label }}</div>
                <div class="line-clamp-1 text-xs text-slate-500">
                  提供商 {{ builtinTool.name }} · {{ builtinTool.tools.length }} 插件
                </div>
              </div>
            </div>
            <div class="mb-2 line-clamp-4 h-[72px] text-sm leading-[18px] text-slate-600">
              {{ builtinTool.description }}
            </div>
            <div class="flex items-center gap-1.5">
              <el-avatar :size="18" class="bg-blue-700">
                <icon-user />
              </el-avatar>
              <div class="text-xs text-slate-400">
                慕课 · 发布时间
                {{ moment(builtinTool.created_at * 1000).format('MM-DD HH:mm') }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col v-if="filterBuiltinTools.length === 0" :span="24">
          <el-empty
            description="没有可用的内置插件"
            class="flex h-[400px] flex-col items-center justify-center"
          />
        </el-col>
      </el-row>

      <el-drawer
        :model-value="showIdx !== -1"
        :width="350"
        title="工具详情"
        class="store-tool-drawer"
        :drawer-style="{
          background: 'rgb(248 250 252)',
          borderLeft: '1px solid rgb(226 232 240 / 0.85)',
        }"
        @update:model-value="(open: boolean) => { if (!open) showIdx = -1 }"
      >
        <div v-if="showIdx != -1" class="text-slate-800">
          <div class="mb-3 flex items-center gap-3">
            <el-avatar
              :size="40"
              shape="square"
              class="ring-1 ring-slate-200/80"
              :style="{ backgroundColor: filterBuiltinTools[showIdx].background }"
            >
              <img
                :src="`${apiPrefix}/builtin-tools/${filterBuiltinTools[showIdx].name}/icon`"
                :alt="filterBuiltinTools[showIdx].name"
              />
            </el-avatar>
            <div class="flex min-w-0 flex-col">
              <div class="truncate text-base font-bold text-slate-900">
                {{ filterBuiltinTools[showIdx].label }}
              </div>
              <div class="line-clamp-1 text-xs text-slate-500">
                提供商 {{ filterBuiltinTools[showIdx].name }} ·
                {{ filterBuiltinTools[showIdx].tools.length }} 插件
              </div>
            </div>
          </div>
          <div class="mb-4 text-sm leading-relaxed text-slate-600">
            {{ filterBuiltinTools[showIdx].description }}
          </div>
          <hr class="my-4 border-slate-200/80" />
          <div class="flex flex-col gap-2">
            <div class="text-xs font-medium text-slate-500">
              包含 {{ filterBuiltinTools[showIdx].tools.length }} 个工具
            </div>
            <el-card
              v-for="tool in filterBuiltinTools[showIdx].tools"
              :key="tool.name"
              class="flex cursor-pointer flex-col rounded-xl border border-slate-200/60 bg-white shadow-sm"
            >
              <div class="mb-2 font-bold text-slate-900">{{ tool.label }}</div>
              <div class="text-xs text-slate-600">{{ tool.description }}</div>
              <div v-if="tool.inputs.length > 0" class="">
                <div class="my-4 flex items-center gap-2">
                  <div class="text-xs font-bold text-slate-500">参数</div>
                  <hr class="flex-1 border-slate-200/80" />
                </div>
                <div class="flex flex-col gap-4">
                  <div v-for="input in tool.inputs" :key="input.name" class="flex flex-col gap-2">
                    <div class="flex items-center gap-2 text-xs">
                      <div class="font-bold text-slate-900">{{ input.name }}</div>
                      <div class="text-slate-500">{{ typeMap[input.type] }}</div>
                      <div v-if="input.required" class="text-red-600">必填</div>
                    </div>
                    <div class="text-xs text-slate-500">{{ input.description }}</div>
                  </div>
                </div>
              </div>
            </el-card>
          </div>
        </div>
      </el-drawer>
    </div>
  </div>
</template>

<style scoped>
.store-search-input :deep(.el-input__wrapper) {
  border-radius: 9999px;
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.06);
}
</style>
