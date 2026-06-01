<script setup lang="ts">
import {computed, onMounted, ref, watch} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import moment from 'moment'
import {useDeleteDocument, useGetDataset, useGetDocumentsWithPage, useUpdateDocumentEnabled,} from '@/hooks/use-dataset'
import UpdateDocumentNameModal from '@/views/space/datasets/documents/components/UpdateDocumentNameModal.vue'
import HitTestingModal from '@/views/space/datasets/documents/components/HitTestingModal.vue'

// 1.定义页面所需数据
const route = useRoute()
const router = useRouter()
const hitModalVisible = ref(false)
const updateDocumentNameModalVisible = ref(false)
const updateDocumentID = ref('')
const {dataset, loadDataset} = useGetDataset()
const {loading, documents, paginator, loadDocuments} = useGetDocumentsWithPage()
const {handleDelete} = useDeleteDocument()
const {handleUpdate: handleUpdateEnabled} = useUpdateDocumentEnabled()
const req = computed(() => {
  return {
    current_page: Number(route.query?.current_page ?? 1),
    page_size: Number(route.query?.page_size ?? 20),
    search_word: String(route.query?.search_word ?? ''),
  }
})

const searchWordInput = ref('')
watch(
  () => route.query.search_word,
  (sw) => {
    searchWordInput.value = String(sw ?? '')
  },
  { immediate: true },
)

// 2.监听路由query变化，当query发生变化时触发loadDocuments函数
watch(
  () => route.query,
  () => {
    loadDocuments(String(route.params?.dataset_id), req.value)
  },
)

onMounted(() => {
  loadDataset(String(route.params?.dataset_id))
  loadDocuments(String(route.params?.dataset_id), req.value)
})
</script>

<template>
  <div class="p-6">
    <!-- 顶部知识库详情 -->
    <div class="flex items-center w-full gap-2 mb-6">
      <!-- 左侧回退按钮 -->
      <router-link :to="{ name: 'space-datasets-list' }">
        <el-button size="mini" type="text" class="text-gray-700!">
          <template #icon>
            <icon-left/>
          </template>
        </el-button>
      </router-link>
      <!-- 右侧知识库信息 -->
      <div class="flex items-center gap-3">
        <!-- 知识库的图标 -->
        <el-avatar :size="40" shape="square" class="rounded-lg" :src="dataset.icon"/>
        <!-- 知识库信息 -->
        <div class="flex flex-col justify-between h-[40px]">
          <el-skeleton-item v-if="!dataset?.name" :widths="[100]"/>
          <div v-else class="text-gray-700">知识库 / {{ dataset.name }}</div>
          <div v-if="!dataset?.name" class="flex items-center gap-2">
            <el-skeleton-item :widths="[60]" :line-height="18"/>
            <el-skeleton-item :widths="[60]" :line-height="18"/>
            <el-skeleton-item :widths="[60]" :line-height="18"/>
          </div>
          <div v-else class="flex items-center gap-2">
            <el-tag size="small" class="rounded-sm h-[18px] leading-[18px] bg-gray-200 text-gray-500">
              {{ dataset?.document_count }} 文档
            </el-tag>
            <el-tag size="small" class="rounded-sm h-[18px] leading-[18px] bg-gray-200 text-gray-500">
              {{ dataset?.hit_count }} 命中
            </el-tag>
            <el-tag size="small" class="rounded-sm h-[18px] leading-[18px] bg-gray-200 text-gray-500">
              {{ dataset?.related_app_count }} 关联应用
            </el-tag>
          </div>
        </div>
      </div>
    </div>
    <!-- 中间检索以及召回测试 -->
    <div class="flex items-center justify-between mb-6">
      <!-- 左侧搜索框 -->
      <el-input
        v-model="searchWordInput"
        placeholder="请输入关键词搜索文档"
        clearable
        class="w-[240px] bg-white rounded-lg border-gray-200"
        @keyup.enter="
          router.push({
            path: route.path,
            query: {
              ...route.query,
              search_word: searchWordInput,
              current_page: 1,
            },
          })
        "
      />
      <!-- 右侧按钮 -->
      <el-space :size="12">
        <el-button class="rounded-lg" @click="hitModalVisible = true">召回测试</el-button>
        <router-link
            :to="{
            name: 'space-datasets-documents-create',
            params: { dataset_id: route.params?.dataset_id as string },
          }"
        >
          <el-button type="primary" class="rounded-lg">添加文件</el-button>
        </router-link>
      </el-space>
    </div>
    <!-- 底部表格 -->
    <div v-loading="loading">
      <el-table :data="documents" class="rounded-lg overflow-hidden">
        <el-table-column
          label="#"
          align="center"
          :width="80"
          header-cell-class-name="rounded-tl-lg bg-gray-200! text-gray-700"
          class-name="bg-transparent text-gray-700"
        >
          <template #default="{ $index }">
            {{ (paginator.current_page - 1) * paginator.page_size + $index + 1 }}
          </template>
        </el-table-column>
        <el-table-column
          prop="name"
          label="文档名"
          :width="400"
          header-cell-class-name="bg-gray-200! text-gray-700"
          class-name="bg-transparent text-gray-700"
        >
          <template #default="{ row }">
            <router-link
              :to="{
                name: 'space-datasets-documents-segments-list',
                params: {
                  dataset_id: route.params?.dataset_id as string,
                  document_id: row.id as string,
                },
              }"
              class="line-clamp-1 hover:text-gray-900"
            >
              {{ row.name }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column
          prop="character_count"
          label="字符数"
          header-cell-class-name="bg-gray-200! text-gray-700"
          class-name="bg-transparent text-gray-700"
        >
          <template #default="{ row }">
            {{ (row.character_count / 1000).toFixed(1) }}k
          </template>
        </el-table-column>
        <el-table-column
          prop="hit_count"
          label="召回次数"
          header-cell-class-name="bg-gray-200! text-gray-700"
          class-name="bg-transparent text-gray-700"
        />
        <el-table-column
          prop="created_at"
          label="上传时间"
          header-cell-class-name="bg-gray-200! text-gray-700"
          class-name="bg-transparent text-gray-700"
        >
          <template #default="{ row }">
            {{ moment(row.created_at * 1000).format('YYYY-MM-DD HH:mm:ss') }}
          </template>
        </el-table-column>
        <el-table-column
          prop="enabled"
          label="状态"
          header-cell-class-name="bg-gray-200! text-gray-700"
          class-name="bg-transparent text-gray-700"
        >
          <template #default="{ row }">
            <el-space>
              <div
                v-if="row.enabled"
                class="w-2 h-2 bg-green-500 rounded-xs border border-green-700"
              ></div>
              <div v-else class="w-2 h-2 bg-gray-500 rounded-xs border border-gray-700"></div>
              <div v-if="row.enabled" class="text-gray-700">可用</div>
              <div v-else class="text-gray-700">已禁用</div>
            </el-space>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          header-cell-class-name="rounded-tr-lg bg-gray-200! text-gray-700"
          class-name="bg-transparent text-gray-700 h-[40px]!"
          :width="100"
        >
          <template #default="{ row, $index }">
            <el-space :size="0">
              <template #split>
                <el-divider direction="vertical" />
              </template>
              <el-tooltip
                v-if="row.status === 'error'"
                placement="left"
                :content="`错误信息: ${row.error}`"
              >
                <el-switch size="small" :model-value="false" disabled />
              </el-tooltip>
              <el-switch
                v-else
                size="small"
                :model-value="row.enabled"
                @change="
                  (value: boolean) => {
                    handleUpdateEnabled(
                      route.params?.dataset_id as string,
                      row.id,
                      value as boolean,
                      () => {
                        documents[$index].enabled = value
                      },
                    )
                  }
                "
              />
              <el-dropdown placement="bottom-end">
                <el-button type="text" size="small" class="text-gray-700!">
                  <template #icon>
                    <icon-more />
                  </template>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      @click="
                        () => {
                          updateDocumentNameModalVisible = true
                          updateDocumentID = row.id
                        }
                      "
                    >
                      重命名
                    </el-dropdown-item>
                    <el-dropdown-item
                      class="text-red-700!"
                      @click="
                        () =>
                          handleDelete(String(route.params?.dataset_id), row.id, () => {
                            loadDocuments(String(route.params?.dataset_id), req)
                            loadDataset(String(route.params?.dataset_id))
                          })
                      "
                    >
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </el-space>
          </template>
        </el-table-column>
      </el-table>
      <div class="flex justify-end mt-4">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="paginator.total_record"
          :page-size="paginator.page_size"
          :current-page="paginator.current_page"
          @current-change="
            (page: number) => {
              router.push({
                path: route.path,
                query: {
                  ...route.query,
                  current_page: page,
                },
              })
            }
          "
        />
      </div>
    </div>
    <!-- 更新文档名字模态窗 -->
    <update-document-name-modal
        :document_id="updateDocumentID"
        :dataset_id="route.params?.dataset_id as string"
        v-model:visible="updateDocumentNameModalVisible"
        :on-after-update="() => loadDocuments(String(route.params?.dataset_id ?? ''), req)"
    />
    <!-- 召回测试模态窗 -->
    <hit-testing-modal
        v-model:visible="hitModalVisible"
        :dataset_id="route.params?.dataset_id as string"
    />
  </div>
</template>

<style scoped></style>
