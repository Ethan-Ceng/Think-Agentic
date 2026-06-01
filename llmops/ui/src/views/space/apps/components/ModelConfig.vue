<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { apiPrefix } from '@/config'
import { useGetLanguageModel, useGetLanguageModels } from '@/hooks/use-language-model'
import { useUpdateDraftAppConfig } from '@/hooks/use-app'

// 1.定义自定义组件所需数据
const props = defineProps({
  app_id: { type: String, default: '', required: true },
  model_config: {
    type: Object,
    default: () => {
      return {}
    },
    required: true,
  },
  dialog_round: { type: Number, default: 3, required: true },
})
const emits = defineEmits(['update:model_config'])
const form = ref<any>({})
const {
  loading: getLanguageModelLoading,
  language_model,
  loadLanguageModel,
} = useGetLanguageModel()
const { language_models, loadLanguageModels } = useGetLanguageModels()
const { handleUpdateDraftAppConfig } = useUpdateDraftAppConfig()
const modelOptions = computed(() => {
  return language_models.value.map((language_model) => {
    return {
      isGroup: true,
      label: language_model.label,
      options: (language_model.models ?? []).map((model) => {
        return {
          label: model.label,
          value: `${language_model.name}/${model.model_name}`,
        }
      }),
    }
  })
})

/** Shown in el-select #label — do not rely on scoped slot props here: #label can bind to ElFormItem (only passes `label`). */
const selectedModelParts = computed(() => {
  const raw =
    typeof form.value?.selectValue === 'string' ? form.value.selectValue : ''
  const i = raw.indexOf('/')
  if (i > 0) {
    return { provider: raw.slice(0, i), model: raw.slice(i + 1) }
  }
  return {
    provider: String(form.value?.provider ?? ''),
    model: String(form.value?.model ?? ''),
  }
})

// 2.定义选择模型处理器
const changeModel = (value: any): any => {
  // 2.1 使用/拆分出提供商+模型名字
  const [provider_name, model_name] = value.split('/')

  // 2.2 发起请求获取模型详情
  loadLanguageModel(provider_name, model_name).then(() => {
    // 2.3 重新赋值parameters
    const parameters = language_model.value?.parameters
    if (!Array.isArray(parameters)) return
    form.value.parameters = parameters.reduce(
      (acc: Record<string, any>, parameter: Record<string, any>) => {
        acc[parameter.name] = parameter.default ?? null
        return acc
      },
      {} as Record<string, any>,
    )
  })
}

// 3.触发器隐藏处理器，提交数据进行更新
const hideModelTrigger = () => {
  // 3.1 处理表单数据
  const [provider_name, model_name] = form.value.selectValue.split('/')

  // 3.2 提取表单模型配置
  const model_config = {
    provider: provider_name,
    model: model_name,
    parameters: form.value.parameters,
  }

  // 3.3 提交应用草稿配置更新
  handleUpdateDraftAppConfig(props.app_id, {
    model_config: model_config,
    dialog_round: form.value.dialog_round,
  }).then(() => emits('update:model_config', model_config))
}

watch(
  () => props.model_config,
  (newValue) => {
    // 1.完成表单数据初始化
    form.value['selectValue'] = `${newValue?.provider}/${newValue.model}`
    form.value['provider'] = newValue?.provider
    form.value['model'] = newValue?.model
    form.value['parameters'] = newValue?.parameters

    // 2.请求语言模型详情API接口
    newValue?.provider && loadLanguageModel(String(newValue?.provider), String(newValue?.model))
  },
  { immediate: true },
)

watch(
  () => props.dialog_round,
  (newValue) => {
    form.value['dialog_round'] = newValue
  },
  { immediate: true },
)

onMounted(() => {
  loadLanguageModels()
})
</script>

<template>
  <el-popover
    v-if="props.model_config?.provider"
    trigger="click"
    placement="bottom-start"
    :offset="12"
    :width="480"
    @hide="hideModelTrigger"
  >
    <template #reference>
      <div
        class="flex cursor-pointer items-center gap-2 rounded-xl border border-slate-200/80 bg-slate-50/90 px-2.5 py-1.5 transition hover:border-indigo-200/80 hover:bg-white hover:shadow-sm"
      >
        <el-avatar
          :size="16"
          shape="square"
          :src="`${apiPrefix}/language-models/${form?.provider}/icon`"
        />
        <span class="text-xs font-medium text-slate-700">{{ form?.model }}</span>
        <icon-down class="text-slate-400" />
      </div>
    </template>
    <div class="max-w-[90vw] rounded-xl border border-slate-100 bg-white px-5 py-4 shadow-lg shadow-slate-900/10">
      <div class="mb-4 text-base font-semibold text-slate-900">模型设置</div>
      <el-form :model="form" label-position="top" size="small" class="model-config-form w-full">
        <el-form-item label="模型" required>
          <el-select
            v-model="form.selectValue"
            :options="modelOptions"
            class="w-full rounded-lg"
            placeholder="请选择 Agent 使用的大语言模型"
            @change="changeModel"
          >
            <template #label>
              <div class="flex items-center gap-2">
                <el-avatar
                  :size="16"
                  shape="square"
                  :src="`${apiPrefix}/language-models/${selectedModelParts.provider}/icon`"
                />
                <el-space :size="4">
                  <span class="text-xs text-slate-700">{{ selectedModelParts.provider }}</span>
                  <span class="text-xs text-slate-400">·</span>
                  <span class="text-xs text-slate-700">{{ selectedModelParts.model }}</span>
                </el-space>
              </div>
            </template>
            <template #option="{ data, value, label }">
              <div class="flex items-center gap-2">
                <el-avatar
                  :size="16"
                  shape="square"
                  :src="`${apiPrefix}/language-models/${String(data?.value ?? value ?? '').split('/')[0]}/icon`"
                />
                <span class="py-2 text-xs text-slate-700">{{ data?.label ?? label }}</span>
              </div>
            </template>
          </el-select>
        </el-form-item>

        <div v-loading="getLanguageModelLoading" class="w-full">
          <el-form-item
            v-for="parameter in language_model?.parameters"
            :key="parameter.name"
            class="!mb-3"
          >
            <template #label>
              <span class="inline-flex items-center gap-1 text-slate-600">
                {{ parameter?.label }}
                <el-tooltip v-if="parameter?.help" :content="String(parameter.help)" placement="top">
                  <icon-question-circle class="cursor-help text-slate-400" />
                </el-tooltip>
              </span>
            </template>
            <el-select
              v-if="parameter?.options?.length > 0"
              v-model="form.parameters[parameter.name]"
              class="w-full"
              placeholder="请选择参数值"
              :options="parameter.options"
            />
            <el-select
              v-else-if="parameter.type === 'boolean'"
              v-model="form.parameters[parameter.name]"
              class="w-full"
              placeholder="请选择参数值"
              :options="[
                { label: '是', value: true },
                { label: '否', value: false },
              ]"
            />
            <el-slider
              v-else-if="['int', 'float'].includes(parameter.type)"
              v-model="form.parameters[parameter.name]"
              class="w-full px-1"
              :min="parameter?.min"
              :max="parameter?.max"
              :step="parameter?.type === 'float' ? 0.1 : 1"
              show-input
            />
            <el-input
              v-else-if="parameter.type === 'string'"
              v-model="form.parameters[parameter.name]"
              class="w-full"
              placeholder="请输入参数值"
            />
          </el-form-item>
        </div>

        <el-divider content-position="left">输入及输出设置</el-divider>

        <el-form-item>
          <template #label>
            <span class="inline-flex items-center gap-1 text-slate-600">
              携带上下文轮数
              <el-tooltip content="每次向 Agent 提问时携带的最近对话轮数，默认为 3。" placement="top">
                <icon-question-circle class="cursor-help text-slate-400" />
              </el-tooltip>
            </span>
          </template>
          <el-slider
            v-model="form.dialog_round"
            class="w-full px-1"
            show-input
            :min="0"
            :max="10"
            :step="1"
          />
        </el-form-item>
      </el-form>
    </div>
  </el-popover>
</template>

<style scoped></style>
