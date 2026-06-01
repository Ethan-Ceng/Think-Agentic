<script setup lang="ts">
import { ref, watch } from 'vue'
import type { FormInstance } from 'element-plus'
import { ElMessage } from 'element-plus'
import { cloneDeep } from 'lodash'

// 1.定义自定义组件所需数据
const props = defineProps({
  visible: { type: Boolean, required: true, default: false },
  node: {
    type: Object as any,
    required: true,
    default: () => {
      return {}
    },
  },
  loading: { type: Boolean, required: true, default: false },
})
const emits = defineEmits(['updateNode'])
const form = ref<Record<string, any>>({})

// 2.定义添加字段函数
const addFormInputField = () => {
  form.value?.inputs.push({ name: '', type: 'string', description: '', required: true })
  ElMessage.success('新增输入字段成功')
}

// 3.定义删除字段函数
const removeFormInputField = (idx: number) => {
  form.value?.inputs?.splice(idx, 1)
}

// 4.定义表单提交函数
const formRef = ref<FormInstance>()
const onSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  // 4.2 深度拷贝图草稿配置
  const cloneNode = cloneDeep(props.node)

  // 4.3 数据校验通过，通过事件触发数据更新
  emits('updateNode', {
    id: cloneNode.id,
    title: form.value.title,
    description: form.value.description,
    inputs: cloneDeep(form.value.inputs),
  })
}

// 5.监听数据，将数据映射到表单模型上
watch(
  () => props.node,
  (newNode) => {
    form.value = {
      id: newNode.id,
      type: newNode.type,
      title: newNode.data.title,
      description: newNode.data.description,
      inputs: [...cloneDeep(newNode.data.inputs)],
    }
  },
  { immediate: true },
)
</script>

<template>
  <div
    v-if="props.visible"
    id="start-node-info"
    class="absolute top-0 right-0 bottom-0 w-[400px] border-l z-50 bg-white overflow-scroll scrollbar-y-sleek p-3"
  >
    <!-- 顶部标题信息 -->
    <div class="flex items-center justify-between gap-3 mb-2">
      <!-- 左侧标题 -->
      <div class="flex items-center gap-1 flex-1">
        <el-avatar :size="30" shape="square" class="bg-blue-700 rounded-lg shrink-0">
          <icon-home />
        </el-avatar>
        <el-input
          v-model="form.title"
          placeholder="请输入标题"
          class="bg-white! text-gray-700 font-semibold px-2"
        />
      </div>
      <!-- 右侧关闭按钮 -->
      <el-button type="text" size="mini" class="!text-gray700 shrink-0">
        <template #icon>
          <icon-close />
        </template>
      </el-button>
    </div>
    <!-- 描述信息 -->
    <el-input
      :auto-size="{ minRows: 3, maxRows: 5 }"
      v-model="form.description"
      class="rounded-lg text-gray-700 text-xs!"
      placeholder="输入描述..."
    />
    <!-- 分隔符 -->
    <el-divider class="my-2" />
    <!-- 输入数据容器 -->
    <div class="">
      <!-- 容器header -->
      <div class="flex items-center justify-between mb-2">
        <!-- 左侧标题 -->
        <div class="flex items-center gap-2 text-gray-700 font-semibold">
          <div class="">输入参数</div>
          <el-tooltip
            content="定义组件运行时的输入参数，大模型调用该组件时，将根据此信息抽取输入参数"
          >
            <icon-question-circle />
          </el-tooltip>
        </div>
        <!-- 右侧新增字段按钮 -->
        <el-button type="text" size="mini" class="text-gray-700!" @click="() => addFormInputField()">
          <template #icon>
            <icon-plus />
          </template>
        </el-button>
      </div>
      <!-- 输入数据列表容器 -->
      <div class="flex flex-col gap-2">
        <!-- 输入数据表单 -->
        <el-form ref="formRef" :model="form" size="small" label-width="auto" @submit.prevent="onSubmit">
          <div class="flex flex-col gap-2">
            <!-- 有数据UI -->
            <div v-for="(input, idx) in form.inputs" :key="idx" class="bg-gray-50 rounded-lg p-3">
              <!-- 变量标题 -->
              <div class="flex items-center justify-between mb-2">
                <!-- 标题 -->
                <div class="flex items-center gap-2 flex-1">
                  <icon-paste :size="16" />
                  <div class="text-gray-700 font-semibold line-clamp-1 break-all">
                    {{ input.name }}
                  </div>
                </div>
                <!-- 删除按钮 -->
                <el-button
                  size="mini"
                  type="text"
                  class="text-gray-700! shrink-0"
                  @click="() => removeFormInputField(idx)"
                >
                  <template #icon>
                    <icon-close />
                  </template>
                </el-button>
              </div>
              <!-- 变量字段 -->
              <el-form-item
                :prop="`inputs.${idx}.name`"
                label="参数名称"
                required
              >
                <el-input v-model="input.name" size="small" placeholder="请输入变量名称" />
              </el-form-item>
              <el-form-item
                :prop="`inputs.${idx}.type`"
                label="变量类型"
                required
              >
                <el-select size="mini" v-model="input.type">
                  <el-option value="string">STRING</el-option>
                  <el-option value="int">INT</el-option>
                  <el-option value="float">FLOAT</el-option>
                  <el-option value="boolean">BOOLEAN</el-option>
                </el-select>
              </el-form-item>
              <el-form-item
                :prop="`inputs.${idx}.description`"
                label="参数描述"
                required
              >
                <el-input
                  :auto-size="{ minRows: 3, maxRows: 3 }"
                  v-model="input.description"
                  size="small"
                  placeholder="请准确描述该参数锁代表的含义，这将帮助大模型更好理解用户意图。"
                />
              </el-form-item>
              <el-form-item
                :prop="`inputs.${idx}.required`"
                label="是否必填"
                required
              >
                <el-switch size="small" v-model="input.required" />
              </el-form-item>
            </div>
            <!-- 没数据UI -->
            <el-empty v-if="form?.inputs.length <= 0" class="my-4">该节点暂无输入数据</el-empty>
            <!-- 保存按钮 -->
            <el-button
              :loading="props.loading"
              type="primary"
              size="small"
              native-type="submit"
              class="w-full rounded-lg"
            >
              保存
            </el-button>
          </div>
        </el-form>
      </div>
    </div>
  </div>
</template>
