<script setup lang="ts">
import { nextTick, onMounted, type PropType, ref, watch } from 'vue'
import { useUpdateDraftAppConfig } from '@/hooks/use-app'
import { useGetDatasetsWithPage } from '@/hooks/use-dataset'
import { cloneDeep, isEqual } from 'lodash'
import { ElMessage } from 'element-plus'

// 1.定义自定义组件所需数据
const props = defineProps({
  app_id: { type: String, default: '', required: true },
  retrieval_config: {
    type: Object,
    default: () => {
      return {}
    },
    required: true,
  },
  datasets: {
    type: Array as PropType<
      {
        id: string
        name: string
        icon: string
        description: string
      }[]
    >,
    default: () => [],
    required: true,
  },
})
const emits = defineEmits(['update:datasets', 'update:retrieval_config'])
const { loading: updateDraftAppConfigLoading, handleUpdateDraftAppConfig } =
  useUpdateDraftAppConfig()
const { loading, paginator, datasets: apiDatasets, loadDatasets } = useGetDatasetsWithPage()
const datasetsModalVisible = ref(false)
const retrievalConfigModalVisible = ref(false)
const isDatasetsInit = ref(false)
const activateDatasets = ref<Record<string, any>[]>([])
const originDatasets = ref<Record<string, any>[]>([])
const retrievalConfigForm = ref<Record<string, any>>({})
const originRetrievalConfigForm = ref<Record<string, any>>({})
const isRetrievalConfigInit = ref(false)

// 2.定义滚动数据分页处理器
const handleScroll = async (event: Event) => {
  // 2.1 获取滚动距离、可滚动的最大距离、客户端/浏览器窗口的高度
  const { scrollTop, scrollHeight, clientHeight } = event.target as HTMLElement

  // 2.2 判断是否滑动到底部
  if (scrollTop + clientHeight >= scrollHeight - 10) {
    if (loading.value) return
    await loadDatasets()
  }
}

// 3.定义判断知识库数据是否发生变化函数
const isDatasetsModified = () => {
  return isEqual(activateDatasets.value, originDatasets.value)
}

// 4.定义判断检索设置是否发生变化函数
const isRetrievalConfigFormModified = () => {
  return isEqual(retrievalConfigForm.value, originRetrievalConfigForm.value)
}

// 5.定义取消模态窗处理器
const handleCancelDatasetsModal = () => {
  // 5.1 隐藏模态窗
  datasetsModalVisible.value = false

  // 5.2 还原初始值
  activateDatasets.value = originDatasets.value
  isDatasetsInit.value = false
}

// 6.定义取消检索设置模态窗处理器
const handleCancelRetrievalConfigModal = () => {
  // 6.1 隐藏模态窗
  retrievalConfigModalVisible.value = false

  // 6.2 还原初始值
  retrievalConfigForm.value = originRetrievalConfigForm.value
  isRetrievalConfigInit.value = false
}

// 7.知识库选择处理器
const handleSelectDataset = (idx: number) => {
  // 7.1 提取对应的知识库id
  const dataset = apiDatasets.value[idx]

  // 7.2 检测id是否选中，如果是选中则删除
  if (activateDatasets.value.some((activateDataset) => activateDataset.id === dataset.id)) {
    activateDatasets.value = activateDatasets.value.filter(
      (activateDataset) => activateDataset.id !== dataset.id,
    )
  } else {
    // 7.3 检测已关联的知识库数量
    if (activateDatasets.value.length >= 5) {
      ElMessage.warning('关联知识库已超过5个，无法继续关联')
      return
    }
    // 7.4 添加数据到激活知识库列表
    activateDatasets.value.push({
      id: dataset.id,
      name: dataset.name,
      icon: dataset.icon,
      description: dataset.description,
    })
  }
}

// 8.提交更新关联知识库
const handleSubmitDatasets = async () => {
  // 8.1 处理数据并完成API接口提交
  await handleUpdateDraftAppConfig(props.app_id, {
    datasets: activateDatasets.value.map((activateDataset) => activateDataset.id),
  })

  // 8.2 接口更新更新成功，同步表单信息
  originDatasets.value = activateDatasets.value
  await nextTick()

  // 8.3 双向同步更新props中的数据
  emits('update:datasets', activateDatasets.value)

  // 8.4 隐藏模态窗
  handleCancelDatasetsModal()
}

// 9.提交更新检索配置
const handleSubmitRetrievalConfig = async () => {
  // 9.1 处理数据并完成API接口提交
  await handleUpdateDraftAppConfig(props.app_id, {
    retrieval_config: retrievalConfigForm.value as any,
  })

  // 9.2 接口更新更新成功，同步表单信息
  originRetrievalConfigForm.value = retrievalConfigForm.value

  // 9.3 双向同步更新props中的数据
  emits('update:retrieval_config', retrievalConfigForm.value)

  // 9.4 隐藏模态窗
  handleCancelRetrievalConfigModal()
}

// 10.监听草稿配置关联的知识库列表
watch(
  () => props.datasets,
  (newValue) => {
    // 10.1 检测数据是否初始化
    if (!isDatasetsInit.value || !isDatasetsModified()) {
      // 10.2 判断草稿配置是否已传递配置
      if (newValue && newValue.length > 0) {
        // 10.3 赋初始值
        const initData = props.datasets.map((dataset) => {
          return {
            id: dataset.id,
            name: dataset.name,
            icon: dataset.icon,
            description: dataset.description,
          }
        })
        activateDatasets.value = cloneDeep(initData)
        originDatasets.value = cloneDeep(initData)

        // 10.4 修改初始化状态
        isDatasetsInit.value = true
      }
    }
  },
  { immediate: true, deep: true },
)

// 11.监听检索配置
watch(
  () => props.retrieval_config,
  (newValue) => {
    // 11.1 检测是否是否更新并且未初始化
    if (!isRetrievalConfigInit.value || !isRetrievalConfigFormModified()) {
      if (newValue && Object.keys(newValue).length > 0) {
        // 11.2 更新表单数据和备份数据
        retrievalConfigForm.value = { ...newValue }
        originRetrievalConfigForm.value = { ...newValue }

        // 11.3 标记为已初始化
        isRetrievalConfigInit.value = true
      }
    }
  },
  { immediate: true, deep: true },
)

// 12.监听知识库模态窗显示or隐藏
watch(
  () => datasetsModalVisible.value,
  async (newValue) => {
    // 12.1 显示状态，重新加载数据，获取最新的知识库列表
    if (newValue) {
      await loadDatasets(true)
    } else {
      // 12.2 隐藏状态，清空数据
      apiDatasets.value.splice(0, apiDatasets.value.length)
    }
  },
)

onMounted(() => {
  loadDatasets(true)
})
</script>

<template>
  <div class="">
    <el-collapse-item name="datasets" class="app-ability-item">
      <template #title>
        <div class="flex w-full items-center justify-between gap-2 pr-2">
          <div class="flex min-w-0 items-center text-sm font-bold leading-none text-gray-700">知识库</div>
          <div class="flex shrink-0 items-center self-stretch" @click.stop>
            <el-space :size="8" class="inline-flex items-center">
              <el-button
                size="small"
                class="!flex !h-7 items-center gap-1 rounded-md px-2"
                @click.stop="retrievalConfigModalVisible = true"
              >
                <template #icon>
                  <icon-language />
                </template>
                <span v-if="retrieval_config?.retrieval_strategy === 'semantic'">相似性检索</span>
                <span v-else-if="retrieval_config?.retrieval_strategy === 'full_text'">全文检索</span>
                <span v-else>混合检索</span>
              </el-button>
              <el-button
                size="small"
                type="text"
                class="!flex !h-7 !w-7 !items-center !justify-center text-gray-700!"
                @click.stop="datasetsModalVisible = true"
              >
                <template #icon>
                  <icon-plus />
                </template>
              </el-button>
            </el-space>
          </div>
        </div>
      </template>
      <template #icon="{ isActive }">
        <icon-down v-if="isActive" />
        <icon-right v-else />
      </template>
      <div v-if="props.datasets?.length > 0" class="flex flex-col gap-1">
        <div
          v-for="(dataset, idx) in props.datasets"
          :key="dataset.id"
          class="flex items-center justify-between bg-white p-3 rounded-lg cursor-pointer hover:shadow-xs group"
        >
          <!-- 左侧知识库信息 -->
          <div class="flex items-center gap-2">
            <!-- 图标 -->
            <el-avatar
              :size="36"
              shape="square"
              class="rounded-sm shrink-0"
              :src="dataset.icon"
            />
            <!-- 名称与描述信息 -->
            <div class="flex flex-col flex-1 gap-1 h-9">
              <div class="text-gray-700 font-bold leading-[18px] line-clamp-1 break-all">
                {{ dataset.name }}
              </div>
              <div class="text-gray-500 text-xs line-clamp-1 break-all">
                {{ dataset.description }}
              </div>
            </div>
          </div>
          <!-- 右侧删除按钮 -->
          <el-button
            size="mini"
            type="text"
            class="hidden group-hover:block shrink-0 ml-2 text-red-700! rounded-sm"
            @click="
              async () => {
                // 1.清除props中指定的数据
                const newDatasets = [...props.datasets]
                newDatasets.splice(idx, 1)

                // 2.提交草稿配置到接口
                await handleUpdateDraftAppConfig(props.app_id, {
                  datasets: newDatasets.map((item) => item.id),
                })

                // 3.更新数据并确保数据完成更新
                isDatasetsInit = false
                emits('update:datasets', newDatasets)
              }
            "
          >
            <template #icon>
              <icon-delete />
            </template>
          </el-button>
        </div>
      </div>
      <div v-else class="text-xs text-gray-500 leading-[22px]">
        引用文本类型的数据，实现知识问答，应用最多支持关联 5 个知识库。
      </div>
    </el-collapse-item>
    <!-- 知识库模态窗 -->
    <el-dialog
      v-model="datasetsModalVisible"
      header-class="hidden"
      :show-close="false"
      :width="400"
      class="datasets-modal"
      modal-class="h-[calc(100vh-32px)] right-4"
      @close="handleCancelDatasetsModal"
    >
      <!-- 顶部标题 -->
      <div class="flex items-center justify-between mb-6">
        <div class="text-lg font-bold text-gray-700">选择引用知识库</div>
        <el-button
          type="text"
          class="text-gray-700!"
          size="small"
          @click="handleCancelDatasetsModal"
        >
          <template #icon>
            <icon-close />
          </template>
        </el-button>
      </div>
      <!-- 中间知识库容器 -->
      <div class="h-[calc(100vh-180px)] mb-4 overflow-scroll scrollbar-y-sleek">
        <div
          v-loading="loading"
          class="block h-full w-full scrollbar-y-sleek overflow-scroll"
          @scroll="handleScroll"
        >
          <!-- 知识库列表 -->
          <div class="flex flex-col gap-2">
            <!-- 有数据UI状态 -->
            <div
              v-for="(dataset, idx) in apiDatasets"
              :key="dataset.id"
              :class="`flex items-center gap-2 border px-3 py-2 rounded-lg cursor-pointer hover:bg-blue-50 hover:border-blue-700 ${activateDatasets.some((activateDataset) => activateDataset.id === dataset.id) ? 'bg-blue-50 border-blue-700' : ''}`"
              @click="() => handleSelectDataset(idx)"
            >
              <el-avatar
                :size="24"
                shape="square"
                class="shrink-0 rounded-sm"
                :src="dataset.icon"
              />
              <div class="line-clamp-1 text-gray-500 flex-1">{{ dataset.name }}</div>
            </div>
            <!-- 无数据UI状态 -->
            <el-empty
              v-if="apiDatasets.length === 0"
              description="没有可用的知识库"
              class="h-[400px] flex flex-col items-center justify-center"
            />
          </div>
          <!-- 加载器 -->
          <el-row v-if="paginator.total_page >= 2">
            <!-- 加载数据中 -->
            <el-col
              v-if="paginator.current_page <= paginator.total_page"
              :span="24"
              class="text-center!"
            >
              <el-space class="my-4">
                <div />
                <div class="text-gray-400">加载中</div>
              </el-space>
            </el-col>
            <!-- 数据加载完成 -->
            <el-col v-else :span="24" class="text-center!">
              <div class="text-gray-400 my-4">数据已加载完成</div>
            </el-col>
          </el-row>
        </div>
      </div>
      <!-- 底部选中知识库及按钮 -->
      <div class="flex items-center justify-between">
        <!-- 左侧提示文字 -->
        <div class="">{{ activateDatasets.length }} 个知识库被选中</div>
        <!-- 按钮组 -->
        <el-space :size="12">
          <el-button class="rounded-lg" @click="handleCancelDatasetsModal">取消</el-button>
          <el-button
            :loading="updateDraftAppConfigLoading"
            type="primary"
            class="rounded-lg"
            @click="handleSubmitDatasets"
          >
            添加
          </el-button>
        </el-space>
      </div>
    </el-dialog>
    <!-- 检索设置模态窗 -->
    <el-dialog
      v-model="retrievalConfigModalVisible"
      header-class="hidden"
      :show-close="false"
      modal-class="rounded-xl"
      @close="handleCancelRetrievalConfigModal"
    >
      <!-- 顶部标题 -->
      <div class="flex items-center justify-between">
        <div class="text-lg font-bold text-gray-700">检索设置</div>
        <el-button
          type="text"
          class="text-gray-700!"
          size="small"
          @click="handleCancelRetrievalConfigModal"
        >
          <template #icon>
            <icon-close />
          </template>
        </el-button>
      </div>
      <!-- 中间表单内容 -->
      <el-form :model="retrievalConfigForm" @submit.prevent="handleSubmitRetrievalConfig" class="pt-6">
        <el-form-item prop="retrieval_strategy" label="检索策略">
          <el-radio-group v-model="retrievalConfigForm.retrieval_strategy">
            <el-radio label="hybrid">混合策略</el-radio>
            <el-radio label="full_text">全文检索</el-radio>
            <el-radio label="semantic">相似性检索</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item prop="k" label="最大召回数量">
          <div class="flex items-center gap-4 w-full pl-3">
            <el-slider v-model="retrievalConfigForm.k" :step="1" :min="1" :max="10" />
            <el-input-number v-model="retrievalConfigForm.k" class="w-[80px]" />
          </div>
        </el-form-item>
        <el-form-item prop="score" label="最小匹配度">
          <div class="flex items-center gap-4 w-full pl-3">
            <el-slider
              v-model="retrievalConfigForm.score"
              :step="0.01"
              :min="0"
              :max="0.99"
            />
            <el-input-number
              v-model="retrievalConfigForm.score"
              class="w-[80px]"
              :min="0"
              :max="0.99"
              :step="0.01"
              :precision="2"
            />
          </div>
        </el-form-item>
        <!-- 底部按钮 -->
        <div class="flex items-center justify-between">
          <div class=""></div>
          <el-space :size="16">
            <el-button class="rounded-lg" @click="handleCancelRetrievalConfigModal">取消</el-button>
            <el-button
              :loading="updateDraftAppConfigLoading"
              type="primary"
              native-type="submit"
              class="rounded-lg"
            >
              保存
            </el-button>
          </el-space>
        </div>
      </el-form>
    </el-dialog>
  </div>
</template>

<style>
.el-dialog.datasets-modal {
  text-align: right;
}
</style>
