<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  useDeleteApiKey,
  useGetApiKeysWithPage,
  useUpdateApiKeyIsActive,
} from '@/hooks/use-api-key'
import moment from 'moment'
import CreateOrUpdateApiKeyModal from './components/CreateOrUpdateApiKeyModal.vue'
import { ElMessage } from 'element-plus'

// 1.定义页面所需基础数据
const route = useRoute()
const router = useRouter()
const props = defineProps({
  create_api_key: { type: Boolean, default: false, required: true },
})
const emits = defineEmits(['update:create_api_key'])
const {
  loading: getApiKeysWithPageLoading,
  paginator,
  api_keys,
  loadApiKeys,
} = useGetApiKeysWithPage()
const { handleUpdateApiKeyIsActive } = useUpdateApiKeyIsActive()
const { handleDeleteApiKey } = useDeleteApiKey()
const createOrUpdateApiKeyModalVisible = ref(false)
const updateApiKeyId = ref('')
const updateApiKeyIsActive = ref(false)
const updateApiKeyRemark = ref('')
const req = computed(() => {
  return {
    current_page: Number(route.query?.current_page ?? 1),
    page_size: Number(route.query?.page_size ?? 20),
  }
})

// 2.定义写入剪切板函数
const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('复制成功')
  } catch (err) {
    ElMessage.error(String(err))
  }
}

// 2.页面加载完毕后获取api秘钥列表数据
onMounted(async () => {
  await loadApiKeys(true, req.value)
})

// 3.监听create_api_key是否开启，执行创建操作
watch(
  () => props.create_api_key,
  (value) => {
    // 3.1 清空updateApiKeyId
    updateApiKeyId.value = ''

    // 3.2 显示or隐藏模态窗
    createOrUpdateApiKeyModalVisible.value = Boolean(value)
  },
)

// 4.监听路由query变化，重新加载数据
watch(
  () => route.query,
  async (newQuery, oldQuery) => {
    if (newQuery.current_page != oldQuery.current_page) {
      await loadApiKeys(false, req.value)
    }
  },
)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200/60 bg-white shadow-sm shadow-slate-900/[0.03]">
    <div v-loading="getApiKeysWithPageLoading" class="flex min-h-0 flex-1 flex-col p-4">
      <el-table
        :data="api_keys"
        class="store-api-keys-table overflow-hidden rounded-lg border border-slate-200/50"
      >
        <el-table-column
          prop="api_key"
          label="秘钥"
          :width="400"
          header-cell-class-name="rounded-tl-lg !bg-slate-100 !text-slate-700"
          class-name="bg-transparent text-slate-700"
        >
          <template #default="{ row }">
            <div class="flex items-center">
              <div class="line-clamp-1">{{ row.api_key }}</div>
              <el-button
                size="small"
                class="shrink-0 rounded-sm"
                @click="async () => copyToClipboard(row.api_key)"
              >
                <template #icon>
                  <icon-copy />
                </template>
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          prop="is_active"
          label="状态"
          header-cell-class-name="!bg-slate-100 !text-slate-700"
          class-name="bg-transparent text-slate-700"
        >
          <template #default="{ row }">
            <el-space>
              <div
                v-if="row.is_active"
                class="h-2 w-2 rounded-xs border border-emerald-700 bg-emerald-500"
              ></div>
              <div v-else class="h-2 w-2 rounded-xs border border-slate-400 bg-slate-400"></div>
              <div v-if="row.is_active" class="text-slate-700">可用</div>
              <div v-else class="text-slate-700">已禁用</div>
            </el-space>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_at"
          label="创建时间"
          header-cell-class-name="!bg-slate-100 !text-slate-700"
          class-name="bg-transparent text-slate-700"
        >
          <template #default="{ row }">
            {{ moment(row.created_at * 1000).format('YYYY-MM-DD hh:mm:ss') }}
          </template>
        </el-table-column>
        <el-table-column
          prop="remark"
          label="备注"
          :width="400"
          header-cell-class-name="!bg-slate-100 !text-slate-700"
          class-name="bg-transparent text-slate-700"
        >
          <template #default="{ row }">
            <div class="line-clamp-1">{{ row.remark }}</div>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          header-cell-class-name="rounded-tr-lg !bg-slate-100 !text-slate-700"
          class-name="h-[40px]! bg-transparent text-slate-700"
          :width="100"
        >
          <template #default="{ row, $index }">
            <el-space :size="0">
              <template #split>
                <el-divider direction="vertical" />
              </template>
              <el-switch
                size="small"
                :model-value="row.is_active"
                @change="
                  (value: boolean) => {
                    handleUpdateApiKeyIsActive(row.id, value as boolean, () => {
                      api_keys[$index].is_active = Boolean(value)
                    })
                  }
                "
              />
              <el-dropdown placement="bottom-end">
                <el-button type="text" size="small" class="!text-slate-600">
                  <template #icon>
                    <icon-more />
                  </template>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      @click="
                        () => {
                          updateApiKeyId = row.id
                          updateApiKeyIsActive = row.is_active
                          updateApiKeyRemark = row.remark
                          createOrUpdateApiKeyModalVisible = true
                        }
                      "
                    >
                      重命名
                    </el-dropdown-item>
                    <el-dropdown-item
                      class="!text-red-700"
                      @click="
                        () =>
                          handleDeleteApiKey(row.id, async () => {
                            await loadApiKeys(false, req)
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
                query: { ...route.query, current_page: page },
              })
            }
          "
        />
      </div>
    </div>
    <!-- 新增or重命名模态窗 -->
    <create-or-update-api-key-modal
      v-model:visible="createOrUpdateApiKeyModalVisible"
      v-model:api_key_id="updateApiKeyId"
      v-model:is_active="updateApiKeyIsActive"
      v-model:remark="updateApiKeyRemark"
      @update:visible="(value) => emits('update:create_api_key', value)"
      :callback="async () => await loadApiKeys(false, req)"
    />
  </div>
</template>

<style scoped></style>
