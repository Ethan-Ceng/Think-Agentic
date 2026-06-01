<script setup lang="ts">
import { type PropType } from 'vue'
import { useUpdateDraftAppConfig } from '@/hooks/use-app'

// 1.定义自定义组件所需数据
const props = defineProps({
  app_id: { type: String, default: '', required: true },
  suggested_after_answer: {
    type: Object as PropType<{ enable: boolean }>,
    default: () => {
      return { enable: false }
    },
    required: true,
  },
})
const emits = defineEmits(['update:suggested_after_answer'])
const { handleUpdateDraftAppConfig } = useUpdateDraftAppConfig()
</script>

<template>
  <div class="">
    <el-collapse-item name="suggested_after_answer" class="app-ability-item">
      <template #title>
        <div class="flex w-full items-center justify-between gap-2 pr-2">
          <div class="flex min-w-0 items-center text-sm font-bold leading-none text-gray-700">用户问题建议</div>
          <div class="flex shrink-0 items-center self-stretch" @click.stop>
            <el-dropdown
              class="inline-flex items-center"
              @select="
                async (value: string | number) => {
                  if (Boolean(value) !== props.suggested_after_answer?.enable) {
                    emits('update:suggested_after_answer', { enable: Boolean(value) })
                    await handleUpdateDraftAppConfig(props.app_id, {
                      suggested_after_answer: { enable: Boolean(value) },
                    })
                  }
                }
              "
            >
              <el-button size="small" class="!flex !h-7 !items-center !gap-1 rounded-md px-2" @click.stop>
                {{ props.suggested_after_answer.enable ? '开启' : '关闭' }}
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
      <div class="text-xs text-gray-500 leading-[22px]">
        在应用回复后，自动根据对话内容提供 3 条用户提问建议。
      </div>
    </el-collapse-item>
  </div>
</template>

<style scoped></style>
