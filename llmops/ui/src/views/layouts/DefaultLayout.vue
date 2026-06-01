<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useLogout } from '@/hooks/use-auth'
import LayoutSidebar from './components/LayoutSidebar.vue'
import { useGetCurrentUser } from '@/hooks/use-account'
import { useCredentialStore } from '@/stores/credential'
import { useAccountStore } from '@/stores/account'
import SettingModal from '@/views/layouts/components/SettingModal.vue'
import { appDescription, appLogoUrl, appTitle } from '@/config'

// 1.定义页面所需数据
const settingModalVisible = ref(false)
const router = useRouter()
const credentialStore = useCredentialStore()
const accountStore = useAccountStore()
const { handleLogout: handleLogoutHook } = useLogout()
const { current_user, loadCurrentUser } = useGetCurrentUser()

// 2.退出登录按钮
const handleLogout = async () => {
  // 2.1 发起请求退出登录
  await handleLogoutHook()

  // 2.2 清空授权凭证+账号信息
  credentialStore.clear()
  accountStore.clear()

  // 2.3 跳转到授权认证页面
  await router.replace({ name: 'auth-login' })
}

// 3.页面DOM加载完成时获取当前登录账号信息
onMounted(async () => {
  await loadCurrentUser()
  accountStore.update(current_user.value)
})
</script>

<template>
  <el-container class="h-full">
    <!-- 侧边栏 -->
    <el-aside width="240px" class="min-h-screen bg-slate-100/90 shadow-none">
      <div
        class="flex h-full flex-col justify-between rounded-xl border border-slate-200/60 bg-white px-2 py-4 shadow-sm shadow-slate-900/5"
      >
        <!-- 上半部分 -->
        <div class="">
          <!-- 顶部品牌：环境变量 VITE_TITLE / VITE_DESCRIPTION；可选 VITE_APP_LOGO 图片 -->
          <router-link
            to="/home"
            class="brand-logo mb-5 flex items-center gap-2.5 rounded-lg px-2 py-2 transition-colors hover:bg-gray-100"
          >
            <div
              v-if="appLogoUrl"
              class="brand-logo__mark flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gray-100 ring-1 ring-gray-200/80"
            >
              <img :src="appLogoUrl" :alt="appTitle" class="h-full w-full object-contain p-0.5" />
            </div>
            <div
              v-else
              class="brand-logo__mark flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-linear-to-br from-indigo-500 to-violet-600 text-white shadow-sm ring-1 ring-indigo-500/20"
            >
              <icon-bulb class="text-lg" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="truncate text-sm font-semibold leading-tight text-gray-900">
                {{ appTitle }}
              </div>
              <div
                v-if="appDescription"
                class="truncate text-xs leading-tight text-gray-500"
              >
                {{ appDescription }}
              </div>
            </div>
          </router-link>
          <!-- 创建AI应用按钮 -->
          <router-link :to="{ name: 'space-apps-list', query: { create_type: 'app' } }">
            <el-button type="primary" class="rounded-lg mb-4 w-full">
              <icon-plus class="mr-1" />
              创建 AI 应用
            </el-button>
          </router-link>
          <!-- 侧边栏导航 -->
          <layout-sidebar />
        </div>
        <!-- 账号设置 -->
        <el-dropdown placement="top-start">
          <div
            class="flex items-center p-2 gap-2 transition-all cursor-pointer rounded-lg hover:bg-gray-100"
          >
            <!-- 头像 -->
            <el-avatar
              :size="32"
              class="text-sm bg-blue-700"
              :src="accountStore.account.avatar"
            >
              {{ accountStore.account.name[0] }}
            </el-avatar>
            <!-- 个人信息 -->
            <div class="flex flex-col">
              <div class="text-sm text-gray-900">{{ accountStore.account.name }}</div>
              <div class="text-xs text-gray-500">{{ accountStore.account.email }}</div>
            </div>
          </div>
          <template #dropdown><el-dropdown-menu>
            <el-dropdown-item @click="settingModalVisible = true">
              <template #icon>
                <icon-settings />
              </template>
              账号设置
            </el-dropdown-item>
            <el-dropdown-item @click="handleLogout">
              <template #icon>
                <icon-poweroff />
              </template>
              退出登录
            </el-dropdown-item>
          </el-dropdown-menu></template></el-dropdown>
      </div>
    </el-aside>
    <!-- 右侧内容 -->
    <el-main class="layout-main bg-slate-50">
      <router-view />
    </el-main>
    <!-- 设置模态窗 -->
    <setting-modal v-model:visible="settingModalVisible" />
  </el-container>
</template>

<style scoped lang="scss">
.layout-main {
  padding: 0;
}
</style>
