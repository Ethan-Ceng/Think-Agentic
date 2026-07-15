<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { LogOut } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'

const auth = useAuthStore()
const sessions = useSessionsStore()
const router = useRouter()
withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
const label = computed(() => auth.user?.name || auth.user?.email || '用户')
const email = computed(() => auth.user?.email || '已登录账户')
const initials = computed(() => {
  const parts = label.value.trim().split(/\s+/).filter(Boolean)
  if (parts.length > 1) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return label.value.slice(0, 2).toUpperCase()
})

async function logout() {
  sessions.stop()
  sessions.clear()
  await auth.logout()
  await router.replace('/auth')
}

async function handleCommand(command: string | number | object) {
  if (command === 'logout') await logout()
}
</script>

<template>
  <ElDropdown
    class="user-menu"
    trigger="click"
    placement="right-end"
    popper-class="account-menu-popper"
    @command="handleCommand"
  >
    <button
      class="sidebar-account-button"
      :class="{ compact }"
      type="button"
      :aria-label="`打开 ${label} 的账号菜单`"
      aria-haspopup="menu"
    >
      <span class="account-avatar" aria-hidden="true">{{ initials }}</span>
    </button>
    <template #dropdown>
      <ElDropdownMenu>
        <ElDropdownItem class="account-menu-identity" disabled>
          <span class="account-menu-avatar" aria-hidden="true">{{ initials }}</span>
          <span class="account-menu-copy">
            <strong>{{ label }}</strong>
            <small>{{ email }}</small>
          </span>
        </ElDropdownItem>
        <ElDropdownItem command="logout" divided>
          <LogOut :size="16" aria-hidden="true" />
          <span>退出登录</span>
        </ElDropdownItem>
      </ElDropdownMenu>
    </template>
  </ElDropdown>
</template>
