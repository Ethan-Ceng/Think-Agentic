<script setup lang="ts">
import { useUpdateDraftAppConfig } from '@/hooks/use-app'
import { useOptimizePrompt } from '@/hooks/use-ai'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  app_id: { type: String, required: true },
  preset_prompt: { type: String, default: '', required: true },
})
const emits = defineEmits(['update:preset_prompt'])
const optimizeTriggerVisible = ref(false)
const origin_prompt = ref('')
const { handleUpdateDraftAppConfig } = useUpdateDraftAppConfig()
const { loading, optimize_prompt, handleOptimizePrompt } = useOptimizePrompt()

const handleReplacePresetPrompt = () => {
  if (optimize_prompt.value.trim() === '') {
    ElMessage.warning('优化prompt为空，请重新生成')
    return
  }
  emits('update:preset_prompt', optimize_prompt.value)
  handleUpdateDraftAppConfig(props.app_id, { preset_prompt: optimize_prompt.value })
  optimizeTriggerVisible.value = false
}

const handleSubmit = async () => {
  if (origin_prompt.value.trim() === '') {
    ElMessage.warning('原始prompt不能为空')
    return
  }
  await handleOptimizePrompt(origin_prompt.value)
}

const handlePresetBlur = async () => {
  await handleUpdateDraftAppConfig(props.app_id, {
    preset_prompt: props.preset_prompt,
  })
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col">
    <!-- 顶栏：紧凑、与分栏区无额外外边距 -->
    <div
      class="flex shrink-0 items-center justify-between gap-2 border-b border-slate-200/75 bg-white/80 px-3 py-2"
    >
      <div class="min-w-0 pr-2">
        <div class="text-xs font-semibold leading-tight text-slate-900">人设与回复逻辑</div>
        <div class="mt-0.5 line-clamp-1 text-[11px] leading-snug text-slate-500">
          身份、语气与约束
        </div>
      </div>
      <el-popover
        v-model:visible="optimizeTriggerVisible"
        trigger="click"
        placement="bottom-start"
        :width="440"
      >
        <template #reference>
          <el-button size="small" class="!h-7 shrink-0 rounded-md !px-2 !text-xs">
            <template #icon>
              <icon-sync />
            </template>
            优化
          </el-button>
        </template>
        <el-card shadow="never" class="optimize-card !border-0 !p-0 !shadow-none">
          <div class="flex flex-col gap-2.5 p-3">
            <div v-if="optimize_prompt" class="flex flex-col gap-2">
              <div
                class="scrollbar-y-sleek max-h-[min(280px,48vh)] overflow-y-auto whitespace-pre-line text-xs leading-relaxed text-slate-700"
              >
                {{ optimize_prompt }}
              </div>
              <el-space v-if="!loading" :size="6" wrap>
                <el-button size="small" type="primary" class="!h-7 rounded-md" @click="handleReplacePresetPrompt">
                  替换
                </el-button>
                <el-button size="small" class="!h-7 rounded-md" @click="optimizeTriggerVisible = false">
                  退出
                </el-button>
              </el-space>
            </div>
            <div class="flex min-w-0 items-center gap-1.5">
              <el-input
                v-model="origin_prompt"
                class="min-w-0 flex-1"
                size="small"
                clearable
                placeholder="描述如何优化提示词"
                @keydown.enter.prevent="handleSubmit"
              />
              <el-button :loading="loading" type="primary" size="small" circle @click="handleSubmit">
                <template #icon>
                  <icon-send :size="14" />
                </template>
              </el-button>
            </div>
          </div>
        </el-card>
      </el-popover>
    </div>

    <!-- 正文：无额外外包层 padding，输入区贴边占满 -->
    <div class="prompt-field min-h-0 flex-1 bg-white">
      <el-input
        type="textarea"
        resize="none"
        class="preset-prompt-textarea preset-input h-full min-h-0 !border-0 !shadow-none"
        placeholder="输入 Agent 人设与回复逻辑（预设 prompt）"
        :maxlength="2000"
        show-word-limit
        :model-value="props.preset_prompt"
        @update:model-value="(value: string) => emits('update:preset_prompt', value)"
        @blur="handlePresetBlur"
      />
    </div>
  </div>
</template>

<style scoped>
.optimize-card :deep(.el-card__body) {
  padding: 0;
}

.prompt-field :deep(.el-textarea) {
  height: 100%;
}

.prompt-field :deep(.el-textarea__inner) {
  height: 100% !important;
  min-height: 96px;
  box-sizing: border-box;
  padding: 10px 12px 32px;
  border: none !important;
  border-radius: 0;
  box-shadow: none !important;
  background-color: rgb(255 255 255 / 0.96);
  line-height: 1.55;
  font-size: 13px;
}

.prompt-field :deep(.el-input__count) {
  bottom: 6px;
  right: 10px;
  background: transparent;
}
</style>
