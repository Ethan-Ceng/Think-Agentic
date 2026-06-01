<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { FormInstance, UploadRequestOptions } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useCreateDocuments, useGetDocumentsStatus } from '@/hooks/use-dataset'
import { useUploadFile } from '@/hooks/use-upload-file'
import { unescapeString } from '@/utils/helper'
import type { CreateDocumentsRequest } from '@/models/dataset'

// 1.定义页面逻辑基础数据，涵盖定时器、路由、当前步骤书、表单信息等
let timer: any = 0
let batch = ''
let fetchCount = 0
const route = useRoute()
const {
  loading: createDocumentsLoading,
  create_documents_result,
  handleCreateDocuments,
} = useCreateDocuments()
const { upload_file, handleUploadFile } = useUploadFile()
const { documents_status_result, loadDocumentsStatus } = useGetDocumentsStatus()
const currentStep = ref(1)
const createDocumentsForm = ref<Record<string, any>>({
  file_list: [],
  process_type: 'automatic',
  rule: {
    separators: ['\\n'],
    chunk_size: 500,
    chunk_overlap: 50,
    pre_process_rules: [],
  },
})
const customRuleFormRef = ref<FormInstance>()
const documents = ref<Array<any>>([])

// 2.定义下一步处理函数
const nextStep = async () => {
  // 2.1 判断下当前所处的步骤并执行不同的操作
  if (currentStep.value === 1) {
    // 2.2 检查是否已经上传了文件，如果没上传则不允许点击下一步
    if (createDocumentsForm.value.file_list.length === 0) {
      ElMessage.error('请上传需要添加到知识库的文件')
      return
    }

    // 2.3 检查所有文件是否全部上传完成
    const isUploaded = createDocumentsForm.value.file_list.every(
      (fileItem: any) => fileItem.response?.id,
    )
    if (!isUploaded) {
      ElMessage.warning('文件正在上传中，请稍等')
      return
    }

    // 2.4 进入下一步
    currentStep.value++
  } else {
    // 2.5 当前处于第2页，需要根据不同的处理类型执行不同的操作
    if (createDocumentsForm.value.process_type === 'custom') {
      // 2.6 校验表单数据监测是否出错
      try {
        await customRuleFormRef.value?.validate()
      } catch {
        return
      }
    }

    // 2.7 如果校验成功或者是自动规则，则执行下一步
    try {
      // 2.8 将加载状态设置为true，并将表单数据转换成api接口数据
      const req: Record<string, any> = {
        upload_file_ids: createDocumentsForm.value.file_list.map(
          (fileItem: any) => fileItem?.response?.id,
        ),
        process_type: createDocumentsForm.value.process_type,
      }

      // 2.9 如果处理类型为自定义，则需要添加上自定义规则
      if (createDocumentsForm.value.process_type === 'custom') {
        req.rule = {
          pre_process_rules: [
            {
              id: 'remove_extra_space',
              enabled:
                createDocumentsForm.value.rule.pre_process_rules.includes('remove_extra_space'),
            },
            {
              id: 'remove_url_and_email',
              enabled:
                createDocumentsForm.value.rule.pre_process_rules.includes('remove_url_and_email'),
            },
          ],
          segment: {
            separators: createDocumentsForm.value.rule.separators.map((separator: any) =>
              unescapeString(separator),
            ),
            chunk_size: createDocumentsForm.value.rule.chunk_size,
            chunk_overlap: createDocumentsForm.value.rule.chunk_overlap,
          },
        }
      }

      // 2.10 发起请求并获取数据
      await handleCreateDocuments(String(route.params?.dataset_id), req as CreateDocumentsRequest)
      batch = create_documents_result.value.batch

      // 2.11 先调用一次获取文档状态，然后创建定时器
      await fetchDocumentsStatus()
      startTimer()

      // 2.12 创建文档预处理成功，当前步骤数+1
      currentStep.value++
    } finally {
      createDocumentsLoading.value = false
    }
  }
}

// 3.定义获取文档状态数据函数
const fetchDocumentsStatus = async () => {
  // 3.1 调用接口获取文档状态数据
  fetchCount++
  await loadDocumentsStatus(String(route.params?.dataset_id), batch)

  // 3.2 同步文档状态信息
  documents.value = documents_status_result.value

  // 3.3 如果请求次数超过限制，则停止
  if (fetchCount >= 30) stopTimer()

  // 3.4 如果文档全部都处理完成（涵盖处理完成+错误），则停止
  const isCompleted = documents_status_result.value.every(
    (document) => document.status === 'completed' || document.status === 'error',
  )
  if (isCompleted) stopTimer()
}

// 4.定义开始定时器函数
const startTimer = () => (timer = setInterval(fetchDocumentsStatus, 5000))

// 5.停止定时器函数
const stopTimer = () => {
  if (timer) {
    clearInterval(timer)
    timer = 0
  }
}

// 6.页面卸载时同步卸载定时器
onUnmounted(() => stopTimer())
</script>

<template>
  <div class="p-6">
    <!-- 回退按钮与标题 -->
    <div class="flex items-center mb-6 gap-4">
      <!-- 左侧回退按钮 -->
      <router-link
        :to="{
          name: 'space-datasets-documents-list',
          params: { dataset_id: route.params?.dataset_id as string },
        }"
      >
        <el-button size="mini" type="text" class="text-gray-700!">
          <template #icon>
            <icon-left />
          </template>
        </el-button>
      </router-link>
      <div class="text-lg font-bold text-gray-700">添加文件</div>
    </div>
    <!-- 步骤条 -->
    <div class="w-[520px] mx-auto">
      <el-steps :current="currentStep">
        <el-step>上传</el-step>
        <el-step>分段设置</el-step>
        <el-step>数据处理</el-step>
      </el-steps>
    </div>
    <!-- 步骤条页面 -->
    <div class="min-h-[calc(100vh-160px)] p-[48px]">
      <!-- 上传页面 -->
      <div v-if="currentStep === 1" class="">
        <!-- 上传文件按钮 -->
        <el-upload
          v-model:file-list="createDocumentsForm.file_list"
          draggable
          accept=".doc,.docx,.pdf,.txt,.md,.markdown"
          :limit="10"
          multiple
          tip="支持PDF、TXT、DOC、DOCX、MD，最多可上传10个文件，每个文件的大小不超过10MB"
          :http-request="
            (option: UploadRequestOptions) => {
              // 1.提取选项中的文件选项以及成功回调
              const { file, onSuccess, onError } = option

              const uploadTask = async () => {
                try {
                  await handleUploadFile(file)
                  onSuccess(upload_file)
                } catch (error) {
                  onError(error as any)
                }
              }

              // 2.调用api接口上传文件并添加数据
              uploadTask()

              return { abort: () => {} }
            }
          "
        />
      </div>
      <!-- 分段设置页面 -->
      <div v-else-if="currentStep === 2" class="">
        <!-- 自动分段与清洗 -->
        <div
          :class="`px-5 py-4 bg-white rounded-lg border cursor-pointer mb-4 hover:border-blue-700 ${createDocumentsForm.process_type === 'automatic' ? 'border-blue-700' : ''}`"
          @click="createDocumentsForm.process_type = 'automatic'"
        >
          <div class="font-bold text-gray-700 mb-2">自动分段与清洗</div>
          <div class="text-gray-500">自动分段与预处理规则</div>
        </div>
        <!-- 自定义 -->
        <div
          :class="`px-5 py-4 bg-white rounded-lg border cursor-pointer hover:border-blue-700 ${createDocumentsForm.process_type === 'custom' ? 'border-blue-700' : ''}`"
          @click="createDocumentsForm.process_type = 'custom'"
        >
          <div class="font-bold text-gray-700 mb-2">自定义</div>
          <div class="text-gray-500">自定义分段规则、分段长度与预处理规则</div>
          <!-- 自定义表单 -->
          <div v-if="createDocumentsForm.process_type === 'custom'" class="">
            <el-divider />
            <!-- 表单选项 -->
            <el-form :model="createDocumentsForm.rule" ref="customRuleFormRef" label-position="top">
              <el-form-item
                prop="separators"
                label="分段标识符"
                required
                :rules="[{ required: true, message: '分段标识符不能为空' }]"
              >
                <el-input-tag
                  v-model="createDocumentsForm.rule.separators"
                  placeholder="请输入分段标识符，按下Enter结束"
                />
              </el-form-item>
              <el-form-item
                prop="chunk_size"
                label="分段最大长度"
                required
                :rules="[{ required: true, message: '分段最大长度不能为空' }]"
              >
                <el-input-number
                  v-model="createDocumentsForm.rule.chunk_size"
                  :min="100"
                  :max="1000"
                  :step="1"
                  placeholder="请输入100-1000的数字"
                />
              </el-form-item>
              <el-form-item
                prop="chunk_overlap"
                label="块重叠数"
                required
                :rules="[{ required: true, message: '块重叠大小不能为空' }]"
              >
                <el-input-number
                  v-model="createDocumentsForm.rule.chunk_overlap"
                  :min="0"
                  :max="500"
                  :step="1"
                  placeholder="请输入0-500的数字"
                />
              </el-form-item>
              <el-form-item prop="pre_process_rules" label="文本预处理规则">
                <el-checkbox-group
                  v-model="createDocumentsForm.rule.pre_process_rules"
                  direction="vertical"
                >
                  <el-checkbox value="remove_extra_space">
                    替换掉连续的空格、换行符和制表符
                  </el-checkbox>
                  <el-checkbox value="remove_url_and_email">删除所有 URL 和电子邮件</el-checkbox>
                </el-checkbox-group>
              </el-form-item>
            </el-form>
          </div>
        </div>
      </div>
      <!-- 数据处理页面 -->
      <div v-else class="">
        <!-- 数据处理状态提示 -->
        <div class="text-gray-900 mb-4 text-base">服务器正在处理中</div>
        <!-- 处理中的文档列表 -->
        <div class="flex flex-col gap-2">
          <div
            v-for="document in documents"
            :key="document.id"
            class="flex items-center justify-between px-4 py-3 bg-white rounded-lg border"
          >
            <!-- 左侧文件信息 -->
            <div class="flex items-center gap-2.5">
              <el-avatar shape="square" class="bg-blue-700" :size="32">
                <icon-file />
              </el-avatar>
              <div class="">
                <div class="text-gray-700">{{ document.name }}</div>
                <div class="text-gray-500">{{ (document.size / 1024).toFixed(2) }}kb</div>
              </div>
            </div>
            <!-- 处理的百分比 -->
            <div v-if="document.segment_count === 0" class="text-gray-500">0.00%</div>
            <div v-else-if="document.status === 'error'" class="">处理出错</div>
            <div v-else-if="document.status === 'completed'" class="">处理完成</div>
            <div v-else class="text-gray-500">
              {{ ((document.completed_segment_count / document.segment_count) * 100).toFixed(2) }}%
            </div>
          </div>
        </div>
      </div>
    </div>
    <!-- 按钮：涵盖上一步和下一步 -->
    <div class="flex items-center justify-between px-[48px]">
      <div class=""></div>
      <div class="flex items-center gap-2">
        <el-button
          v-if="currentStep === 2"
          class="rounded-lg"
          @click="
            () => {
              if (currentStep > 1) currentStep--
            }
          "
        >
          上一步
        </el-button>
        <el-button
          :loading="createDocumentsLoading"
          v-if="currentStep <= 2"
          type="primary"
          class="rounded-lg"
          @click="nextStep"
        >
          下一步
        </el-button>
        <!-- 数据处理页面显示的内容 -->
        <div v-if="currentStep === 3" class="flex items-center gap-2">
          <div class="text-gray-500">点击确认不影响数据处理，处理完毕后可进行引用</div>
          <router-link
            :to="{
              name: 'space-datasets-documents-list',
              params: { dataset_id: route.params?.dataset_id as string },
            }"
          >
            <el-button type="primary" class="rounded-lg">确定</el-button>
          </router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped></style>
