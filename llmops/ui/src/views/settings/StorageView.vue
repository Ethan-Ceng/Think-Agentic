<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSettings, upsertSetting } from '@/services/setting'

const loading = ref(false)
const saving = ref(false)
const defaultProvider = ref('local')
const activeProvider = ref('local')
const forms = reactive<Record<string, Record<string, any>>>({
  local: { root: 'storage/uploads', base_url: 'http://localhost:3000/upload-files' },
  qcloud_cos: { bucket: '', region: '', domain: '', secret_id: '', secret_key: '' },
  aliyun_oss: { bucket: '', region: '', endpoint: '', domain: '', access_key: '', secret_key: '' },
})

const providerOptions = [
  { label: '本地存储', value: 'local' },
  { label: '腾讯云 COS', value: 'qcloud_cos' },
  { label: '阿里云 OSS', value: 'aliyun_oss' },
]

const providerTitle = computed(() => providerOptions.find((item) => item.value === activeProvider.value)?.label)

const loadSettings = async () => {
  loading.value = true
  try {
    const res = await getSettings('storage')
    for (const setting of res.data) {
      if (setting.key === 'default') defaultProvider.value = setting.value?.provider || 'local'
      if (forms[setting.key]) forms[setting.key] = { ...forms[setting.key], ...setting.value }
    }
  } finally {
    loading.value = false
  }
}

const saveProvider = async () => {
  saving.value = true
  try {
    await upsertSetting('storage', activeProvider.value, { value: forms[activeProvider.value], enabled: true })
    ElMessage.success('存储配置已保存')
  } finally {
    saving.value = false
  }
}

const saveDefault = async () => {
  saving.value = true
  try {
    await upsertSetting('storage', 'default', { value: { provider: defaultProvider.value }, enabled: true })
    ElMessage.success('默认存储已更新')
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <div v-loading="loading" class="mx-auto max-w-5xl space-y-4">
    <section class="bg-white p-5 ring-1 ring-slate-200">
      <div class="mb-4 flex items-center justify-between">
        <div>
          <h2 class="text-base font-semibold text-gray-900">默认存储</h2>
          <p class="mt-1 text-sm text-gray-500">新上传文件会记录上传时使用的 storage provider。</p>
        </div>
        <el-button type="primary" :loading="saving" @click="saveDefault">保存默认</el-button>
      </div>
      <el-radio-group v-model="defaultProvider">
        <el-radio-button v-for="item in providerOptions" :key="item.value" :label="item.value">
          {{ item.label }}
        </el-radio-button>
      </el-radio-group>
    </section>

    <section class="grid grid-cols-[220px_minmax(0,1fr)] gap-4">
      <aside class="bg-white p-3 ring-1 ring-slate-200">
        <button
          v-for="item in providerOptions"
          :key="item.value"
          :class="[
            'mb-1 flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm',
            activeProvider === item.value ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-slate-50',
          ]"
          @click="activeProvider = item.value"
        >
          <span>{{ item.label }}</span>
          <el-tag v-if="defaultProvider === item.value" size="small" type="primary">默认</el-tag>
        </button>
      </aside>

      <div class="bg-white p-5 ring-1 ring-slate-200">
        <div class="mb-5 flex items-center justify-between">
          <h2 class="text-base font-semibold text-gray-900">{{ providerTitle }}</h2>
          <el-button type="primary" :loading="saving" @click="saveProvider">保存配置</el-button>
        </div>

        <el-form label-position="top">
          <template v-if="activeProvider === 'local'">
            <el-form-item label="存储根目录">
              <el-input v-model="forms.local.root" />
            </el-form-item>
            <el-form-item label="访问 Base URL">
              <el-input v-model="forms.local.base_url" />
            </el-form-item>
          </template>

          <template v-else-if="activeProvider === 'qcloud_cos'">
            <el-form-item label="Bucket">
              <el-input v-model="forms.qcloud_cos.bucket" />
            </el-form-item>
            <el-form-item label="Region">
              <el-input v-model="forms.qcloud_cos.region" />
            </el-form-item>
            <el-form-item label="Domain">
              <el-input v-model="forms.qcloud_cos.domain" placeholder="https://cdn.example.com" />
            </el-form-item>
            <el-form-item label="Secret ID">
              <el-input v-model="forms.qcloud_cos.secret_id" show-password />
            </el-form-item>
            <el-form-item label="Secret Key">
              <el-input v-model="forms.qcloud_cos.secret_key" show-password />
            </el-form-item>
          </template>

          <template v-else>
            <el-form-item label="Bucket">
              <el-input v-model="forms.aliyun_oss.bucket" />
            </el-form-item>
            <el-form-item label="Region">
              <el-input v-model="forms.aliyun_oss.region" />
            </el-form-item>
            <el-form-item label="Endpoint">
              <el-input v-model="forms.aliyun_oss.endpoint" />
            </el-form-item>
            <el-form-item label="Domain">
              <el-input v-model="forms.aliyun_oss.domain" placeholder="https://cdn.example.com" />
            </el-form-item>
            <el-form-item label="Access Key">
              <el-input v-model="forms.aliyun_oss.access_key" show-password />
            </el-form-item>
            <el-form-item label="Secret Key">
              <el-input v-model="forms.aliyun_oss.secret_key" show-password />
            </el-form-item>
          </template>
        </el-form>
      </div>
    </section>
  </div>
</template>
