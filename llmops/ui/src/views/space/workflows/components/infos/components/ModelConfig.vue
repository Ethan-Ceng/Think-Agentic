<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { apiPrefix } from '@/config'
import { useGetLanguageModel, useGetLanguageModels } from '@/hooks/use-language-model'

// 1.定义自定义组件所需数据
const props = defineProps({
  model_config: {
    type: Object,
    default: () => {
      return {}
    },
    required: true,
  },
})
const emits = defineEmits(['update:model_config'])
const form = ref<any>({})
const {
  loading: getLanguageModelLoading,
  language_model,
  loadLanguageModel,
} = useGetLanguageModel()
const { language_models, loadLanguageModels } = useGetLanguageModels()
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
  emits('update:model_config', model_config)
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

onMounted(() => {
  loadLanguageModels()
})
</script>

<template>
  <el-popover
    v-if="props.model_config?.provider"
    trigger="click"
    placement="bottom-end"
    :popup-translate="[0, 12]"
    @hide="hideModelTrigger"
  >
    <div class="flex items-center gap-1 cursor-pointer hover:bg-gray-100 px-1.5 py-1 rounded-lg">
      <el-avatar
        :size="16"
        shape="square"
        :src="`${apiPrefix}/language-models/${form?.provider}/icon`"
      />
      <div class="text-gray-700 text-xs">{{ form?.model }}</div>
      <icon-down />
    </div>
    <template #content>
      <div class="bg-white px-6 py-5 shadow-sm rounded-lg w-[460px]">
        <!-- 标题 -->
        <div class="text-gray-700 text-base font-semibold mb-3">模型设置</div>
        <!-- 模型选择 -->
        <div class="flex flex-col gap-2 mb-2">
          <div class="text-gray-700">模型</div>
          <el-select
            v-model="form.selectValue"
            :options="modelOptions"
            size="small"
            class="rounded-lg mb-2"
            placeholder="请选择Agent使用的大语言模型"
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
                  <div class="text-xs text-gray-700">{{ selectedModelParts.provider }}</div>
                  <div class="text-xs text-gray-500">·</div>
                  <div class="text-xs text-gray-700">{{ selectedModelParts.model }}</div>
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
                <div class="text-xs text-gray-700 py-2">{{ data?.label ?? label }}</div>
              </div>
            </template>
          </el-select>
        </div>
        <!-- 参数列表 -->
        <div class="text-gray-700 mb-2">参数</div>
        <div v-loading="getLanguageModelLoading" class="w-full">
          <div
            v-for="parameter in language_model?.parameters"
            :key="parameter.name"
            class="flex items-center gap-2 h-8 mb-4"
          >
            <!-- 字段标签 -->
            <div class="flex items-center gap-2 text-gray-500 w-[120px] shrink-0">
              <div class="text-xs">{{ parameter?.label }}</div>
              <el-tooltip :content="parameter?.help">
                <icon-question-circle />
              </el-tooltip>
            </div>
            <!-- 字段输入框 -->
            <template v-if="parameter?.options?.length > 0">
              <el-select
                v-model="form.parameters[parameter.name]"
                placeholder="请选择参数值"
                :options="parameter.options"
              />
            </template>
            <template v-else-if="parameter.type === 'boolean'">
              <el-select
                v-model="form.parameters[parameter.name]"
                placeholder="请选择参数值"
                :options="[
                  { label: '是', value: true },
                  { label: '否', value: false },
                ]"
              />
            </template>
            <template v-else-if="['int', 'float'].includes(parameter.type)">
              <el-slider
                v-model="form.parameters[parameter.name]"
                :min="parameter?.min"
                :max="parameter?.max"
                :step="parameter?.type === 'float' ? 0.1 : 1"
                show-input
              />
            </template>
            <template v-else-if="parameter.type === 'string'">
              <el-input
                v-model="form.parameters[parameter.name]"
                placeholder="请输入参数值"
              />
            </template>
          </div>
        </div>
      </div>
    </template>
  </el-popover>
</template>

<style scoped></style>
