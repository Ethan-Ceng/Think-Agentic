<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useCredentialStore } from '@/stores/credential'
import type { FormInstance } from 'element-plus'
import { ElMessage } from 'element-plus'
import { usePasswordLogin } from '@/hooks/use-auth'
import { useProvider } from '@/hooks/use-oauth'

// 1.定义自定义组件所需数据
const errorMessage = ref('')
const loginForm = ref({ email: '', password: '' })
const loginFormRef = ref<FormInstance>()
const credentialStore = useCredentialStore()
const router = useRouter()
const { loading: passwordLoginLoading, authorization, handlePasswordLogin } = usePasswordLogin()
const { loading: providerLoading, redirect_url, handleProvider } = useProvider()

// 2.定义忘记密码点击事件
const forgetPassword = () => ElMessage.error('忘记密码请联系管理员')

// 3.定义github第三方授权认证登录
const githubLogin = async () => {
  // 3.1 调用处理器获取提供者重定向地址
  await handleProvider('github')

  // 3.2 跳转到重定向地址
  window.location.href = redirect_url.value
}

// 4.账号密码登录
const handleSubmit = async () => {
  try {
    await loginFormRef.value?.validate()
  } catch {
    return
  }

  try {
    // 4.3 发起账号密码登录，并且将loading设置为true
    await handlePasswordLogin(loginForm.value.email, loginForm.value.password)
    ElMessage.success('登录成功，正在跳转')
    credentialStore.update(authorization.value)
    await router.replace({ path: '/home' })
  } catch (error: any) {
    // 4.4 添加错误信息并清除密码
    errorMessage.value = error.message
    loginForm.value.password = ''
  }
}
</script>

<template>
  <div class="">
    <!-- 顶部标题 -->
    <div class="text-gray-900 font-bold text-2xl leading-8">慕课LLMOps AppBuilder</div>
    <p class="text-base leading-6 text-gray-600">高效开发你的AI原生应用</p>
    <!-- 错误提示占位符 -->
    <div class="h-8 text-red-700 leading-8 line-clamp-1">{{ errorMessage }}</div>
    <!-- 登录表单 -->
    <el-form
      ref="loginFormRef"
      :model="loginForm"
      @submit.prevent="handleSubmit"
      label-position="top"
      size="large"
      class="flex flex-col w-full"
    >
      <el-form-item
        prop="email"
        :rules="[{ type: 'email', required: true, message: '登录账号必须是合法的邮箱' }]"
        :validate-trigger="['change', 'blur-sm']"
      >
        <el-input v-model="loginForm.email" size="large" placeholder="登录账号">
          <template #prefix>
            <icon-user />
          </template>
        </el-input>
      </el-form-item>
      <el-form-item
        prop="password"
        :rules="[{ required: true, message: '账号密码不能为空' }]"
        :validate-trigger="['change', 'blur-sm']"
      >
        <el-input
          v-model="loginForm.password"
          type="password"
          show-password
          size="large"
          placeholder="账号密码"
        >
          <template #prefix>
            <icon-lock />
          </template>
        </el-input>
      </el-form-item>
      <div class="flex w-full flex-col gap-4">
        <div class="flex w-full shrink-0 items-center justify-between">
          <el-checkbox>记住密码</el-checkbox>
          <el-link @click.prevent="forgetPassword">忘记密码?</el-link>
        </div>
        <el-button
          :loading="passwordLoginLoading"
          size="large"
          type="primary"
          native-type="submit"
          class="mx-0! w-full"
        >
          登录
        </el-button>
        <el-divider content-position="center" class="my-0!">第三方授权</el-divider>
        <el-button
          :loading="providerLoading"
          size="large"
          type="info"
          plain
          class="mx-0! w-full"
          @click="githubLogin"
        >
          <template #icon>
            <icon-github />
          </template>
          Github
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<style scoped></style>
