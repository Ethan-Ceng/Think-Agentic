<script setup lang="ts">
import moment from 'moment'
import { useRoute } from 'vue-router'
import { useCancelPublish, useGetApp, usePublish } from '@/hooks/use-app'
import { onMounted, ref } from 'vue'
import PublishHistoryDrawer from '@/views/space/apps/components/PublishHistoryDrawer.vue'

const route = useRoute()
const publishHistoryDrawerVisible = ref(false)
const { loading, app, loadApp } = useGetApp()
const { loading: publishLoading, handlePublish } = usePublish()
const { handleCancelPublish } = useCancelPublish()

onMounted(async () => await loadApp(String(route.params?.app_id)))
</script>

<template>
  <div class="flex h-full min-h-screen flex-col overflow-hidden bg-slate-50">
    <header
      class="flex min-h-[72px] shrink-0 flex-wrap items-center gap-3 border-b border-slate-200/60 bg-white px-4 py-2 shadow-sm shadow-slate-900/[0.04]"
    >
      <div class="flex min-w-0 flex-1 items-center gap-2">
        <router-link v-slot="{ navigate }" :to="{ name: 'space-apps-list' }" custom>
          <el-button text class="shrink-0 !px-2 text-gray-600" @click="navigate">
            <template #icon>
              <icon-left />
            </template>
            应用列表
          </el-button>
        </router-link>
        <span class="hidden h-4 w-px shrink-0 bg-slate-200 sm:block" aria-hidden="true" />
        <div class="flex min-w-0 items-center gap-3">
          <el-avatar
            :size="40"
            shape="square"
            class="shrink-0 rounded-lg ring-1 ring-slate-200/70 ring-offset-1 ring-offset-white"
            :src="app.icon"
          />
          <div class="flex min-w-0 flex-col justify-center gap-0.5">
            <el-skeleton-item v-if="loading" variant="text" style="width: 140px; height: 20px" />
            <div v-else class="truncate text-base font-semibold text-gray-900">{{ app.name }}</div>
            <div v-if="loading" class="flex flex-wrap items-center gap-2">
              <el-skeleton-item variant="text" style="width: 72px; height: 14px" />
              <el-skeleton-item variant="text" style="width: 56px; height: 14px" />
            </div>
            <div v-else class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-500">
              <span class="inline-flex items-center gap-0.5">
                <icon-user class="text-[13px]" />
                个人空间
              </span>
              <span class="text-gray-300">·</span>
              <span class="inline-flex items-center gap-0.5">
                <icon-schedule class="text-[13px]" />
                {{ app.status === 'draft' ? '草稿' : '已发布' }}
              </span>
              <template v-if="app.draft_updated_at">
                <span class="text-gray-300">·</span>
                <el-tag
                  size="small"
                  effect="plain"
                  class="!h-5 !rounded-md !border-slate-200/80 !bg-slate-50 !px-1.5 !text-[11px] !leading-5 !text-slate-500"
                >
                  保存于 {{ moment(app.draft_updated_at * 1000).format('HH:mm:ss') }}
                </el-tag>
              </template>
            </div>
          </div>
        </div>
      </div>

      <nav
        class="inline-flex max-w-full shrink-0 overflow-x-auto rounded-full bg-slate-200/45 p-0.5 ring-1 ring-slate-200/55 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        aria-label="应用配置"
      >
        <router-link
          :to="{ name: 'space-apps-detail', params: { app_id: String(route.params?.app_id) } }"
          class="rounded-full px-4 py-1.5 text-sm text-gray-600 transition-colors hover:text-gray-900"
          active-class="!bg-white !font-medium !text-blue-700 !shadow-sm"
        >
          编排
        </router-link>
        <router-link
          :to="{ name: 'space-apps-published', params: { app_id: String(route.params?.app_id) } }"
          class="rounded-full px-4 py-1.5 text-sm text-gray-600 transition-colors hover:text-gray-900"
          active-class="!bg-white !font-medium !text-blue-700 !shadow-sm"
        >
          发布配置
        </router-link>
        <router-link
          :to="{ name: 'space-apps-analysis', params: { app_id: String(route.params?.app_id) } }"
          class="rounded-full px-4 py-1.5 text-sm text-gray-600 transition-colors hover:text-gray-900"
          active-class="!bg-white !font-medium !text-blue-700 !shadow-sm"
        >
          统计分析
        </router-link>
        <router-link
          :to="{ name: 'space-apps-tasks', params: { app_id: String(route.params?.app_id) } }"
          :class="[
            'rounded-full px-4 py-1.5 text-sm text-gray-600 transition-colors hover:text-gray-900',
            route.path.includes('/tasks') ? '!bg-white !font-medium !text-blue-700 !shadow-sm' : '',
          ]"
          active-class="!bg-white !font-medium !text-blue-700 !shadow-sm"
        >
          会话记录
        </router-link>
      </nav>

      <div class="flex min-w-0 flex-1 justify-end">
        <el-space :size="8" wrap>
          <el-tooltip content="发布历史" placement="bottom">
            <el-button
              :disabled="loading"
              class="rounded-lg"
              @click="publishHistoryDrawerVisible = true"
            >
              <template #icon>
                <icon-schedule />
              </template>
            </el-button>
          </el-tooltip>
          <el-button-group>
            <el-button
              :disabled="loading"
              :loading="publishLoading"
              type="primary"
              class="rounded-l-lg!"
              @click="
                async () => {
                  const app_id = String(route.params?.app_id)
                  await handlePublish(app_id)
                  await loadApp(app_id)
                }
              "
            >
              更新发布
            </el-button>
            <el-dropdown placement="bottom-end">
              <el-button :disabled="loading" type="primary" class="rounded-r-lg! !min-w-[2rem] !px-2">
                <template #icon>
                  <icon-down />
                </template>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    :disabled="app.status === 'draft'"
                    class="!text-red-700"
                    @click="
                      async () => {
                        const app_id = String(route.params?.app_id)
                        await handleCancelPublish(app_id, async () => await loadApp(app_id))
                      }
                    "
                  >
                    取消发布
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </el-button-group>
        </el-space>
      </div>
    </header>
    <!-- 底部内容区 -->
    <router-view :app="app" class="min-h-0 flex-1 overflow-hidden" />
    <!-- 发布历史抽屉组件 -->
    <publish-history-drawer
      :app="app"
      v-model:visible="publishHistoryDrawerVisible"
      @load-draft-app-config="() => {}"
    />
  </div>
</template>

<style scoped></style>
