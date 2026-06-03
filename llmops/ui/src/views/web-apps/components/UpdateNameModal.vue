<script setup lang="ts">
import { useUpdateWebAppConversationName } from '@/hooks/use-web-app'
import type { FormInstance } from 'element-plus'
import { ref, watch } from 'vue'

// 1.定义自定义组件所需数据
const props = defineProps({
  token: { type: String, default: '', required: true },
  conversation_id: { type: String, default: '', required: false },
  visible: { type: Boolean, required: true },
  success_callback: { type: Function, required: false },
})
const emits = defineEmits(['update:visible', 'update:conversation_id'])
const {
  loading: updateConversationNameLoading,
  handleUpdateConversationName, //
} = useUpdateWebAppConversationName()
const defaultForm = { name: '' }
const form = ref({ ...defaultForm })
const formRef = ref<FormInstance>()

// 2.定义隐藏模态窗函数
const hideModal = () => emits('update:visible', false)

// 3.定义表单提交函数
const saveName = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  // 3.2 检测是保存还是新增，调用不同的API接口
  await handleUpdateConversationName(props.token, props.conversation_id, form.value.name)

  // 3.3 完成保存操作，隐藏模态窗并调用回调函数
  props.success_callback && props.success_callback(props.conversation_id, form.value.name)
  emits('update:visible', false)
}

// 4.监听模态窗显示状态变化
watch(
  () => props.visible,
  async (newValue) => {
    // 4.1 清除表单校验信息
    formRef.value?.resetFields()

    // 4.2 关闭弹窗，需要清空表单数据
    if (!newValue) {
      form.value = defaultForm
      emits('update:conversation_id', '')
    }
  },
)
</script>

<template>
  <el-dialog
    :width="520"
    :model-value="props.visible"
    class="rounded-xl"
    @update:model-value="(v: boolean) => emits('update:visible', v)"
  >
    <!-- 顶部标题 -->
    <div class="flex items-center justify-between">
      <div class="text-lg font-bold text-gray-700">重命名</div>
      <el-button type="text" class="text-gray-700!" size="small" @click="hideModal">
        <template #icon>
          <icon-close />
        </template>
      </el-button>
    </div>
    <!-- 中间表单 -->
    <div class="pt-6">
      <el-form ref="formRef" :model="form" label-position="top" @submit.prevent="saveName">
        <el-form-item
          prop="name"
          label="会话名称"
          :rules="[{ required: true, message: '会话名称不能为空' }]"
        >
          <el-input v-model="form.name" placeholder="请输入新会话名称" />
        </el-form-item>
        <!-- 底部按钮 -->
        <div class="flex items-center justify-between">
          <div class=""></div>
          <el-space :size="16">
            <el-button class="rounded-lg" @click="hideModal">取消</el-button>
            <el-button
              :loading="updateConversationNameLoading"
              type="primary"
              native-type="submit"
              class="rounded-lg"
            >
              确认
            </el-button>
          </el-space>
        </div>
      </el-form>
    </div>
  </el-dialog>
</template>

<style scoped></style>
