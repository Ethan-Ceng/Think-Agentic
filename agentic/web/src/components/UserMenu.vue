<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { LogOut } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'

const auth = useAuthStore()
const sessions = useSessionsStore()
const router = useRouter()
const label = computed(() => auth.user?.name || auth.user?.email || '用户')

async function logout() {
  sessions.stop()
  sessions.clear()
  await auth.logout()
  await router.replace('/auth')
}
</script>

<template>
  <div class="user-menu">
    <span class="user-label">{{ label }}</span>
    <button class="icon-button subtle" type="button" title="退出登录" @click="logout">
      <LogOut :size="16" />
    </button>
  </div>
</template>
