<script setup lang="ts">
import { ref, watch } from 'vue'
import type { FormInstance, UploadRequestOptions } from 'element-plus'
import { useCreateApp, useGetApp, useUpdateApp } from '@/hooks/use-app'
import { useUploadImage } from '@/hooks/use-upload-file'

// 1.定义自定义组件所需数据
const props = defineProps({
  app_id: { type: String, default: '', required: false },
  visible: { type: Boolean, required: true },
  callback: { type: Function, required: false },
})
const emits = defineEmits(['update:visible', 'update:app_id'])
const { loading: createAppLoading, handleCreateApp } = useCreateApp()
const { loading: updateAppLoading, handleUpdateApp } = useUpdateApp()
const { app, loadApp } = useGetApp()
const { image_url, handleUploadImage } = useUploadImage()
const defaultForm = {
  fileList: [] as any,
  icon: '',
  name: '',
  description: '',
  agent_type: 'worker' as 'worker' | 'planner',
}
const form = ref({ ...defaultForm })
const formRef = ref<FormInstance>()

// 2.定义隐藏模态窗函数
const hideModal = () => emits('update:visible', false)

// 3.定义表单提交函数
const saveApp = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  // 3.2 检测是保存还是新增，调用不同的API接口
  if (props.app_id) {
    await handleUpdateApp(props.app_id, {
      icon: form.value.icon,
      name: form.value.name,
      description: form.value.description,
    })
  } else {
    await handleCreateApp(form.value)
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
      if (props.app_id) {
        // 4.4 调用接口获取文档片段详情
        await loadApp(props.app_id)

        // 4.5 更新表单数据
        form.value = {
          fileList: [{ uid: '1', name: '应用图标', url: app.value.icon }],
          icon: app.value.icon,
          name: app.value.name,
          description: app.value.description,
          agent_type: app.value.agent_type || 'worker',
        }
      }
    } else {
      // 4.6 关闭弹窗，需要清空表单数据
      form.value = defaultForm
      formRef.value?.resetFields()
      emits('update:app_id', '')
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
        {{ props.app_id === '' ? '创建 AI 应用' : '编辑 AI 应用' }}
      </div>
      <el-button type="text" class="text-gray-700!" size="small" @click="hideModal">
        <template #icon>
          <icon-close />
        </template>
      </el-button>
    </div>
    <!-- 中间表单 -->
    <div class="pt-6">
      <el-form ref="formRef" :model="form" label-position="top" @submit.prevent="saveApp">
        <el-form-item prop="fileList" :rules="[{ required: true, message: '应用图标不能为空' }]">
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
          v-if="!props.app_id"
          prop="agent_type"
          label="应用类型"
          :rules="[{ required: true, message: '应用类型不能为空' }]"
        >
          <el-radio-group v-model="form.agent_type">
            <el-radio-button label="worker">WorkerAgent</el-radio-button>
            <el-radio-button label="planner">PlannerAgent</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          prop="name"
          label="应用名称"
          :rules="[{ required: true, message: '应用名称不能为空' }]"
        >
          <el-input v-model="form.name" placeholder="请输入应用名称" />
        </el-form-item>
        <el-form-item prop="description" label="应用描述">
          <el-input
            v-model="form.description"
            :auto-size="{ minRows: 8, maxRows: 8 }"
            :max-length="800"
            show-word-limit
            placeholder="请输入关于该应用的描述信息"
          />
        </el-form-item>
        <!-- 底部按钮 -->
        <div class="flex items-center justify-between">
          <div class=""></div>
          <el-space :size="16">
            <el-button class="rounded-lg" @click="hideModal">取消</el-button>
            <el-button
              :loading="createAppLoading || updateAppLoading"
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
