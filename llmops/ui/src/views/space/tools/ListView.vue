<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  useCreateApiToolProvider,
  useDeleteApiToolProvider,
  useGetApiToolProvider,
  useGetApiToolProvidersWithPage,
  useUpdateApiToolProvider,
  useValidateOpenAPISchema,
} from '@/hooks/use-tool'
import { useUploadImage } from '@/hooks/use-upload-file'
import { type CreateApiToolProviderRequest } from '@/models/api-tool'
import moment from 'moment/moment'
import { typeMap } from '@/config'
import type { FormInstance, UploadFile, UploadRequestOptions, UploadUserFile } from 'element-plus'

// 1.定义额面所需数据
const route = useRoute()
const props = defineProps({
  createType: { type: String, required: true },
})
const emits = defineEmits(['update:create-type'])
const form = ref<{
  fileList: UploadUserFile[]
  icon: string
  name: string
  openapi_schema: string
  headers: Record<string, any>[]
}>({
  fileList: [],
  icon: '',
  name: '',
  openapi_schema: '',
  headers: [],
})
const { image_url, handleUploadImage } = useUploadImage()
const {
  loading: getApiToolProviderLoading,
  api_tool_provider,
  loadApiToolProvider,
} = useGetApiToolProvider()
const {
  loading: getApiToolProvidersLoading,
  loadingMore: getApiToolProvidersLoadingMore,
  paginator,
  api_tool_providers,
  loadApiToolProviders,
} = useGetApiToolProvidersWithPage()
const { handleDelete: handleDeleteApiToolProvider } = useDeleteApiToolProvider()
const {
  loading: updateApiToolProviderLoading,
  handleUpdateApiToolProvider, //
} = useUpdateApiToolProvider()
const {
  loading: createApiToolProviderLoading,
  handleCreateApiToolProvider, //
} = useCreateApiToolProvider()
const { handleValidateOpenAPISchema } = useValidateOpenAPISchema()
const formRef = ref<FormInstance>()
const showIdx = ref<number>(-1)
const showUpdateModal = ref<boolean>(false)
const tools = computed(() => {
  try {
    // 1.解析openapi_schema数据
    const available_tools = []
    const openapi_schema = JSON.parse(form.value.openapi_schema)

    // 2.检测是否存在paths路径
    if ('paths' in openapi_schema) {
      // 3.循环所有paths并提取工具
      for (const path in openapi_schema['paths']) {
        // 4.遍历对应path下的get和post方法
        for (const method in openapi_schema['paths'][path]) {
          if (['get', 'post'].includes(method)) {
            // 5.提取工具信息，并校验是否存在name、description这两个字段
            const tool = openapi_schema['paths'][path][method]
            if ('operationId' in tool && 'description' in tool) {
              available_tools.push({
                name: tool?.operationId,
                description: tool?.description,
                method: method,
                path: path,
              })
            }
          }
        }
      }
    }
    return available_tools
  } catch (e) {
    return []
  }
})

// 2.定义滚动分页处理器
const handleScroll = (event: Event) => {
  // 2.1 获取滚动距离、可滚动的最大距离、客户端/浏览器窗口的高度
  const { scrollTop, scrollHeight, clientHeight } = event.target as HTMLElement

  // 2.2 判断是否滑动到底部
  if (scrollTop + clientHeight >= scrollHeight - 10) {
    if (getApiToolProvidersLoading.value || getApiToolProvidersLoadingMore.value) return
    loadApiToolProviders(false, String(route.query?.search_word ?? ''))
  }
}

// 3.定义打开更新模态窗
const handleUpdate = async () => {
  // 3.1 获取当前显示的provider_id
  const provider_id = api_tool_providers.value[showIdx.value]['id']

  // 3.2 根据拿到的id获取该工具提供商的详情信息
  await loadApiToolProvider(provider_id)

  // 3.3 更新form表单数据
  formRef.value?.resetFields()
  form.value.fileList = [{ uid: 1, name: '插件图标', url: api_tool_provider.value.icon }]
  form.value.icon = api_tool_provider.value.icon
  form.value.name = api_tool_provider.value.name
  form.value.openapi_schema = api_tool_provider.value.openapi_schema
  form.value.headers = api_tool_provider.value.headers

  showUpdateModal.value = true
}

// 4.定义删除工具提供者处理器
const handleDelete = () => {
  // 4.1 提取选中数据条目的提供者id
  const provider_id = api_tool_providers.value[showIdx.value]['id']

  // 4.2 调用删除Api工具提供者处理器
  handleDeleteApiToolProvider(provider_id, () => {
    // 4.3 关闭模态窗+抽屉
    handleCancel()
    showIdx.value = -1

    // 4.4 重新加载数据
    loadApiToolProviders(true, String(route.query?.search_word ?? ''))
  })
}

// 提交模态窗处理器
const handleSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  const values = form.value

  if (props.createType === 'tool') {
    await handleCreateApiToolProvider(values as CreateApiToolProviderRequest)
  } else if (showUpdateModal.value) {
    await handleUpdateApiToolProvider(
      api_tool_providers.value[showIdx.value]['id'],
      values as CreateApiToolProviderRequest,
    )
  }

  // 5.执行后续操作，涵盖隐藏模态窗、隐藏抽屉
  handleCancel()
  showIdx.value = -1

  // 6.重新加载数据
  await loadApiToolProviders(true, String(route.query?.search_word ?? ''))
}

// 取消显示模态窗处理器
const handleCancel = () => {
  // 1.重置整个表单的数据
  formRef.value?.resetFields()

  // 2.隐藏表单模态窗
  emits('update:create-type', '')
  showUpdateModal.value = false
}

// 页面DOM加载完毕初始化数据
onMounted(() => loadApiToolProviders(true, String(route.query?.search_word ?? '')))

// 监听路由query变化
watch(
  () => route.query?.search_word,
  (newValue) => {
    loadApiToolProviders(true, String(newValue ?? ''))
  },
)

// 监听路由create_type变化
watch(
  () => route.query?.create_type,
  (newValue) => {
    if (newValue === 'tool') emits('update:create-type', 'tool')
  },
  { immediate: true },
)
</script>

<template>
  <div
    v-loading="getApiToolProvidersLoading"
    class="block h-full w-full scrollbar-y-sleek overflow-scroll"
    @scroll="handleScroll"
  >
    <!-- 底部插件列表 -->
    <el-row :gutter="20" class="flex-1">
      <!-- 有数据的UI状态 -->
      <el-col
        v-for="(provider, idx) in api_tool_providers"
        :key="provider.name"
        :span="6"
        class="mb-5"
      >
        <el-card shadow="hover" class="cursor-pointer rounded-lg transition-shadow" @click="showIdx = Number(idx)">
          <!-- 顶部提供商名称 -->
          <div class="flex items-center gap-3 mb-3">
            <!-- 左侧图标 -->
            <el-avatar :size="40" shape="square" :src="provider.icon" />
            <!-- 右侧工具信息 -->
            <div class="flex flex-col">
              <div class="text-base text-gray-900 font-bold">{{ provider.name }}</div>
              <div class="text-xs text-gray-500 line-clamp-1">
                提供商 {{ provider.name }} · {{ provider.tools.length }} 插件
              </div>
            </div>
          </div>
          <!-- 提供商的描述信息 -->
          <div class="leading-[18px] text-gray-500 h-[72px] line-clamp-4 mb-2">
            {{ provider.description }}
          </div>
          <!-- 提供商的发布信息 -->
          <div class="flex items-center gap-1.5">
            <el-avatar :size="18" class="bg-blue-700">
              <icon-user />
            </el-avatar>
            <div class="text-xs text-gray-400">
              慕小课 · 编辑时间
              {{ moment(provider.created_at * 1000).format('MM-DD HH:mm') }}
            </div>
          </div>
        </el-card>
      </el-col>
      <!-- 没数据的UI状态 -->
      <el-col v-if="api_tool_providers.length === 0" :span="24">
        <el-empty
          description="没有可用的API插件"
          class="h-[400px] flex flex-col items-center justify-center"
        />
      </el-col>
    </el-row>
    <!-- 加载器 -->
    <el-row v-if="paginator.total_page >= 2">
      <el-col v-if="paginator.current_page <= paginator.total_page" :span="24" class="text-center">
        <el-space class="my-4">
          <div />
          <div class="text-gray-400">
            {{ getApiToolProvidersLoadingMore ? '加载中…' : '向下滑动加载更多' }}
          </div>
        </el-space>
      </el-col>
      <!-- 数据加载完成 -->
      <el-col v-else :span="24" class="text-center">
        <div class="text-gray-400 my-4">数据已加载完成</div>
      </el-col>
    </el-row>
    <!-- 卡片抽屉 -->
    <el-drawer
      :model-value="showIdx !== -1"
      :width="350"
      title="工具详情"
      :drawer-style="{ background: '#F9FAFB' }"
      @update:model-value="(open: boolean) => { if (!open) showIdx = -1 }"
    >
      <!-- 外部容器，用于判断showIdx是否为-1，为-1的时候就不显示 -->
      <div v-if="showIdx != -1" class="">
        <!-- 顶部提供商名称 -->
        <div class="flex items-center gap-3 mb-3">
          <!-- 左侧图标 -->
          <el-avatar :size="40" shape="square" :src="api_tool_providers[showIdx].icon" />
          <!-- 右侧工具信息 -->
          <div class="flex flex-col">
            <div class="text-base text-gray-900 font-bold">
              {{ api_tool_providers[showIdx].name }}
            </div>
            <div class="text-xs text-gray-500 line-clamp-1">
              提供商 {{ api_tool_providers[showIdx].name }} ·
              {{ api_tool_providers[showIdx].tools.length }} 插件
            </div>
          </div>
        </div>
        <!-- 提供商的描述信息 -->
        <div class="leading-[18px] text-gray-500 mb-4">
          {{ api_tool_providers[showIdx].description }}
        </div>
        <!-- 编辑按钮 -->
        <el-button
          :loading="getApiToolProviderLoading"
          plain
          class="mb-2 w-full rounded-lg border-dashed"
          @click="handleUpdate"
        >
          <template #icon>
            <icon-settings />
          </template>
          编辑工具
        </el-button>
        <!-- 分隔符 -->
        <hr class="my-4" />
        <!-- 提供者工具 -->
        <div class="flex flex-col gap-2">
          <div class="text-xs text-gray-500">
            包含 {{ api_tool_providers[showIdx].tools.length }} 个工具
          </div>
          <!-- 工具列表 -->
          <el-card
            v-for="tool in api_tool_providers[showIdx].tools"
            :key="tool.name"
            class="cursor-pointer flex flex-col rounded-xl"
          >
            <!-- 工具名称 -->
            <div class="font-bold text-gray-900 mb-2">{{ tool.name }}</div>
            <!-- 工具描述 -->
            <div class="text-gray-500 text-xs">{{ tool.description }}</div>
            <!-- 工具参数 -->
            <div v-if="tool.inputs.length > 0" class="">
              <!-- 分隔符 -->
              <div class="flex items-center gap-2 my-4">
                <div class="text-xs font-bold text-gray-500">参数</div>
                <hr class="flex-1" />
              </div>
              <!-- 参数列表 -->
              <div class="flex flex-col gap-4">
                <div v-for="input in tool.inputs" :key="input.name" class="flex flex-col gap-2">
                  <!-- 上半部分 -->
                  <div class="flex items-center gap-2 text-xs">
                    <div class="text-gray-900 font-bold">{{ input.name }}</div>
                    <div class="text-gray-500">{{ typeMap[input.type] }}</div>
                    <div v-if="input.required" class="text-red-700">必填</div>
                  </div>
                  <!-- 参数描述信息 -->
                  <div class="text-xs text-gray-500">{{ input.description }}</div>
                </div>
              </div>
            </div>
          </el-card>
        </div>
      </div>
    </el-drawer>
    <!-- 新建/修改模态窗 -->
    <el-dialog
      :width="630"
      :model-value="props.createType === 'tool' || showUpdateModal"
      class="rounded-xl"
      @update:model-value="(open: boolean) => { if (!open) handleCancel() }"
    >
      <!-- 顶部标题 -->
      <div class="flex items-center justify-between">
        <div class="text-lg font-bold text-gray-700">
          {{ props.createType === 'tool' ? '新建' : '更新' }}插件
        </div>
        <el-button type="text" class="text-gray-700!" size="small" @click="handleCancel">
          <template #icon>
            <icon-close />
          </template>
        </el-button>
      </div>
      <!-- 中间表单 -->
      <div class="pt-6">
        <el-form ref="formRef" :model="form" @submit.prevent="handleSubmit" label-position="top">
          <el-form-item prop="fileList" :rules="[{ required: true, message: '插件图标不能为空' }]">
            <el-upload
              :limit="1"
              list-type="picture-card"
              accept="image/png, image/jpeg"
              class="w-auto! mx-auto"
              v-model:file-list="form.fileList"
              :http-request="
                (option: UploadRequestOptions) => {
                  const uploadTask = async () => {
                    const { file, onSuccess, onError } = option
                    try {
                      await handleUploadImage(file)
                      form.icon = image_url
                      onSuccess(image_url)
                    } catch (error) {
                      onError(error as any)
                    }
                  }

                  uploadTask()

                  return {}
                }
              "
              :on-before-remove="
                async (_uploadFile: UploadFile) => {
                  form.icon = ''
                  return true
                }
              "
            />
          </el-form-item>
          <el-form-item
            prop="name"
            label="插件名称"
            :rules="[{ required: true, message: '插件名称不能为空' }]"
          >
            <el-input
              v-model="form.name"
              placeholder="请输入插件名称，确保名称含义清晰"
              show-word-limit
              :max-length="60"
            />
          </el-form-item>
          <el-form-item
            prop="openapi_schema"
            label="OpenAPI Schema"
            :rules="[{ required: true, message: 'OpenAPI Schema不能为空' }]"
          >
            <el-input
              v-model="form.openapi_schema"
              :auto-size="{ minRows: 4, maxRows: 6 }"
              placeholder="在此处输入您的 OpenAPI Schema"
              @blur="
                () => {
                  if (form.openapi_schema.trim() !== '') {
                    // 调用验证openapi_schema接口
                    handleValidateOpenAPISchema(form.openapi_schema)
                  }
                }
              "
            />
          </el-form-item>
          <el-form-item label="可用工具">
            <!-- 可用工具表格 -->
            <div class="rounded-lg border border-gray-200 w-full overflow-x-auto">
              <table class="w-full leading-[18px] text-xs text-gray-700 font-normal">
                <thead class="text-gray-500">
                  <tr class="border-b border-gray-200">
                    <th class="p-2 pl-3 font-medium">名称</th>
                    <th class="p-2 pl-3 font-medium w-[236px]">描述</th>
                    <th class="p-2 pl-3 font-medium">方法</th>
                    <th class="p-2 pl-3 font-medium">路径</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(tool, idx) in tools"
                    :key="idx"
                    class="border-b last:border-0 border-gray-200 text-gray-700"
                  >
                    <td class="p-2 pl-3">{{ tool.name }}</td>
                    <td class="p-2 pl-3 w-[236px]">{{ tool.description }}</td>
                    <td class="p-2 pl-3">{{ tool.method }}</td>
                    <td class="p-2 pl-3 w-[62px]">{{ tool.path }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </el-form-item>
          <el-form-item label="Headers">
            <!-- 请求头表单 -->
            <div class="rounded-lg border border-gray-200 w-full overflow-x-auto">
              <table class="w-full leading-[18px] text-xs text-gray-700 font-normal mb-3">
                <thead class="text-gray-500">
                  <tr class="border-b border-gray-200">
                    <th class="p-2 pl-3 font-medium">Key</th>
                    <th class="p-2 pl-3 font-medium">Value</th>
                    <th class="p-2 pl-3 font-medium w-[50px]">操作</th>
                  </tr>
                </thead>
                <tbody v-if="form.headers.length > 0" class="border-b border-gray-200">
                  <tr
                    v-for="(header, idx) in form.headers"
                    :key="idx"
                    class="border-b last:border-0 border-gray-200"
                  >
                    <td class="p-2 pl-3">
                      <el-form-item :prop="`headers.${idx}.key`" class="m-0">
                        <el-input v-model="header.key" placeholder="请输入请求头键名" />
                      </el-form-item>
                    </td>
                    <td class="p-2 pl-3">
                      <el-form-item :prop="`headers.${idx}.value`" class="m-0">
                        <el-input v-model="header.value" placeholder="请输入请求头键值内容" />
                      </el-form-item>
                    </td>
                    <td class="p-2 pl-3">
                      <el-button
                        size="mini"
                        type="text"
                        class="text-gray-700!"
                        @click="form.headers.splice(idx, 1)"
                      >
                        <template #icon>
                          <icon-delete />
                        </template>
                      </el-button>
                    </td>
                  </tr>
                </tbody>
              </table>
              <el-button
                size="mini"
                class="rounded-sm ml-3 mb-3 text-gray-700!"
                @click="form.headers.push({ key: '', value: '' })"
              >
                <template #icon>
                  <icon-plus />
                </template>
                增加参数
              </el-button>
            </div>
          </el-form-item>
          <!-- 底部按钮 -->
          <div class="flex items-center justify-between">
            <div class="">
              <el-button
                v-if="showUpdateModal"
                class="rounded-lg text-red-700!"
                @click="handleDelete"
              >
                删除
              </el-button>
            </div>
            <el-space :size="16">
              <el-button class="rounded-lg" @click="handleCancel">取消</el-button>
              <el-button
                :loading="updateApiToolProviderLoading || createApiToolProviderLoading"
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
  </div>
</template>

<style scoped></style>
