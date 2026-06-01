<script setup lang="ts">
import moment from 'moment'
import {ref, watch} from 'vue'
import { ElMessage } from 'element-plus'
import {useGetDatasetQueries, useHit} from '@/hooks/use-dataset'
import type {HitRequest} from '@/models/dataset'

// 1.定义组件接收数据以及事件
const props = defineProps({
  visible: {type: Boolean, required: true},
  dataset_id: {type: String, required: true},
})
const emits = defineEmits(['update:visible'])
const retrievalSettingModalVisible = ref(false)
const defaultRetrievalSetting = {retrieval_strategy: 'semantic', k: 5, score: 0.5}
const retrievalSettingForm = ref<Record<string, any>>(defaultRetrievalSetting)
const hitTestingSegments = ref<any[]>([])
const hitTestingForm = ref<Record<string, any>>({query: '', ...defaultRetrievalSetting})
const {loading: getDatasetQueriesLoading, queries, loadDatasetQueries} = useGetDatasetQueries()
const {loading: hitLoading, hits, handleHit} = useHit()

// 2.定义知识库检索设置相关
const hideRetrievalSettingModal = () => {
  // 2.1 复原检索策略
  retrievalSettingForm.value = hitTestingForm.value

  // 2.2 隐藏模态窗
  retrievalSettingModalVisible.value = false
}

// 3.定义保存检索设置处理器
const saveRetrievalSetting = () => {
  // 3.1 重置检索查询片段列表
  hitTestingSegments.value = []

  // 3.2 更新检索策略
  hitTestingForm.value = {query: hitTestingForm.value.query, ...retrievalSettingForm.value}

  // 3.3 隐藏模态窗
  retrievalSettingModalVisible.value = false
}

// 4.定义隐藏召回测试模态窗
const hideHitTestingModal = () => emits('update:visible', false)

const handleRecentQueryRowClick = (row: { query: string }) => {
  hitTestingForm.value.query = row.query
}

// 5.定义召回测试处理器
const handleHitTesting = async () => {
  // 5.1 判断检索的源文本是否为空
  if (hitTestingForm.value.query.trim() === '') {
    ElMessage.error('检索源文本不能为空')
    return
  }

  // 5.2 调用处理器执行召回测试
  await handleHit(props.dataset_id, hitTestingForm.value as HitRequest)
  hitTestingSegments.value = hits.value

  // 5.3 重新更新知识库最近查询
  await loadDatasetQueries(props.dataset_id)
}

// 6.监听数据变化
watch(
    () => props.visible,
    async (newValue) => {
      if (newValue) {
        // 6.1 模态窗开启，加载最近查询
        await loadDatasetQueries(props.dataset_id)
      } else {
        // 6.2 模态窗关闭，清空最近查询、召回记录、初始化检索配置
        queries.value = []
        hitTestingSegments.value = []
        hitTestingForm.value = {query: '', ...defaultRetrievalSetting}
        retrievalSettingForm.value = defaultRetrievalSetting
      }
    },
)
</script>

<template>
  <div class="">
    <!-- 召回测试模态窗 -->
    <el-dialog
        :width="1000"
        :model-value="props.visible"
        class="rounded-xl h-3/4 overflow-auto scrollbar-y-sleek"
        @update:model-value="(v: boolean) => emits('update:visible', v)"
    >
      <!-- 顶部标题 -->
      <div class="flex items-center justify-between">
        <div class="text-lg font-bold text-gray-700">召回测试</div>
        <el-button type="text" class="text-gray-700!" size="small" @click="hideHitTestingModal">
          <template #icon>
            <icon-close/>
          </template>
        </el-button>
      </div>
      <!-- 副标题 -->
      <div class="text-gray-500">基于给定的查询文本测试知识库的召回效果</div>
      <!-- 中间内容区 -->
      <div class="pt-6">
        <div class="w-full flex justify-between gap-2">
          <!-- 左侧输入框以及最近查询 -->
          <div class="flex flex-col w-1/2">
            <!-- 顶部输入框 -->
            <div class="border border-blue-700 bg-blue-100 rounded-lg flex flex-col mb-6">
              <!-- 输入框标题 -->
              <div class="flex items-center justify-between px-4 py-1.5">
                <div class="font-bold text-gray-900">源文本</div>
                <el-button
                    size="small"
                    class="rounded-lg px-2"
                    @click="retrievalSettingModalVisible = true"
                >
                  <template #icon>
                    <icon-language/>
                  </template>
                  <div v-if="hitTestingForm.retrieval_strategy === 'semantic'" class="">
                    相似性检索
                  </div>
                  <div v-else-if="hitTestingForm.retrieval_strategy === 'full_text'" class="">
                    全文检索
                  </div>
                  <div v-else class="">混合检索</div>
                </el-button>
              </div>
              <!-- 输入框容器 -->
              <div class="bg-white rounded-lg p-2">
                <!-- 输入框 -->
                <el-input
                    v-model="hitTestingForm.query"
                    placeholder="请输入文本，建议使用简短的陈述句"
                    :max-length="200"
                    :auto-size="{ minRows: 6, maxRows: 6 }"
                    class="bg-white! border-0! mb-1"
                />
                <!-- 字符限制以及召回按钮 -->
                <div class="flex items-center justify-between">
                  <el-tag size="small" class="rounded-sm text-gray-700">
                    {{ hitTestingForm.query.length }}/200
                  </el-tag>
                  <el-button
                      :loading="hitLoading"
                      type="primary"
                      size="small"
                      class="rounded-lg"
                      @click="handleHitTesting"
                  >
                    召回测试
                  </el-button>
                </div>
              </div>
            </div>
            <!-- 底部最近查询 -->
            <div class="">
              <div class="text-gray-700 font-bold mb-4">最近查询</div>
              <el-table
                  v-loading="getDatasetQueriesLoading"
                  size="small"
                  :data="queries"
                  class="recent-queries-table"
                  @row-click="handleRecentQueryRowClick"
              >
                <el-table-column
                  prop="source"
                  label="数据源"
                  width="110"
                  header-cell-class-name="text-gray-500 bg-transparent border-b font-bold"
                  class-name="text-gray-500"
                />
                <el-table-column
                  prop="query"
                  label="文本"
                  header-cell-class-name="text-gray-500 bg-transparent border-b font-bold"
                  class-name="text-gray-500"
                >
                  <template #default="{ row }">
                    <div class="line-clamp-1">{{ row.query }}</div>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="created_at"
                  label="时间"
                  width="160"
                  header-cell-class-name="text-gray-500 bg-transparent border-b font-bold"
                  class-name="text-gray-500"
                >
                  <template #default="{ row }">
                    {{ moment(row.created_at * 1000).format('YYYY-MM-DD HH:mm') }}
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
          <el-divider direction="vertical"/>
          <!-- 右侧召回列表 -->
          <div class="w-1/2">
            <div v-loading="hitLoading" class="w-full">
              <!-- 有数据的状态 -->
              <el-row v-if="hitTestingSegments.length > 0" :gutter="16">
                <el-col
                  v-for="segment in hitTestingSegments"
                  :key="segment.id"
                  :span="12"
                  class="mb-4"
                >
                  <div class="p-4 bg-gray-50 rounded-lg cursor-pointer">
                    <!-- 顶部得分部分 -->
                    <div
                        v-if="hitTestingForm.retrieval_strategy === 'semantic'"
                        class="flex items-center gap-2 mb-1.5"
                    >
                      <icon-pushpin/>
                      <el-progress
                        :stroke-width="6"
                        :show-text="false"
                        :percentage="segment.score <= 1 ? segment.score * 100 : segment.score"
                      />
                      <div class="text-gray-700 text-xs">{{ segment.score.toFixed(2) }}</div>
                    </div>
                    <!-- 中间内容部分 -->
                    <div class="text-gray-500 line-clamp-4 h-[88px] break-all">
                      {{ segment.content }}
                    </div>
                    <!-- 文档归属信息 -->
                    <el-divider class="my-2"/>
                    <div class="flex items-center gap-2 text-gray-500 text-xs">
                      <icon-file class="shrink-0"/>
                      <div class="line-clamp-1">{{ segment.document.name }}</div>
                    </div>
                  </div>
                </el-col>
              </el-row>
              <!-- 无数据的状态 -->
              <el-empty v-else/>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
    <!-- 检索设置模态窗 -->
    <el-dialog
        v-model="retrievalSettingModalVisible"
        header-class="hidden"
        :show-close="false"
        modal-class="rounded-xl"
    >
      <!-- 顶部标题 -->
      <div class="flex items-center justify-between">
        <div class="text-lg font-bold text-gray-700">检索设置</div>
        <el-button
            type="text"
            class="text-gray-700!"
            size="small"
            @click="hideRetrievalSettingModal"
        >
          <template #icon>
            <icon-close/>
          </template>
        </el-button>
      </div>
      <!-- 中间表单内容 -->
      <el-form :model="retrievalSettingForm" @submit.prevent="saveRetrievalSetting" class="pt-6">
        <el-form-item prop="retrieval_strategy" label="检索策略">
          <el-radio-group v-model="retrievalSettingForm.retrieval_strategy">
            <el-radio label="hybrid">混合策略</el-radio>
            <el-radio label="full_text">全文检索</el-radio>
            <el-radio label="semantic">相似性检索</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item prop="k" label="最大召回数量">
          <div class="flex items-center gap-4 w-full pl-3">
            <el-slider v-model="retrievalSettingForm.k" :step="1" :min="1" :max="10"/>
            <el-input-number
                v-model="retrievalSettingForm.k"
                class="w-[80px]"
            />
          </div>
        </el-form-item>
        <el-form-item prop="score" label="最小匹配度">
          <div class="flex items-center gap-4 w-full pl-3">
            <el-slider
                v-model="retrievalSettingForm.score"
                :step="0.01"
                :min="0"
                :max="0.99"
            />
            <el-input-number
                v-model="retrievalSettingForm.score"
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
            <el-button class="rounded-lg" @click="hideRetrievalSettingModal">取消</el-button>
            <el-button type="primary" native-type="submit" class="rounded-lg">保存</el-button>
          </el-space>
        </div>
      </el-form>
    </el-dialog>
  </div>
</template>

<style scoped></style>
