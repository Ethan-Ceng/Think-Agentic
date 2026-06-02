<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { LLMModel, LLMProvider } from '@/models/llm-provider'
import {
  createLLMModel,
  createLLMProvider,
  deleteLLMModel,
  deleteLLMProvider,
  getLLMProviders,
  syncSystemLLMProviders,
  updateLLMModel,
  updateLLMProvider,
} from '@/services/llm-provider'

const loading = ref(false)
const syncing = ref(false)
const providerDialogVisible = ref(false)
const modelDialogVisible = ref(false)
const selectedProviderId = ref('')
const editingProviderId = ref('')
const editingModelId = ref('')
const providers = ref<LLMProvider[]>([])

const providerForm = reactive<Record<string, any>>({
  provider: 'openai',
  name: 'OpenAI',
  base_url: 'https://api.openai.com/v1',
  api_key: '',
  enabled: true,
  is_default: false,
  config: {},
})

const modelForm = reactive<Record<string, any>>({
  model: '',
  display_name: '',
  model_type: 'chat',
  features: [],
  context_window: 0,
  max_output_tokens: 0,
  default_parameters: {},
  enabled: true,
  is_default: false,
})

const providerOptions = [
  { label: 'OpenAI', value: 'openai', base_url: 'https://api.openai.com/v1' },
  { label: 'DeepSeek', value: 'deepseek', base_url: 'https://api.deepseek.com' },
  { label: '通义千问', value: 'tongyi', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { label: 'Moonshot', value: 'moonshot', base_url: 'https://api.moonshot.cn/v1' },
  { label: 'Ollama', value: 'ollama', base_url: 'http://localhost:11434/v1' },
  { label: 'Custom', value: 'custom', base_url: '' },
]

const featureOptions = [
  { label: 'Tool Call', value: 'tool_call' },
  { label: 'Agent Thought', value: 'agent_thought' },
  { label: 'Vision', value: 'image_input' },
  { label: 'Embedding', value: 'embedding' },
]

const selectedProvider = computed(() => providers.value.find((item) => item.id === selectedProviderId.value))
const providerHasApiKey = (provider?: LLMProvider) => Boolean(provider?.api_key)

const loadProviders = async () => {
  loading.value = true
  try {
    const res = await getLLMProviders()
    providers.value = res.data
    if (!selectedProviderId.value && providers.value.length > 0) selectedProviderId.value = providers.value[0].id
  } finally {
    loading.value = false
  }
}

const resetProviderForm = (provider?: LLMProvider) => {
  editingProviderId.value = provider?.id || ''
  Object.assign(providerForm, {
    provider: provider?.provider || 'openai',
    name: provider?.name || 'OpenAI',
    base_url: provider?.base_url || 'https://api.openai.com/v1',
    api_key: provider?.api_key || '',
    enabled: provider?.enabled ?? true,
    is_default: provider?.is_default ?? false,
    config: provider?.config || {},
  })
}

const resetModelForm = (model?: LLMModel) => {
  editingModelId.value = model?.id || ''
  Object.assign(modelForm, {
    model: model?.model || '',
    display_name: model?.display_name || '',
    model_type: model?.model_type || 'chat',
    features: model?.features ? [...model.features] : [],
    context_window: model?.context_window || 0,
    max_output_tokens: model?.max_output_tokens || 0,
    default_parameters: model?.default_parameters || {},
    enabled: model?.enabled ?? true,
    is_default: model?.is_default ?? false,
  })
}

const applyProviderTemplate = () => {
  const option = providerOptions.find((item) => item.value === providerForm.provider)
  if (!option) return
  if (!providerForm.name || providerForm.name === 'OpenAI') providerForm.name = option.label
  if (!providerForm.base_url) providerForm.base_url = option.base_url
}

const saveProvider = async () => {
  const payload = { ...providerForm }
  if (editingProviderId.value) {
    await updateLLMProvider(editingProviderId.value, payload)
  } else {
    await createLLMProvider(payload)
  }
  providerDialogVisible.value = false
  ElMessage.success('供应商已保存')
  await loadProviders()
}

const removeProvider = async (provider: LLMProvider) => {
  await ElMessageBox.confirm(`删除供应商 ${provider.name}？`, '确认删除', { type: 'warning' })
  await deleteLLMProvider(provider.id)
  if (selectedProviderId.value === provider.id) selectedProviderId.value = ''
  await loadProviders()
}

const resetSystemProviders = async () => {
  await ElMessageBox.confirm('当前供应商和模型会被系统模型配置替换。', '重置系统模型', { type: 'warning' })
  syncing.value = true
  try {
    const res = await syncSystemLLMProviders({ reset: true })
    providers.value = res.data
    selectedProviderId.value =
      providers.value.find((provider) => provider.is_default)?.id || providers.value[0]?.id || ''
    ElMessage.success('系统模型已同步')
  } finally {
    syncing.value = false
  }
}

const saveModel = async () => {
  if (!selectedProvider.value) return
  const payload = { ...modelForm }
  if (editingModelId.value) {
    await updateLLMModel(selectedProvider.value.id, editingModelId.value, payload)
  } else {
    await createLLMModel(selectedProvider.value.id, payload)
  }
  modelDialogVisible.value = false
  ElMessage.success('模型已保存')
  await loadProviders()
}

const removeModel = async (model: LLMModel) => {
  if (!selectedProvider.value) return
  await ElMessageBox.confirm(`删除模型 ${model.model}？`, '确认删除', { type: 'warning' })
  await deleteLLMModel(selectedProvider.value.id, model.id)
  await loadProviders()
}

onMounted(loadProviders)
</script>

<template>
  <div v-loading="loading" class="mx-auto grid max-w-6xl grid-cols-[280px_minmax(0,1fr)] gap-4">
    <aside class="bg-white p-4 ring-1 ring-slate-200">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-base font-semibold text-gray-900">供应商</h2>
        <div class="flex gap-2">
          <el-button size="small" :loading="syncing" @click="resetSystemProviders">重置系统模型</el-button>
          <el-button
            type="primary"
            size="small"
            @click="
              () => {
                resetProviderForm()
                providerDialogVisible = true
              }
            "
          >
            新增
          </el-button>
        </div>
      </div>
      <button
        v-for="provider in providers"
        :key="provider.id"
        :class="[
          'mb-2 block w-full rounded-md border px-3 py-2 text-left',
          selectedProviderId === provider.id ? 'border-blue-300 bg-blue-50' : 'border-slate-200 hover:bg-slate-50',
        ]"
        @click="selectedProviderId = provider.id"
      >
        <div class="flex items-start justify-between gap-2">
          <span class="min-w-0 flex-1 truncate text-sm font-medium text-gray-900">{{ provider.name }}</span>
          <div class="flex shrink-0 flex-wrap justify-end gap-1">
            <el-tag v-if="provider.is_default" size="small">默认</el-tag>
            <el-tag :type="providerHasApiKey(provider) ? 'success' : 'warning'" size="small">
              密钥{{ providerHasApiKey(provider) ? '已配置' : '未配置' }}
            </el-tag>
          </div>
        </div>
        <div class="mt-1 truncate text-xs text-gray-500">{{ provider.provider }} · {{ provider.base_url }}</div>
      </button>
    </aside>

    <main class="min-w-0 bg-white p-5 ring-1 ring-slate-200">
      <template v-if="selectedProvider">
        <div class="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <h2 class="truncate text-base font-semibold text-gray-900">{{ selectedProvider.name }}</h2>
            <p class="mt-1 truncate text-sm text-gray-500">{{ selectedProvider.base_url }}</p>
            <div class="mt-2 text-sm text-gray-600">
              <span>Provider: {{ selectedProvider.provider }}</span>
            </div>
          </div>
          <div class="flex shrink-0 flex-col items-end gap-2">
            <div class="flex flex-wrap justify-end gap-2">
              <el-tag v-if="selectedProvider.is_default" size="small">默认</el-tag>
              <el-tag :type="providerHasApiKey(selectedProvider) ? 'success' : 'warning'" size="small">
                密钥{{ providerHasApiKey(selectedProvider) ? '已配置' : '未配置' }}
              </el-tag>
            </div>
            <div class="flex gap-2">
              <el-button
                @click="
                  () => {
                    resetProviderForm(selectedProvider)
                    providerDialogVisible = true
                  }
                "
              >
                编辑供应商
              </el-button>
              <el-button type="danger" plain @click="removeProvider(selectedProvider)">删除</el-button>
            </div>
          </div>
        </div>

        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold text-gray-700">模型</h3>
          <el-button
            type="primary"
            size="small"
            @click="
              () => {
                resetModelForm()
                modelDialogVisible = true
              }
            "
          >
            新增模型
          </el-button>
        </div>

        <el-table :data="selectedProvider.models" stripe>
          <el-table-column prop="model" label="模型" min-width="160" />
          <el-table-column prop="display_name" label="显示名称" min-width="140" />
          <el-table-column prop="model_type" label="类型" width="100" />
          <el-table-column label="能力" min-width="180">
            <template #default="{ row }">
              <el-space wrap>
                <el-tag v-for="feature in row.features" :key="feature" size="small">{{ feature }}</el-tag>
              </el-space>
            </template>
          </el-table-column>
          <el-table-column prop="context_window" label="上下文" width="100" />
          <el-table-column prop="max_output_tokens" label="输出上限" width="100" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                {{ row.enabled ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button
                type="primary"
                link
                @click="
                  () => {
                    resetModelForm(row)
                    modelDialogVisible = true
                  }
                "
              >
                编辑
              </el-button>
              <el-button type="danger" link @click="removeModel(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
      <el-empty v-else description="暂无模型供应商" />
    </main>

    <el-dialog v-model="providerDialogVisible" width="560px" title="供应商">
      <el-form label-position="top">
        <el-form-item label="Provider">
          <el-select v-model="providerForm.provider" class="w-full" @change="applyProviderTemplate">
            <el-option v-for="item in providerOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="providerForm.name" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="providerForm.base_url" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="providerForm.api_key" show-password />
          <p class="mt-1 text-xs text-gray-500">
            已配置的密钥会显示为 ********；保存时保持 ******** 不会覆盖原密钥，清空后保存会删除密钥。
          </p>
        </el-form-item>
        <div class="flex gap-6">
          <el-checkbox v-model="providerForm.enabled">启用</el-checkbox>
          <el-checkbox v-model="providerForm.is_default">默认供应商</el-checkbox>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="providerDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveProvider">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="modelDialogVisible" width="620px" title="模型">
      <el-form label-position="top">
        <el-form-item label="模型名">
          <el-input v-model="modelForm.model" placeholder="gpt-4o-mini" />
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="modelForm.display_name" />
        </el-form-item>
        <div class="grid grid-cols-2 gap-3">
          <el-form-item label="类型">
            <el-select v-model="modelForm.model_type" class="w-full">
              <el-option label="Chat" value="chat" />
              <el-option label="Embedding" value="embedding" />
              <el-option label="Rerank" value="rerank" />
            </el-select>
          </el-form-item>
          <el-form-item label="能力">
            <el-select v-model="modelForm.features" class="w-full" multiple>
              <el-option v-for="item in featureOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <el-form-item label="上下文窗口">
            <el-input-number v-model="modelForm.context_window" :min="0" class="w-full" />
          </el-form-item>
          <el-form-item label="最大输出 Token">
            <el-input-number v-model="modelForm.max_output_tokens" :min="0" class="w-full" />
          </el-form-item>
        </div>
        <div class="flex gap-6">
          <el-checkbox v-model="modelForm.enabled">启用</el-checkbox>
          <el-checkbox v-model="modelForm.is_default">默认模型</el-checkbox>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="modelDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveModel">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
