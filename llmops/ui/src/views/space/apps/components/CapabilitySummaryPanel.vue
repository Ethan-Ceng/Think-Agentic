<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { WorkerCapabilitySummary } from '@/models/app'

const props = withDefaults(
  defineProps<{
    summary?: WorkerCapabilitySummary | null
    title?: string
    subtitle?: string
    loading?: boolean
    editable?: boolean
    compact?: boolean
  }>(),
  {
    summary: null,
    title: '能力摘要',
    subtitle: '',
    loading: false,
    editable: false,
    compact: false,
  },
)

const emit = defineEmits<{
  refresh: []
  saveOverrides: [overrides: Record<string, any>]
}>()

const editorVisible = ref(false)
const overrideText = ref('{}')
const overrideError = ref('')

const safeSummary = computed<WorkerCapabilitySummary>(() => props.summary || {})
const semanticTags = computed(() => safeSummary.value.semantic_tags || [])
const inputModalities = computed(() => safeSummary.value.input_modalities || [])
const outputModalities = computed(() => safeSummary.value.output_modalities || [])
const toolNames = computed(() => safeSummary.value.tool_names || [])
const modelFeatures = computed(() => safeSummary.value.model_features || [])
const skills = computed(() => safeSummary.value.skills || [])
const constraints = computed(() => safeSummary.value.constraints || {})

const hasSummary = computed(() => Boolean(safeSummary.value.schema_version))

const openEditor = () => {
  overrideError.value = ''
  overrideText.value = JSON.stringify(safeSummary.value.manual_overrides || {}, null, 2)
  editorVisible.value = true
}

const saveOverrides = () => {
  try {
    const parsed = JSON.parse(overrideText.value || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('JSON 必须是对象')
    }
    emit('saveOverrides', parsed)
    editorVisible.value = false
  } catch (error) {
    overrideError.value = error instanceof Error ? error.message : 'JSON 格式不正确'
    ElMessage.error(overrideError.value)
  }
}

const tagType = (tag: string) => {
  const map: Record<string, 'success' | 'warning' | 'info' | 'danger' | ''> = {
    search: 'success',
    weather: 'success',
    vision: 'warning',
    document_qa: 'info',
    api: 'warning',
    workflow: 'info',
  }
  return map[tag] || 'info'
}

watch(
  () => props.summary?.manual_overrides,
  () => {
    if (editorVisible.value) {
      overrideText.value = JSON.stringify(safeSummary.value.manual_overrides || {}, null, 2)
    }
  },
)
</script>

<template>
  <section v-loading="loading" class="border border-slate-200 bg-white">
    <div class="flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 px-3 py-2">
      <div class="min-w-0">
        <div class="text-sm font-semibold text-slate-900">{{ title }}</div>
        <div v-if="subtitle" class="mt-0.5 line-clamp-1 text-xs text-slate-500">{{ subtitle }}</div>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <el-tag v-if="safeSummary.executor_type" size="small" type="info">
          {{ safeSummary.executor_type }}
        </el-tag>
        <el-button size="small" @click="emit('refresh')">
          <template #icon>
            <icon-sync />
          </template>
          刷新
        </el-button>
        <el-button v-if="editable" size="small" @click="openEditor">
          <template #icon>
            <icon-edit />
          </template>
          修正
        </el-button>
      </div>
    </div>

    <div v-if="hasSummary" class="space-y-3 p-3">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div class="min-w-0">
          <div class="mb-1 text-xs font-medium text-slate-500">语义标签</div>
          <div class="flex min-h-7 flex-wrap gap-1.5">
            <el-tag v-for="tag in semanticTags" :key="tag" size="small" :type="tagType(tag)">
              {{ tag }}
            </el-tag>
            <span v-if="!semanticTags.length" class="text-xs text-slate-400">-</span>
          </div>
        </div>
        <div class="min-w-0">
          <div class="mb-1 text-xs font-medium text-slate-500">模型能力</div>
          <div class="flex min-h-7 flex-wrap gap-1.5">
            <el-tag v-for="feature in modelFeatures" :key="feature" size="small" type="info">
              {{ feature }}
            </el-tag>
            <span v-if="!modelFeatures.length" class="text-xs text-slate-400">-</span>
          </div>
        </div>
        <div class="min-w-0">
          <div class="mb-1 text-xs font-medium text-slate-500">输入模态</div>
          <div class="flex min-h-7 flex-wrap gap-1.5">
            <el-tag v-for="mode in inputModalities" :key="mode" size="small">
              {{ mode }}
            </el-tag>
            <span v-if="!inputModalities.length" class="text-xs text-slate-400">-</span>
          </div>
        </div>
        <div class="min-w-0">
          <div class="mb-1 text-xs font-medium text-slate-500">输出模态</div>
          <div class="flex min-h-7 flex-wrap gap-1.5">
            <el-tag v-for="mode in outputModalities" :key="mode" size="small">
              {{ mode }}
            </el-tag>
            <span v-if="!outputModalities.length" class="text-xs text-slate-400">-</span>
          </div>
        </div>
      </div>

      <div v-if="toolNames.length">
        <div class="mb-1 text-xs font-medium text-slate-500">工具</div>
        <div class="flex flex-wrap gap-1.5">
          <el-tag v-for="tool in toolNames" :key="tool" size="small" type="success">{{ tool }}</el-tag>
        </div>
      </div>

      <div v-if="!compact && skills.length">
        <div class="mb-1 text-xs font-medium text-slate-500">Skills</div>
        <el-table :data="skills" size="small" stripe>
          <el-table-column label="名称" min-width="150">
            <template #default="{ row }">
              <div class="truncate text-sm font-medium text-slate-900">{{ row.name || row.id }}</div>
              <div v-if="row.description" class="truncate text-xs text-slate-500">{{ row.description }}</div>
            </template>
          </el-table-column>
          <el-table-column label="标签" min-width="160">
            <template #default="{ row }">
              <div class="flex flex-wrap gap-1">
                <el-tag v-for="tag in row.tags || []" :key="tag" size="small" type="info">{{ tag }}</el-tag>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="!compact && Object.keys(constraints).length" class="grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
        <div v-for="(value, key) in constraints" :key="String(key)" class="bg-slate-50 px-2 py-1.5">
          <span class="text-slate-500">{{ key }}</span>
          <span class="ml-1 font-medium text-slate-800">{{ String(value) }}</span>
        </div>
      </div>
    </div>

    <div v-else class="p-4">
      <el-empty description="暂无能力摘要" />
    </div>

    <el-dialog v-model="editorVisible" title="人工修正" width="680px" destroy-on-close>
      <el-input
        v-model="overrideText"
        type="textarea"
        :rows="14"
        resize="vertical"
        spellcheck="false"
        class="font-mono"
      />
      <p v-if="overrideError" class="mt-2 text-xs text-red-600">{{ overrideError }}</p>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" @click="saveOverrides">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>
