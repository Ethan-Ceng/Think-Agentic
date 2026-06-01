<script setup lang="ts">
import { ref, watch } from 'vue'
import type { FormInstance } from 'element-plus'
import { useGetDocument, useUpdateDocumentName } from '@/hooks/use-dataset'

// 1.定义组件所需要使用的数据
const props = defineProps({
  visible: { type: Boolean, required: true },
  dataset_id: { type: String, required: true },
  document_id: { type: String, required: true },
  onAfterUpdate: {
    type: Function,
    required: false,
    default: () => {
      return {}
    },
  },
})
const emits = defineEmits(['update:visible'])
const { document, loadDocument } = useGetDocument()
const { loading: updateDocumentNameLoading, handleUpdateDocumentName } = useUpdateDocumentName()
const form = ref({ name: '' })
const formRef = ref<FormInstance>()

// 2.定义关闭模态窗函数，执行关闭模态窗并重置表单操作
const hideModal = () => {
  emits('update:visible', false)
  formRef.value?.resetFields()
}

// 3.定义表单提交函数
const handleSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  // 3.3 调用处理器发起请求
  await handleUpdateDocumentName(props.dataset_id, props.document_id, form.value.name)

  // 3.4 隐藏模态窗并重置表单
  hideModal()

  // 3.5 调用完成后的回调函数
  props.onAfterUpdate()
}

// 4.监听visible，当模态窗开启的时候，我们需要调用接口获取数据并填充到表单中
watch(
  () => props.visible,
  async (newValue: boolean) => {
    if (newValue) {
      await loadDocument(props.dataset_id, props.document_id)

      formRef.value?.resetFields()
      form.value.name = document.value.name
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
      <el-form ref="formRef" :model="form" @submit.prevent="handleSubmit" label-position="top">
        <el-form-item
          prop="name"
          label="名称"
          :rules="[{ required: true, message: '文档名称不能为空' }]"
        >
          <el-input
            v-model="form.name"
            placeholder="请输入文档名称"
            show-word-limit
            :max-length="100"
          />
        </el-form-item>
        <!-- 底部按钮 -->
        <div class="flex items-center justify-between">
          <div class=""></div>
          <el-space :size="16">
            <el-button class="rounded-lg" @click="hideModal">取消</el-button>
            <el-button
              :loading="updateDocumentNameLoading"
              type="primary"
              native-type="submit"
              class="rounded-lg"
            >
              保存
            </el-button>
          </el-space>
        </div>
      </el-form>
    </div>
  </el-dialog>
</template>

<style scoped></style>
