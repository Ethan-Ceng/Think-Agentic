<script setup lang="ts">
import { cloneDeep, isEqual } from 'lodash'
import { nextTick, ref, watch } from 'vue'
import { useUpdateDraftAppConfig } from '@/hooks/use-app'

// 1.定义自定义组件所需数据
const props = defineProps({
  app_id: { type: String, default: '', required: true },
  review_config: {
    type: Object,
    default: () => {
      return {}
    },
    required: true,
  },
})
const emits = defineEmits<{
  'update:review_config': [
    value: {
      enable?: boolean
      keywords: string[]
      inputs_config: { enable?: boolean; preset_response?: string }
      outputs_config: { enable?: boolean }
    },
  ]
}>()
const { loading, handleUpdateDraftAppConfig } = useUpdateDraftAppConfig()
const isInit = ref(false)
const reviewConfigModalVisible = ref(false)
const reviewConfigForm = ref({
  enable: props.review_config?.enable,
  keywords: props.review_config?.keywords?.join('\n'),
  inputs_config: {
    enable: props.review_config?.inputs_config?.enable,
    preset_response: props.review_config?.inputs_config?.preset_response,
  },
  outputs_config: {
    enable: props.review_config?.outputs_config?.enable,
  },
})
const originReviewConfigForm = ref({ ...cloneDeep(reviewConfigForm.value) })

// 2.定义检查表单修改函数
const isFormModified = () => {
  return isEqual(originReviewConfigForm.value, reviewConfigForm.value)
}

// 3.隐藏审核配置模态窗处理器
const handleCancelReviewConfigModal = () => {
  // 3.1 隐藏模态窗
  reviewConfigModalVisible.value = false

  // 3.2 还原表单数据
  reviewConfigForm.value = cloneDeep(originReviewConfigForm.value)
}

// 4.提交审核配置模态窗存储的内容
const handleSubmitReviewConfig = async () => {
  const review_config = {
    enable: reviewConfigForm.value.enable,
    keywords: reviewConfigForm.value.keywords
      .split(/\r?\n/)
      .filter((item: string) => item.trim() !== ''),
    inputs_config: reviewConfigForm.value.inputs_config,
    outputs_config: reviewConfigForm.value.outputs_config,
  }
  // 4.1 处理数据并完成API接口提交
  await handleUpdateDraftAppConfig(props.app_id, {
    review_config,
  })
  emits('update:review_config', review_config)

  // 4.2 接口更新更新成功，同步表单信息
  originReviewConfigForm.value = cloneDeep(reviewConfigForm.value)
  await nextTick()

  // 4.3 隐藏模态窗
  handleCancelReviewConfigModal()
}

// 5.监听review_config变化并同步到表单
watch(
  () => props.review_config,
  (newValue: any) => {
    // 5.1 检测数据是否更新并且未初始化
    if (!isInit.value || !isFormModified()) {
      if (newValue && Object.keys(newValue).length > 0) {
        // 5.2 更新表单数据和备份数据，使用深拷贝
        reviewConfigForm.value = cloneDeep({ ...newValue, keywords: newValue?.keywords.join('\n') })
        originReviewConfigForm.value = cloneDeep({
          ...newValue,
          keywords: newValue?.keywords.join('\n'),
        })

        // 5.3 标记为已初始化
        isInit.value = true
      }
    }
  },
  { immediate: true, deep: true },
)
</script>

<template>
  <div class="">
    <el-collapse-item name="review_config" class="app-ability-item review-config-ability-item">
      <template #title>
        <div class="flex w-full items-center justify-between gap-2 pr-2">
          <div class="flex min-w-0 items-center text-sm font-bold leading-none text-gray-700">内容审查</div>
          <div class="flex shrink-0 items-center self-stretch" @click.stop>
            <el-dropdown
              class="inline-flex items-center"
              @select="
                async (value: string | number) => {
                  if (Boolean(value) !== reviewConfigForm.enable) {
                    try {
                      // 1.表盖表单数据并确保数据同步
                      reviewConfigForm.enable = Boolean(value)
                      await nextTick()

                      // 2.提交表单更新数据
                      await handleSubmitReviewConfig()
                    } catch (e) {}
                  }
                }
              "
            >
              <el-button size="small" class="!flex !h-7 !items-center !gap-1 rounded-md px-2" @click.stop>
                {{ reviewConfigForm.enable ? '开启' : '关闭' }}
                <icon-down />
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item :value="1" class="text-xs py-1.5 text-gray-700">开启</el-dropdown-item>
                  <el-dropdown-item :value="0" class="text-xs py-1.5 text-red-700">关闭</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </template>
      <template #icon="{ isActive }">
        <icon-down v-if="isActive" />
        <icon-right v-else />
      </template>
      <div class="group py-2">
        <div class="text-xs text-gray-500 leading-[22px] group-hover:hidden">
          对用户输入以及大语言模型输出内容进行审查。
        </div>
        <el-button
          size="small"
          class="hidden group-hover:block w-full rounded-lg transition-all"
          @click="reviewConfigModalVisible = true"
        >
          <template #icon>
            <icon-settings />
          </template>
          设置
        </el-button>
      </div>
    </el-collapse-item>
    <!-- 模态窗组件 -->
    <el-dialog
      v-model="reviewConfigModalVisible"
      header-class="hidden"
      :show-close="false"
      modal-class="rounded-xl"
      @close="handleCancelReviewConfigModal"
    >
      <!-- 顶部标题 -->
      <div class="flex items-center justify-between">
        <div class="text-lg font-bold text-gray-700">内容审核</div>
        <el-button
          type="text"
          class="text-gray-700!"
          size="small"
          @click="handleCancelReviewConfigModal"
        >
          <template #icon>
            <icon-close />
          </template>
        </el-button>
      </div>
      <!-- 中间表单 -->
      <div class="py-4">
        <div class="flex flex-col gap-5">
          <!-- 关键词 -->
          <div class="flex flex-col gap-2">
            <div class="flex flex-col">
              <div class="flex items-center gap-1 text-gray-700">
                关键词
                <div class="text-red-700">*</div>
              </div>
              <div class="text-gray-500 text-xs">每行一个，用换行符分割，最多填写100个关键词</div>
            </div>
            <el-input
              v-model="reviewConfigForm.keywords"
              class="bg-white rounded-lg border border-gray-200"
              placeholder="每行一个，用换行符分隔。"
              :max-length="100"
              show-word-limit
              :auto-size="{ minRows: 4, maxRows: 4 }"
              :word-length="
                (value: string) => {
                  if (value.trim() === '') return 0
                  return value.split(/\r?\n/).length
                }
              "
              :word-slice="
                (value: string, maxLength: number) => {
                  // 1.分割内容并截取前100个关键词
                  const lines = value.split(/\r?\n/)
                  const first100Lines = lines.slice(0, maxLength)

                  // 2.拼接换行符后返回
                  return first100Lines.join('\n')
                }
              "
            />
          </div>
          <!-- 输入审核 -->
          <div class="flex flex-col gap-2 p-3 bg-gray-50 border border-gray-200 rounded-lg">
            <div class="flex items-center justify-between">
              <div class="text-gray-700">输入审查内容</div>
              <el-switch
                v-model="reviewConfigForm.inputs_config.enable"
                size="small"
              />
            </div>
            <div class="flex flex-col gap-2">
              <div class="text-gray-700 text-xs">预设回复</div>
              <el-input
                v-model="reviewConfigForm.inputs_config.preset_response"
                placeholder="这里是预设回复内容"
                class="bg-white rounded-lg border border-gray-200"
                :auto-size="{ minRows: 3, maxRows: 3 }"
              />
            </div>
          </div>
          <!-- 输出审核 -->
          <div class="flex flex-col p-3 bg-gray-50 border border-gray-200 rounded-lg">
            <div class="flex items-center justify-between">
              <div class="text-gray-700">输出审查内容</div>
              <el-switch
                v-model="reviewConfigForm.outputs_config.enable"
                size="small"
              />
            </div>
          </div>
        </div>
      </div>
      <!-- 底部按钮 -->
      <div class="flex items-center justify-between">
        <div class=""></div>
        <el-space :size="16">
          <el-button class="rounded-lg" @click="handleCancelReviewConfigModal">取消</el-button>
          <el-button
            :loading="loading"
            type="primary"
            class="rounded-lg"
            @click="handleSubmitReviewConfig"
          >
            保存
          </el-button>
        </el-space>
      </div>
    </el-dialog>
  </div>
</template>

<style>
.review-config-ability-item :deep(.el-collapse-item__content) {
  padding: 0;
}
</style>
