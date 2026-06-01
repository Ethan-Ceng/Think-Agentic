<script setup lang="ts">
import { type PropType } from 'vue'
import { useUpdateDraftAppConfig } from '@/hooks/use-app'

// 1.定义自定义组件所需数据
const props = defineProps({
  app_id: { type: String, default: '', required: true },
  long_term_memory: {
    type: Object as PropType<{ enable: boolean }>,
    default: () => {
      return { enable: false }
    },
    required: true,
  },
})
const emits = defineEmits(['update:long_term_memory'])
const { handleUpdateDraftAppConfig } = useUpdateDraftAppConfig()
</script>

<template>
  <div class="">
    <el-collapse-item name="long_term_memory" class="app-ability-item">
      <template #title>
        <div class="flex w-full items-center justify-between gap-2 pr-2">
          <div class="flex min-w-0 items-center text-sm font-bold leading-none text-gray-700">长期记忆</div>
          <div class="flex shrink-0 items-center self-stretch" @click.stop>
            <el-dropdown
              class="inline-flex items-center"
              @select="
                async (value: string | number) => {
                  if (Boolean(value) !== props.long_term_memory?.enable) {
                    emits('update:long_term_memory', { enable: Boolean(value) })
                    await handleUpdateDraftAppConfig(props.app_id, {
                      long_term_memory: { enable: Boolean(value) },
                    })
                  }
                }
              "
            >
              <el-button size="small" class="!flex !h-7 !items-center !gap-1 rounded-md px-2" @click.stop>
                {{ props.long_term_memory.enable ? '开启' : '关闭' }}
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
        总结聊天对话内容，并用于更好的响应用户的信息。
      </div>
    </el-collapse-item>
  </div>
</template>

<style scoped></style>
