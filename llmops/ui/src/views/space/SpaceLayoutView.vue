<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const createType = ref<string>('')
const searchWord = ref(String(route.query?.search_word ?? ''))

type SpaceSection = 'apps' | 'tools' | 'workflows' | 'datasets'

const activeSection = computed((): SpaceSection | null => {
  const p = route.path
  if (p.startsWith('/space/apps')) return 'apps'
  if (p.startsWith('/space/tools')) return 'tools'
  if (p.startsWith('/space/workflows')) return 'workflows'
  if (p.startsWith('/space/datasets')) return 'datasets'
  return null
})

const pageHead = computed(() => {
  switch (activeSection.value) {
    case 'apps':
      return {
        title: 'AI 应用',
        subtitle: '创建与编排 Agent 智能体',
      }
    case 'tools':
      return {
        title: '插件',
        subtitle: 'OpenAPI 工具与自定义能力',
      }
    case 'workflows':
      return {
        title: '工作流',
        subtitle: '可视化编排业务流程',
      }
    case 'datasets':
      return {
        title: '知识库',
        subtitle: '文档分段与检索配置',
      }
    default:
      return { title: '个人空间', subtitle: '管理你的 AI 资源' }
  }
})

const runSearch = () => {
  const q = String(searchWord.value ?? '').trim()
  router.push({
    path: route.path,
    query: q ? { search_word: q } : {},
  })
}

watch(
  () => route.query?.search_word,
  () => {
    searchWord.value = String(route.query?.search_word ?? '')
  },
)
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-slate-50 px-6">
    <header
      class="sticky top-0 z-20 -mx-6 border-b border-slate-200/60 bg-white/85 px-6 pb-4 pt-6 shadow-sm shadow-slate-900/[0.03] backdrop-blur-md"
    >
      <div class="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div class="flex min-w-0 items-center gap-3">
          <div
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-600/15 ring-1 ring-white/20"
          >
            <icon-apps v-if="activeSection === 'apps'" class="text-xl" />
            <icon-tool v-else-if="activeSection === 'tools'" class="text-xl" />
            <icon-branch v-else-if="activeSection === 'workflows'" class="text-xl" />
            <icon-storage v-else-if="activeSection === 'datasets'" class="text-xl" />
            <icon-user v-else class="text-xl" />
          </div>
          <div class="min-w-0">
            <div class="text-xs font-medium uppercase tracking-wide text-gray-400">个人空间</div>
            <h1 class="truncate text-lg font-semibold leading-tight text-gray-900">
              {{ pageHead.title }}
            </h1>
            <p class="mt-0.5 truncate text-xs text-gray-500">{{ pageHead.subtitle }}</p>
          </div>
        </div>
        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <el-button
            v-if="route.path.startsWith('/space/apps')"
            type="primary"
            class="rounded-lg"
            @click="createType = 'app'"
          >
            <template #icon>
              <icon-plus />
            </template>
            创建 AI 应用
          </el-button>
          <el-button
            v-if="route.path.startsWith('/space/tools')"
            type="primary"
            class="rounded-lg"
            @click="createType = 'tool'"
          >
            <template #icon>
              <icon-plus />
            </template>
            创建自定义插件
          </el-button>
          <el-button
            v-if="route.path.startsWith('/space/workflows')"
            type="primary"
            class="rounded-lg"
            @click="createType = 'workflow'"
          >
            <template #icon>
              <icon-plus />
            </template>
            创建工作流
          </el-button>
          <el-button
            v-if="route.path.startsWith('/space/datasets')"
            type="primary"
            class="rounded-lg"
            @click="createType = 'dataset'"
          >
            <template #icon>
              <icon-plus />
            </template>
            创建知识库
          </el-button>
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3">
        <nav
          class="inline-flex gap-0.5 rounded-full bg-slate-200/50 p-0.5 ring-1 ring-slate-200/60"
          aria-label="空间导航"
        >
          <router-link
            to="/space/apps"
            class="rounded-full px-3.5 py-1.5 text-sm text-gray-600 transition-colors hover:text-gray-900"
            active-class="!bg-white !text-blue-700 !shadow-sm !font-medium"
          >
            AI 应用
          </router-link>
          <router-link
            to="/space/tools"
            class="rounded-full px-3.5 py-1.5 text-sm text-gray-600 transition-colors hover:text-gray-900"
            active-class="!bg-white !text-blue-700 !shadow-sm !font-medium"
          >
            插件
          </router-link>
          <router-link
            to="/space/workflows"
            class="rounded-full px-3.5 py-1.5 text-sm text-gray-600 transition-colors hover:text-gray-900"
            active-class="!bg-white !text-blue-700 !shadow-sm !font-medium"
          >
            工作流
          </router-link>
          <router-link
            to="/space/datasets"
            class="rounded-full px-3.5 py-1.5 text-sm text-gray-600 transition-colors hover:text-gray-900"
            active-class="!bg-white !text-blue-700 !shadow-sm !font-medium"
          >
            知识库
          </router-link>
        </nav>

        <el-input
          v-model="searchWord"
          clearable
          placeholder="搜索当前列表…"
          class="space-search-input w-full min-w-[200px] max-w-[280px]"
          @clear="runSearch"
          @keyup.enter="runSearch"
        >
          <template #suffix>
            <el-icon
              class="cursor-pointer text-gray-400 transition-colors hover:text-blue-600"
              :size="16"
              @click="runSearch"
            >
              <Search />
            </el-icon>
          </template>
        </el-input>
      </div>
    </header>

    <div class="min-h-0 flex-1 overflow-hidden pt-4">
      <router-view v-model:create-type="createType" />
    </div>
  </div>
</template>

<style scoped>
.space-search-input :deep(.el-input__wrapper) {
  border-radius: 9999px;
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.06);
}
</style>
