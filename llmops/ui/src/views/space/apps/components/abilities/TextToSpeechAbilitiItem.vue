<script setup lang="ts">
import { cloneDeep, isEqual } from 'lodash'
import { nextTick, ref, watch } from 'vue'
import { useUpdateDraftAppConfig } from '@/hooks/use-app'

// 1.定义自定义组件所需数据
const props = defineProps({
  app_id: { type: String, default: '', required: true },
  text_to_speech: {
    type: Object,
    default: () => {
      return {}
    },
    required: true,
  },
})
const emits = defineEmits<{
  'update:text_to_speech': [
    value: {
      enable?: boolean
      voice?: string
      auto_play?: boolean
    },
  ]
}>()
const { loading, handleUpdateDraftAppConfig } = useUpdateDraftAppConfig()
const isInit = ref(false)
const textToSpeechModalVisible = ref(false)
const textToSpeechForm = ref({
  enable: props.text_to_speech?.enable,
  voice: props.text_to_speech?.voice,
  auto_play: props.text_to_speech?.auto_play,
})
const originTextToSpeechForm = ref({ ...cloneDeep(textToSpeechForm.value) })

// 2.定义检查表单修改函数
const isFormModified = () => {
  return isEqual(originTextToSpeechForm.value, textToSpeechForm.value)
}

// 3.隐藏文本转语音配置模态窗
const handleCancelTextToSpeechModal = () => {
  // 3.1 隐藏模态窗
  textToSpeechModalVisible.value = false

  // 3.2 还原表单数据
  textToSpeechForm.value = cloneDeep(originTextToSpeechForm.value)
}

// 4.提交模态窗存储的内容
const handleSubmitTextToSpeech = async () => {
  const text_to_speech = {
    enable: textToSpeechForm.value.enable,
    voice: textToSpeechForm.value.voice,
    auto_play: textToSpeechForm.value.auto_play,
  }
  // 4.1 处理数据并完成API接口提交
  await handleUpdateDraftAppConfig(props.app_id, {
    text_to_speech,
  })
  emits('update:text_to_speech', text_to_speech)

  // 4.2 接口更新更新成功，同步表单信息
  originTextToSpeechForm.value = cloneDeep(textToSpeechForm.value)
  await nextTick()

  // 4.3 隐藏模态窗
  handleCancelTextToSpeechModal()
}

// 5.监听text_to_speech变化并同步到表单
watch(
  () => props.text_to_speech,
  (newValue: any) => {
    // 5.1 检测数据是否更新并且未初始化
    if (!isInit.value || !isFormModified()) {
      if (newValue && Object.keys(newValue).length > 0) {
        // 5.2 更新表单数据和备份数据，使用深拷贝
        textToSpeechForm.value = { ...newValue }
        originTextToSpeechForm.value = { ...newValue }

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
    <el-collapse-item name="text_to_speech" class="app-ability-item text-to-speech-ability-item">
      <template #title>
        <div class="flex w-full items-center justify-between gap-2 pr-2">
          <div class="flex min-w-0 items-center text-sm font-bold leading-none text-gray-700">语音输出</div>
          <div class="flex shrink-0 items-center self-stretch" @click.stop>
            <el-dropdown
              class="inline-flex items-center"
              @select="
                async (value: string | number) => {
                  if (Boolean(value) !== textToSpeechForm.enable) {
                    try {
                      // 1.表盖表单数据并确保数据同步
                      textToSpeechForm.enable = Boolean(value)
                      await nextTick()

                      // 2.提交表单更新数据
                      await handleSubmitTextToSpeech()
                    } catch (e) {}
                  }
                }
              "
            >
              <el-button size="small" class="!flex !h-7 !items-center !gap-1 rounded-md px-2" @click.stop>
                {{ textToSpeechForm.enable ? '开启' : '关闭' }}
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
          在Bot回复后，语音播报回复内容。
        </div>
        <el-button
          size="small"
          class="hidden group-hover:block w-full rounded-lg transition-all"
          @click="textToSpeechModalVisible = true"
        >
          <template #icon>
            <icon-settings />
          </template>
          语音设置
        </el-button>
      </div>
    </el-collapse-item>
    <!-- 模态窗组件 -->
    <el-dialog
      v-model="textToSpeechModalVisible"
      header-class="hidden"
      :show-close="false"
      modal-class="rounded-xl"
      @close="handleCancelTextToSpeechModal"
    >
      <!-- 顶部标题 -->
      <div class="flex items-center justify-between">
        <div class="text-lg font-bold text-gray-700">语音输出</div>
        <el-button
          type="text"
          class="text-gray-700!"
          size="small"
          @click="handleCancelTextToSpeechModal"
        >
          <template #icon>
            <icon-close />
          </template>
        </el-button>
      </div>
      <!-- 中间表单 -->
      <div class="py-4">
        <div class="flex flex-col gap-5">
          <!-- 音色设置 -->
          <div class="flex flex-col gap-2">
            <div class="flex flex-col">
              <div class="flex items-center gap-1 text-gray-700">
                音色设置
                <div class="text-red-700">*</div>
              </div>
              <div class="text-gray-500 text-xs">不同的音色适用于不同的场景，请结合业务进行选择。</div>
            </div>
            <el-select v-model="textToSpeechForm.voice">
              <el-option value="alloy">alloy</el-option>
              <el-option value="ash">ash</el-option>
              <el-option value="coral">coral</el-option>
              <el-option value="echo">echo</el-option>
              <el-option value="fable">fable</el-option>
              <el-option value="onyx">onyx</el-option>
              <el-option value="nova">nova</el-option>
              <el-option value="sage">sage</el-option>
              <el-option value="shimmer">shimmer</el-option>
            </el-select>
          </div>
          <!-- 自动播放 -->
          <div class="flex flex-col gap-2">
            <div class="flex flex-col">
              <div class="flex items-center gap-1 text-gray-700">
                自动播放
                <div class="text-red-700">*</div>
              </div>
              <div class="text-gray-500 text-xs">Agent回复结束后，自动播放音频内容</div>
            </div>
            <div class="">
              <el-switch
                v-model="textToSpeechForm.auto_play"
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
          <el-button class="rounded-lg" @click="handleCancelTextToSpeechModal">取消</el-button>
          <el-button
            :loading="loading"
            type="primary"
            class="rounded-lg"
            @click="handleSubmitTextToSpeech"
          >
            保存
          </el-button>
        </el-space>
      </div>
    </el-dialog>
  </div>
</template>

<style>
.text-to-speech-ability-item :deep(.el-collapse-item__content) {
  padding: 0;
}
</style>
