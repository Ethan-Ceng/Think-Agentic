<script setup lang="ts">
import { ref, watch } from 'vue'
import type { FormInstance, UploadRequestOptions } from 'element-plus'
import { useCreateWorkflow, useGetWorkflow, useUpdateWorkflow } from '@/hooks/use-workflow'
import { useUploadImage } from '@/hooks/use-upload-file'

// 1.定义自定义组件所需数据
const props = defineProps({
  workflow_id: { type: String, default: '', required: false },
  visible: { type: Boolean, required: true },
  callback: { type: Function, required: false },
})
const emits = defineEmits(['update:visible', 'update:workflow_id'])
const { loading: createWorkflowLoading, handleCreateWorkflow } = useCreateWorkflow()
const { loading: updateWorkflowLoading, handleUpdateWorkflow } = useUpdateWorkflow()
const { workflow, loadWorkflow } = useGetWorkflow()
const { image_url, handleUploadImage } = useUploadImage()
const defaultForm = {
  fileList: [] as any,
  icon: '',
  name: '',
  tool_call_name: '',
  description: '',
}
const form = ref({ ...defaultForm })
const formRef = ref<FormInstance>()

// 2.定义隐藏模态窗函数
const hideModal = () => emits('update:visible', false)

// 3.定义表单提交函数
const saveWorkflow = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  // 3.2 检测是保存还是新增，调用不同的API接口
  if (props.workflow_id) {
    await handleUpdateWorkflow(props.workflow_id, form.value)
  } else {
    await handleCreateWorkflow(form.value)
  }

  // 3.3 完成保存操作，隐藏模态窗并调用回调函数
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
      if (props.workflow_id) {
        // 4.4 调用接口获取工作流详情
        await loadWorkflow(props.workflow_id)

        // 4.5 更新表单数据
        form.value = {
          fileList: [{ uid: 1, name: '应用图标', url: String(workflow.value?.icon) }],
          icon: String(workflow.value?.icon),
          name: String(workflow.value?.name),
          tool_call_name: String(workflow.value?.tool_call_name),
          description: String(workflow.value?.description),
        }
      }
    } else {
      // 4.6 关闭弹窗，需要清空表单数据
      form.value = defaultForm
      formRef.value?.resetFields()
      emits('update:workflow_id', '')
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
        {{ props.workflow_id === '' ? '创建工作流' : '编辑工作流' }}
      </div>
      <el-button type="text" class="text-gray-700!" size="small" @click="hideModal">
        <template #icon>
          <icon-close />
        </template>
      </el-button>
    </div>
    <!-- 中间表单 -->
    <div class="pt-6">
      <el-form ref="formRef" :model="form" label-position="top" @submit.prevent="saveWorkflow">
        <el-form-item prop="fileList" :rules="[{ required: true, message: '工作流图标不能为空' }]">
          <el-upload
            :limit="1"
            list-type="picture-card"
            accept="image/png, image/jpeg"
            class="w-auto! mx-auto"
            v-model:file-list="form.fileList"
            :http-request="
              (option: UploadRequestOptions) => {
                // 1.从option中提取数据
                const { file, onSuccess, onError } = option

                // 2.使用普通异步函数完成上传
                const uploadTask = async () => {
                  try {
                    await handleUploadImage(file)
                    form.icon = image_url
                    onSuccess(image_url)
                  } catch (error) {
                    onError(error as any)
                  }
                }
                uploadTask()

                return { abort: () => {} }
              }
            "
            :on-before-remove="
              async () => {
                form.icon = ''
                return true
              }
            "
          />
        </el-form-item>
        <el-form-item
          prop="name"
          label="工作流名称"
          :rules="[{ required: true, message: '工作流名称不能为空' }]"
        >
          <el-input
            show-word-limit
            :max-length="50"
            v-model="form.name"
            placeholder="请输入工作流名称"
          />
        </el-form-item>
        <el-form-item
          prop="tool_call_name"
          label="英文名称"
          :rules="[{ required: true, message: '英文名称不能为空' }]"
        >
          <el-input
            show-word-limit
            :max-length="50"
            v-model="form.tool_call_name"
            placeholder="英文名称将用于被大模型识别及调用"
          />
        </el-form-item>
        <el-form-item
          prop="description"
          label="工作流描述"
          :rules="[{ required: true, message: '工作流描述不能为空' }]"
        >
          <el-input
            v-model="form.description"
            :auto-size="{ minRows: 8, maxRows: 8 }"
            :max-length="1024"
            show-word-limit
            placeholder="请输入关于该工作流的描述信息，以便LLM能准确识别工作流的用途。"
          />
        </el-form-item>
        <!-- 底部按钮 -->
        <div class="flex items-center justify-between">
          <div class=""></div>
          <el-space :size="16">
            <el-button class="rounded-lg" @click="hideModal">取消</el-button>
            <el-button
              :loading="createWorkflowLoading || updateWorkflowLoading"
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
