<script setup lang="ts">
import { useGetDebugConversationSummary, useUpdateDebugConversationSummary } from '@/hooks/use-app'
import { ref } from 'vue'

// 1.定义自定义组件所需数据
const props = defineProps({
  app_id: { type: String, required: true },
  long_term_memory: {
    type: Object,
    default: () => {
      return { enable: false }
    },
    required: true,
  },
})
const { debug_conversation_summary, loadDebugConversationSummary } =
  useGetDebugConversationSummary()
const { loading, handleUpdateDebugConversationSummary } = useUpdateDebugConversationSummary()
const summaryModalVisible = ref(false)

// 2.模态窗打开处理器
const openSummaryModal = async () => {
  // 2.1 调用API获取长期记忆
  await loadDebugConversationSummary(props.app_id)

  // 2.2 开启模态窗
  summaryModalVisible.value = true
}
</script>

<template>
  <div class="">
    <!-- 预览与调试头组件 -->
    <div
      class="flex h-16 shrink-0 items-center justify-between border-b border-slate-200/60 bg-white px-4 shadow-sm shadow-slate-900/[0.02]"
    >
      <div class="text-base font-medium text-slate-800">预览与调试</div>
      <el-button
        :disabled="!props.long_term_memory?.enable"
        size="small"
        type="text"
        class="rounded-lg px-1 !text-blue-700"
        @click="openSummaryModal"
      >
        <template #icon>
          <icon-save />
        </template>
        长期记忆
      </el-button>
    </div>
    <!-- 长期记忆模态窗 -->
    <el-dialog
      :width="520"
      v-model="summaryModalVisible"
      header-class="hidden"
      :show-close="false"
      modal-class="rounded-xl"
    >
      <!-- 顶部标题 -->
      <div class="flex items-center justify-between">
        <div class="text-lg font-bold text-gray-700">长期记忆</div>
        <el-button
          type="text"
          class="text-gray-700!"
          size="small"
          @click="summaryModalVisible = false"
        >
          <template #icon>
            <icon-close />
          </template>
        </el-button>
      </div>
      <!-- 底部表单 -->
      <div class="pt-6">
        <el-input
          v-model="debug_conversation_summary"
          placeholder="请输入当前调试会话长期记忆"
          show-word-limit
          :max-length="2000"
          :auto-size="{ minRows: 8, maxRows: 8 }"
        />
        <!-- 底部按钮 -->
        <div class="flex items-center justify-between">
          <div class=""></div>
          <el-space :size="16">
            <el-button class="rounded-lg" @click="summaryModalVisible = false">取消</el-button>
            <el-button
              :loading="loading"
              type="primary"
              class="rounded-lg"
              @click="
                async () => {
                  await handleUpdateDebugConversationSummary(
                    props.app_id,
                    debug_conversation_summary,
                  )
                  summaryModalVisible = false
                }
              "
            >
              保存
            </el-button>
          </el-space>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped></style>
