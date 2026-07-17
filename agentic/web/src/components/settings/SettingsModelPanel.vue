<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Loader2, RotateCcw, ShieldCheck } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { configApi, DEFAULT_LLM_MAX_TOKENS } from '@/lib/api/config'
import type { LLMConfig } from '@/lib/api/types'
import type { SettingsPanelEmits } from './types'

const emit = defineEmits<SettingsPanelEmits>()
const toast = useToast()
const config = ref<LLMConfig>({})
const initialSnapshot = ref('')
const loading = ref(true)
const loadError = ref('')

const dirty = computed(() => Boolean(initialSnapshot.value) && JSON.stringify(config.value) !== initialSnapshot.value)
watch(dirty, (value) => emit('dirty-change', value), { immediate: true })

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    config.value = await configApi.getLLMConfig() || {}
    initialSnapshot.value = JSON.stringify(config.value)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '模型配置加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function save() {
  try {
    config.value = await configApi.updateLLMConfig(config.value)
    initialSnapshot.value = JSON.stringify(config.value)
    toast.success('模型提供商配置保存成功')
    return true
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '模型配置保存失败')
    return false
  }
}

function isDirty() { return dirty.value }
defineExpose({ isDirty, save })
</script>

<template>
  <div v-if="loading" class="center-state" aria-live="polite"><Loader2 :size="22" class="spin" /><span>正在加载模型配置</span></div>
  <div v-else-if="loadError" class="settings-error-state" role="alert">
    <p>{{ loadError }}</p><ElButton @click="load"><RotateCcw :size="15" />重试</ElButton>
  </div>
  <ElForm v-else label-position="top" class="settings-form">
    <header class="settings-section-heading">
      <div><span>模型</span><h3>模型提供商</h3></div>
      <p>连接兼容 OpenAI API 的模型服务，并设置默认生成参数。</p>
    </header>
    <div class="settings-security-note"><ShieldCheck :size="18" /><p>密钥仅提交给配置接口，不会显示在日志或设置摘要中。</p></div>
    <ElFormItem label="提供商基础地址 base_url">
      <ElInput v-model="config.base_url" placeholder="https://api.openai.com/v1" clearable />
      <p class="settings-field-hint">需要兼容 OpenAI API 格式。</p>
    </ElFormItem>
    <ElFormItem label="提供商密钥">
      <ElInput v-model="config.api_key" type="password" placeholder="请输入 API Key" show-password clearable autocomplete="new-password" />
    </ElFormItem>
    <ElFormItem label="模型名称"><ElInput v-model="config.model_name" placeholder="请输入模型名称" clearable /></ElFormItem>
    <div class="settings-field-grid">
      <ElFormItem label="温度 temperature"><ElInputNumber v-model="config.temperature" :min="0" :max="2" :step="0.1" controls-position="right" /></ElFormItem>
      <ElFormItem label="最大输出 Token 数"><ElInputNumber v-model="config.max_tokens" :min="1" :max="128000" :step="1024" :value-on-clear="DEFAULT_LLM_MAX_TOKENS" controls-position="right" /></ElFormItem>
    </div>
  </ElForm>
</template>
