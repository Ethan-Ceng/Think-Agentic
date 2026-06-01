<script setup lang="ts">
import moment from 'moment/moment'
import { useCopyApp, useDeleteApp, useGetAppsWithPage } from '@/hooks/use-app'
import { onMounted, ref, watch } from 'vue'
import { useAccountStore } from '@/stores/account'
import CreateOrUpdateAppModal from './components/CreateOrUpdateAppModal.vue'
import { useRoute } from 'vue-router'

// 1.定义页面所需数据
const route = useRoute()
const props = defineProps({
  createType: { type: String, default: '', required: true },
})
const emits = defineEmits(['update:create-type'])
const createOrUpdateAppModalVisible = ref(false)
const updateAppId = ref('')
const accountStore = useAccountStore()
const { handleCopyApp } = useCopyApp()
const {
  loading: getAppsWithPageLoading,
  loadingMore: getAppsWithPageLoadingMore,
  apps,
  paginator,
  loadApps,
} = useGetAppsWithPage()
const { handleDeleteApp } = useDeleteApp()

// 2.定义滚动数据分页处理器
const handleScroll = async (event: Event) => {
  // 1.获取滚动距离、可滚动的最大距离、客户端/浏览器窗口的高度
  const { scrollTop, scrollHeight, clientHeight } = event.target as HTMLElement

  // 2.判断是否滑动到底部
  if (scrollTop + clientHeight >= scrollHeight - 10) {
    if (getAppsWithPageLoading.value || getAppsWithPageLoadingMore.value) return
    await loadApps(false, String(route.query?.search_word ?? ''))
  }
}

// 页面DOM加载完毕后执行
onMounted(async () => {
  // 初始化apps数据
  await loadApps(true, String(route.query?.search_word ?? ''))
})

watch(
  () => props.createType,
  (newValue) => {
    if (newValue === 'app') {
      updateAppId.value = ''
      createOrUpdateAppModalVisible.value = true
      emits('update:create-type', '')
    }
  },
)

watch(
  () => route.query?.search_word,
  (newValue) => loadApps(true, String(newValue ?? '')),
)

watch(
  () => route.query?.create_type,
  (newValue) => {
    if (newValue === 'app') {
      updateAppId.value = ''
      createOrUpdateAppModalVisible.value = true
    }
  },
  { immediate: true },
)
</script>

<template>
  <div
    v-loading="getAppsWithPageLoading"
    class="block h-full w-full scrollbar-y-sleek overflow-scroll"
    @scroll="handleScroll"
  >
    <!-- 底部应用列表 -->
    <el-row :gutter="20" class="flex-1">
      <!-- 有数据的UI状态 -->
      <el-col v-for="app in apps" :key="app.id" :span="6" class="mb-5">
        <el-card shadow="hover" class="cursor-pointer rounded-lg transition-shadow">
          <!-- 顶部应用名称 -->
          <div class="flex items-center gap-3 mb-3">
            <!-- 左侧图标 -->
            <el-avatar :size="40" shape="square" :src="app.icon" />
            <!-- 右侧App信息 -->
            <div class="flex flex-1 justify-between">
              <div class="flex flex-col">
                <router-link
                  :to="{
                    name: 'space-apps-detail',
                    params: { app_id: app.id },
                  }"
                  class="text-base text-gray-900 font-bold"
                >
                  {{ app.name }}
                  <icon-check-circle-fill
                    v-if="app.status === 'published'"
                    class="text-green-700"
                  />
                </router-link>
                <div class="text-xs text-gray-500 line-clamp-1">
                  {{ app.model_config.provider }} · {{ app.model_config.model }}
                </div>
              </div>
              <!-- 操作按钮 -->
              <el-dropdown placement="bottom-end">
                <el-button type="text" size="small" class="rounded-lg text-gray-700!">
                  <template #icon>
                    <icon-more />
                  </template>
                </el-button>
                <template #dropdown><el-dropdown-menu>
                  <router-link :to="{ name: 'space-apps-analysis', params: { app_id: app.id } }">
                    <el-dropdown-item>分析</el-dropdown-item>
                  </router-link>
                  <el-dropdown-item
                    @click="
                      () => {
                        updateAppId = app.id
                        createOrUpdateAppModalVisible = true
                      }
                    "
                  >
                    编辑应用
                  </el-dropdown-item>
                  <el-dropdown-item @click="async () => await handleCopyApp(app.id)">创建副本</el-dropdown-item>
                  <el-dropdown-item
                    class="text-red-700"
                    @click="
                      () =>
                        handleDeleteApp(
                          app.id,
                          async () => await loadApps(true, String(route.query?.search_word ?? '')),
                        )
                    "
                  >
                    删除
                  </el-dropdown-item>
                </el-dropdown-menu></template></el-dropdown>
            </div>
          </div>
          <!-- App的描述信息 -->
          <div class="leading-[18px] text-gray-500 h-[72px] line-clamp-4 mb-2 break-all">
            {{ app.description.trim() === '' ? app.preset_prompt : app.description }}
          </div>
          <!-- 应用的归属者信息 -->
          <div class="flex items-center gap-1.5">
            <el-avatar :size="18" class="bg-blue-700">
              <icon-user />
            </el-avatar>
            <div class="text-xs text-gray-400">
              {{ accountStore.account.name }} · 最近编辑
              {{ moment(app.created_at * 1000).format('MM-DD HH:mm') }}
            </div>
          </div>
        </el-card>
      </el-col>
      <!-- 没数据的UI状态 -->
      <el-col v-if="apps.length === 0" :span="24">
        <el-empty
          description="没有可用的Agent智能体"
          class="h-[400px] flex flex-col items-center justify-center"
        />
      </el-col>
    </el-row>
    <!-- 加载器 -->
    <el-row v-if="paginator.total_page >= 2">
      <!-- 还有更多页：首屏用整页 v-loading；翻页仅用底部提示，避免中间一直全屏遮罩 -->
      <el-col v-if="paginator.current_page <= paginator.total_page" :span="24" class="text-center">
        <el-space class="my-4">
          <div />
          <div class="text-gray-400">
            {{
              getAppsWithPageLoadingMore
                ? '加载中…'
                : '向下滑动加载更多'
            }}
          </div>
        </el-space>
      </el-col>
      <!-- 数据加载完成 -->
      <el-col v-else :span="24" class="text-center">
        <div class="text-gray-400 my-4">数据已加载完成</div>
      </el-col>
    </el-row>
    <!-- 新建/修改模态窗 -->
    <create-or-update-app-modal
      v-model:visible="createOrUpdateAppModalVisible"
      v-model:app_id="updateAppId"
      :callback="() => loadApps(true, String(route.query?.search_word ?? ''))"
    />
  </div>
</template>

<style scoped></style>
