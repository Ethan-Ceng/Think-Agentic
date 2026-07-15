<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { CheckCircle2, Database, Loader2, ShieldCheck } from 'lucide-vue-next'
import { configApi } from '@/lib/api/config'
import type { StorageConfig, StorageProvider } from '@/lib/api/types'
import { useToast } from '@/composables/useToast'
import type { SettingsPanelEmits } from '@/components/settings/types'

const emit = defineEmits<SettingsPanelEmits>()
const toast = useToast()
const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const initialSnapshot = ref('')
const activeProvider = ref<StorageProvider>('local')
const config = ref<StorageConfig>({
  default_provider: 'local',
  providers: {
    local: { enabled: true },
    qcloud_cos: { enabled: false, bucket: '', region: '', domain: '', scheme: 'https', secret_id: '', secret_key: '' },
    aliyun_oss: { enabled: false, bucket: '', endpoint: '', region: '', domain: '', path_prefix: '', access_key_id: '', access_key_secret: '' },
  },
})

const options: Array<{ value: StorageProvider; label: string; description: string }> = [
  { value: 'local', label: '本地存储', description: '服务器持久化卷，路径由管理员配置' },
  { value: 'qcloud_cos', label: '腾讯云 COS', description: '使用用户级 COS Bucket 保存新文件' },
  { value: 'aliyun_oss', label: '阿里云 OSS', description: '使用用户级 OSS Bucket 保存新文件' },
]
const activeOption = computed(() => options.find((item) => item.value === activeProvider.value)!)
const dirty = computed(() => Boolean(initialSnapshot.value) && JSON.stringify(config.value) !== initialSnapshot.value)
watch(dirty, (value) => emit('dirty-change', value), { immediate: true })

onMounted(async () => {
  try {
    config.value = await configApi.getStorageConfig()
    activeProvider.value = config.value.default_provider
    initialSnapshot.value = JSON.stringify(config.value)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '存储配置加载失败')
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  try {
    config.value = await configApi.updateStorageConfig(config.value)
    initialSnapshot.value = JSON.stringify(config.value)
    toast.success('存储配置已保存')
    return true
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '存储配置保存失败')
    return false
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  try {
    config.value = await configApi.updateStorageConfig(config.value)
    initialSnapshot.value = JSON.stringify(config.value)
    await configApi.testStorageConfig(activeProvider.value)
    toast.success(`${activeOption.value.label}连接测试成功`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '连接测试失败')
  } finally {
    testing.value = false
  }
}

function setDefault(provider: StorageProvider) {
  config.value.default_provider = provider
  config.value.providers[provider].enabled = true
}

function isDirty() { return dirty.value }
defineExpose({ isDirty, save })
</script>

<template>
  <div v-if="loading" class="center-state"><Loader2 :size="22" class="spin" /></div>
  <section v-else class="storage-settings">
    <header class="settings-section-heading storage-heading">
      <div>
        <span>存储</span>
        <h3>文件存储</h3>
        <p>默认 Provider 只影响新文件，历史文件继续从原存储位置读取。</p>
      </div>
    </header>

    <div class="storage-provider-list">
      <button
        v-for="item in options"
        :key="item.value"
        type="button"
        class="storage-provider-card"
        :class="{ active: activeProvider === item.value }"
        @click="activeProvider = item.value"
      >
        <Database :size="18" />
        <span><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span>
        <ElTag v-if="config.default_provider === item.value" size="small" type="success">默认</ElTag>
      </button>
    </div>

    <div class="storage-provider-form">
      <div class="storage-provider-title">
        <div><h3>{{ activeOption.label }}</h3><p>{{ activeOption.description }}</p></div>
        <ElSwitch
          v-if="activeProvider !== 'local'"
          v-model="config.providers[activeProvider].enabled"
          active-text="启用"
          inactive-text="停用"
        />
      </div>

      <div v-if="activeProvider === 'local'" class="storage-local-note">
        <ShieldCheck :size="20" />
        <div><strong>本地存储由部署管理员维护</strong><p>普通用户不能修改服务器目录，避免越权访问主机文件。</p></div>
      </div>

      <ElForm v-else-if="activeProvider === 'qcloud_cos'" label-position="top" class="settings-form compact">
        <div class="storage-form-grid">
          <ElFormItem label="Bucket"><ElInput v-model="config.providers.qcloud_cos.bucket" /></ElFormItem>
          <ElFormItem label="Region"><ElInput v-model="config.providers.qcloud_cos.region" placeholder="ap-guangzhou" /></ElFormItem>
        </div>
        <ElFormItem label="自定义 Domain（可选）"><ElInput v-model="config.providers.qcloud_cos.domain" placeholder="https://cdn.example.com" /></ElFormItem>
        <div class="storage-form-grid">
          <ElFormItem label="Secret ID"><ElInput v-model="config.providers.qcloud_cos.secret_id" type="password" show-password /></ElFormItem>
          <ElFormItem label="Secret Key"><ElInput v-model="config.providers.qcloud_cos.secret_key" type="password" show-password /></ElFormItem>
        </div>
      </ElForm>

      <ElForm v-else label-position="top" class="settings-form compact">
        <div class="storage-form-grid">
          <ElFormItem label="Bucket"><ElInput v-model="config.providers.aliyun_oss.bucket" /></ElFormItem>
          <ElFormItem label="Region（可选）"><ElInput v-model="config.providers.aliyun_oss.region" placeholder="cn-hangzhou" /></ElFormItem>
        </div>
        <ElFormItem label="Endpoint"><ElInput v-model="config.providers.aliyun_oss.endpoint" placeholder="https://oss-cn-hangzhou.aliyuncs.com" /></ElFormItem>
        <ElFormItem label="自定义 Domain（可选）"><ElInput v-model="config.providers.aliyun_oss.domain" placeholder="https://cdn.example.com" /></ElFormItem>
        <ElFormItem label="对象路径前缀（可选）"><ElInput v-model="config.providers.aliyun_oss.path_prefix" placeholder="agentic-files" /></ElFormItem>
        <div class="storage-form-grid">
          <ElFormItem label="AccessKey ID"><ElInput v-model="config.providers.aliyun_oss.access_key_id" type="password" show-password /></ElFormItem>
          <ElFormItem label="AccessKey Secret"><ElInput v-model="config.providers.aliyun_oss.access_key_secret" type="password" show-password /></ElFormItem>
        </div>
      </ElForm>

      <div class="storage-actions">
        <ElButton v-if="activeProvider !== 'local'" :loading="testing" @click="testConnection">
          <CheckCircle2 :size="15" /> 测试连接
        </ElButton>
        <ElButton
          type="primary"
          :disabled="config.default_provider === activeProvider || !config.providers[activeProvider].enabled"
          @click="setDefault(activeProvider)"
        >设为默认</ElButton>
      </div>
    </div>
  </section>
</template>

<style scoped>
.storage-settings { display: flex; flex-direction: column; gap: 18px; }
.storage-heading, .storage-provider-title, .storage-actions { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.storage-heading p, .storage-provider-title p, .storage-local-note p { color: var(--text-secondary); font-size: 13px; margin-top: 4px; }
.storage-provider-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.storage-provider-card { display: flex; align-items: center; gap: 10px; padding: 12px; border: 1px solid var(--border-light); border-radius: var(--radius-md); background: var(--surface-primary); color: var(--text-primary); text-align: left; cursor: pointer; }
.storage-provider-card:hover { border-color: var(--border-heavy); background: var(--surface-secondary); }
.storage-provider-card:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.storage-provider-card.active { border-color: var(--accent-primary); box-shadow: 0 0 0 1px var(--accent-primary); }
.storage-provider-card span { min-width: 0; flex: 1; display: flex; flex-direction: column; }
.storage-provider-card small { color: var(--text-secondary); font-size: 11px; margin-top: 3px; }
.storage-provider-form { padding: 18px; border: 1px solid var(--border-light); border-radius: var(--radius-lg); background: var(--surface-primary); }
.storage-provider-title { margin-bottom: 18px; }
.storage-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.storage-local-note { display: flex; gap: 12px; padding: 16px; border-radius: var(--radius-md); background: var(--surface-secondary); }
.storage-actions { justify-content: flex-end; margin-top: 8px; }
@media (max-width: 760px) { .storage-provider-list, .storage-form-grid { grid-template-columns: 1fr; } }
</style>
