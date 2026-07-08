import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '@/lib/api/auth'
import { clearAuthToken, getAuthToken, setAuthToken } from '@/lib/api/auth-token'
import type { LoginParams, RegisterParams, UserInfo } from '@/lib/api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const token = ref(getAuthToken())
  const initialized = ref(false)
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value && user.value))

  function applyAuth(accessToken: string, nextUser: UserInfo): void {
    token.value = accessToken
    user.value = nextUser
    setAuthToken(accessToken)
  }

  async function initialize(): Promise<void> {
    if (initialized.value) return
    initialized.value = true

    if (!token.value) return
    try {
      user.value = await authApi.me()
    } catch {
      token.value = ''
      user.value = null
      clearAuthToken()
    }
  }

  async function login(params: LoginParams): Promise<void> {
    loading.value = true
    try {
      const auth = await authApi.login(params)
      applyAuth(auth.access_token, auth.user)
    } finally {
      loading.value = false
    }
  }

  async function register(params: RegisterParams): Promise<void> {
    loading.value = true
    try {
      const auth = await authApi.register(params)
      applyAuth(auth.access_token, auth.user)
    } finally {
      loading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      if (token.value) {
        await authApi.logout()
      }
    } catch {
      // Local logout should still complete if the token is already invalid.
    } finally {
      token.value = ''
      user.value = null
      clearAuthToken()
    }
  }

  return {
    user,
    token,
    initialized,
    loading,
    isAuthenticated,
    initialize,
    login,
    register,
    logout,
  }
})
