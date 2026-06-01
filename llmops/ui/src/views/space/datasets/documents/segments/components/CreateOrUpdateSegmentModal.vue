<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FormInstance } from 'element-plus'
import { useCreateSegment, useGetSegment, useUpdateSegment } from '@/hooks/use-dataset'
import type { CreateSegmentRequest, UpdateSegmentRequest } from '@/models/dataset'

// 1.定义自定义组件所需数据
const props = defineProps({
  dataset_id: { type: String, required: false },
  document_id: { type: String, required: false },
  segment_id: { type: String, required: false },
  visible: { type: Boolean, required: true },
  callback: { type: Function, required: false },
})
const emits = defineEmits(['update:visible'])
const { loading: createSegmentLoading, handleCreateSegment } = useCreateSegment()
const { loading: updateSegmentLoading, handleUpdateSegment } = useUpdateSegment()
const { segment, loadSegment } = useGetSegment()
const defaultForm: { content: string; keywords: string[] } = {
  content: '',
  keywords: [],
}
const form = ref(defaultForm)
const formRef = ref<FormInstance>()
const isUpdateOperation = computed(() => props.segment_id && props.segment_id !== '')

// 2.定义隐藏模态窗函数
const hideModal = () => emits('update:visible', false)

// 3.定义表单提交函数
const saveSegment = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  // 3.2 检测是保存还是新增，调用不同的API接口
  if (isUpdateOperation.value) {
    // 3.3 更新文档片段信息
    await handleUpdateSegment(
      props.dataset_id as string,
      props.document_id as string,
      props.segment_id as string,
      form.value as UpdateSegmentRequest,
    )
  } else {
    // 3.4 新增文档片段信息
    await handleCreateSegment(
      props.dataset_id as string,
      props.document_id as string,
      form.value as CreateSegmentRequest,
    )
  }

  // 3.5 完成保存操作，隐藏模态窗并调用回调函数
  emits('update:visible', false)
  props.callback && props.callback()
}

// 4.监听模态窗显示状态变化
watch(
  () => props.visible,
  async (newValue) => {
    // 4.1 清除表单校验信息
    formRef.value?.resetFields()

    // 4.2 判断弹窗是打开还是关闭
    if (newValue) {
      // 4.3 开启弹窗，需要检测下是更新还是创建操作
      if (isUpdateOperation.value) {
        // 4.4 调用接口获取文档片段详情
        await loadSegment(
          props.dataset_id as string,
          props.document_id as string,
          props.segment_id as string,
        )

        // 4.5 更新表单数据
        form.value.content = segment.value.content
        form.value.keywords = segment.value.keywords
      }
    } else {
      // 4.6 关闭弹窗，需要清空表单数据
      formRef.value?.resetFields()
      form.value = defaultForm
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
      <div class="text-lg font-bold text-gray-700">
        {{ isUpdateOperation ? '更新' : '添加' }}片段
      </div>
      <el-button type="text" class="text-gray-700!" size="small" @click="hideModal">
        <template #icon>
          <icon-close />
        </template>
      </el-button>
    </div>
    <!-- 中间表单 -->
    <div class="pt-6">
      <el-form ref="formRef" :model="form" label-position="top" @submit.prevent="saveSegment">
        <el-form-item
          prop="content"
          label="片段内容"
          :rules="[{ required: true, message: '片段内容不能为空' }]"
        >
          <el-input
            v-model="form.content"
            :auto-size="{ minRows: 8, maxRows: 8 }"
            placeholder="在这里添加文档片段内容"
          />
        </el-form-item>
        <el-form-item prop="keywords" label="关键词">
          <el-input-tag
            v-model="form.keywords"
            :max-tag-count="10"
            placeholder="请输入该文档片段关键词，最多不超过10个，按Enter输入"
          />
        </el-form-item>
        <!-- 底部按钮 -->
        <div class="flex items-center justify-between">
          <div class=""></div>
          <el-space :size="16">
            <el-button class="rounded-lg" @click="hideModal">取消</el-button>
            <el-button
              :loading="updateSegmentLoading || createSegmentLoading"
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
