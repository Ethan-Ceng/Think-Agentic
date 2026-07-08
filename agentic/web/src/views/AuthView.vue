<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { LogIn, UserPlus } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToast()

const mode = ref<'login' | 'register'>('login')
const email = ref('')
const password = ref('')
const name = ref('')
const submitting = ref(false)
const title = computed(() => (mode.value === 'login' ? '登录 MoocManus' : '注册 MoocManus'))
const description = computed(() =>
  mode.value === 'login' ? '使用你的账号继续访问任务和文件' : '创建一个本地账号开始使用增强型 Agent',
)

async function submit() {
  if (submitting.value) return
  submitting.value = true

  try {
    if (mode.value === 'login') {
      await auth.login({
        email: email.value,
        password: password.value,
      })
    } else {
      await auth.register({
        email: email.value,
        password: password.value,
        name: name.value || undefined,
      })
    }

    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '认证失败')
  } finally {
    submitting.value = false
  }
}

function toggleMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-panel">
      <div class="auth-heading">
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <label class="form-field">
          <span>邮箱</span>
          <input v-model.trim="email" type="email" autocomplete="email" required>
        </label>

        <label v-if="mode === 'register'" class="form-field">
          <span>显示名</span>
          <input v-model.trim="name" type="text" autocomplete="name" maxlength="255">
        </label>

        <label class="form-field">
          <span>密码</span>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            minlength="8"
            maxlength="16"
            required
          >
        </label>

        <button class="button primary auth-submit" type="submit" :disabled="submitting">
          <LogIn v-if="mode === 'login'" :size="16" />
          <UserPlus v-else :size="16" />
          {{ submitting ? '处理中...' : mode === 'login' ? '登录' : '注册并进入' }}
        </button>
      </form>

      <button class="link-button auth-switch" type="button" @click="toggleMode">
        {{ mode === 'login' ? '没有账号？注册一个' : '已有账号？返回登录' }}
      </button>
    </section>
  </main>
</template>
