<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useVueFlow } from '@vue-flow/core'
import { cloneDeep } from 'lodash'
import { getReferencedVariables } from '@/utils/helper'
import type { FormInstance } from 'element-plus'
import { ElMessage } from 'element-plus'

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
const emits = defineEmits(['update:visible', 'updateNode'])
const { nodes, edges } = useVueFlow()
const form = ref<Record<string, any>>({})
const variableTypes = [
  { label: '引用', value: 'ref' },
  { label: 'STRING', value: 'string' },
  { label: 'INT', value: 'int' },
  { label: 'FLOAT', value: 'float' },
  { label: 'BOOLEAN', value: 'boolean' },
]

// 2.定义输出变量引用选项
const outputRefOptions = computed(() => {
  return getReferencedVariables(cloneDeep(nodes.value), cloneDeep(edges.value), props.node.id)
})

// 3.定义添加表单字段函数
const addFormField = () => {
  form.value?.outputs.push({ name: '', type: 'string', content: '', ref: '' })
  ElMessage.success('新增输入字段成功')
}

// 4.定义移除表单字段函数
const removeFormField = (idx: number) => {
  form.value?.outputs?.splice(idx, 1)
}

// 5.定义表单提交函数
const formRef = ref<FormInstance>()
const onSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  // 5.2 深度拷贝表单数据内容
  const cloneOutputs = cloneDeep(form.value.outputs)

  emits('updateNode', {
    id: props.node.id,
    title: form.value.title,
    description: form.value.description,
    outputs: cloneOutputs.map((output: any) => {
      return {
        name: output.name,
        description: '',
        required: true,
        type: output.type === 'ref' ? 'string' : output.type,
        value: {
          type: output.type === 'ref' ? 'ref' : 'literal',
          content:
            output.type === 'ref'
              ? {
                  ref_node_id: output.ref.split('/', 2)[0] || '',
                  ref_var_name: output.ref.split('/', 2)[1] || '',
                }
              : output.content,
        },
        meta: {},
      }
    }),
  })
}

// 6.监听数据，将数据映射到表单模型上
watch(
  () => props.node,
  (newNode) => {
    const cloneOutputs = cloneDeep(newNode.data.outputs)
    form.value = {
      id: newNode.id,
      type: newNode.type,
      title: newNode.data.title,
      description: newNode.data.description,
      outputs: cloneOutputs.map((output: any) => {
        // 6.1 计算引用的变量值信息
        const ref =
          output.value.type === 'ref'
            ? `${output.value.content.ref_node_id}/${output.value.content.ref_var_name}`
            : ''
        // 6.2 判断引用的变量值信息是否存在
        let refExists = false
        if (output.value.type === 'ref') {
          for (const outputRefOption of outputRefOptions.value) {
            for (const option of outputRefOption.options) {
              if (option.value === ref) {
                refExists = true
                break
              }
            }
          }
        }
        return {
          name: output.name, // 变量名
          type: output.value.type === 'literal' ? output.type : 'ref', // 数据类型(涵盖ref/string/int/float/boolean
          content: output.value.type === 'literal' ? output.value.content : '', // 变量值内容
          ref: output.value.type === 'ref' && refExists ? ref : '', // 变量引用信息，存储引用节点id+引用变量名
        }
      }),
    }
  },
  { immediate: true },
)
</script>

<template>
  <div
    v-if="props.visible"
    id="end-node-info"
    class="absolute top-0 right-0 bottom-0 w-[400px] border-l z-50 bg-white overflow-scroll scrollbar-y-sleek p-3"
  >
    <!-- 顶部标题信息 -->
    <div class="flex items-center justify-between gap-3 mb-2">
      <!-- 左侧标题 -->
      <div class="flex items-center gap-1 flex-1">
        <el-avatar :size="30" shape="square" class="bg-red-700 rounded-lg shrink-0">
          <icon-filter />
        </el-avatar>
        <el-input
          v-model="form.title"
          placeholder="请输入标题"
          class="bg-white! text-gray-700 font-semibold px-2"
        />
      </div>
      <!-- 右侧关闭按钮 -->
      <el-button
        type="text"
        size="mini"
        class="!text-gray700 shrink-0"
        @click="() => emits('update:visible', false)"
      >
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
    <!-- 表单信息 -->
    <el-form ref="formRef" size="mini" :model="form" label-position="top" @submit.prevent="onSubmit">
      <!-- 输出参数 -->
      <div class="flex flex-col gap-2">
        <!-- 标题&操作按钮 -->
        <div class="flex items-center justify-between">
          <!-- 左侧标题 -->
          <div class="flex items-center gap-2 text-gray-700 font-semibold">
            <div class="">输出参数</div>
            <el-tooltip content="组件运行完成后的最终输出。">
              <icon-question-circle />
            </el-tooltip>
          </div>
          <!-- 右侧新增字段按钮 -->
          <el-button type="text" size="mini" class="text-gray-700!" @click="() => addFormField()">
            <template #icon>
              <icon-plus />
            </template>
          </el-button>
        </div>
        <!-- 字段名 -->
        <div class="flex items-center gap-1 text-xs text-gray-500 mb-2">
          <div class="w-[20%]">参数名</div>
          <div class="w-[25%]">类型</div>
          <div class="w-[47%]">值</div>
          <div class="w-[8%]"></div>
        </div>
        <!-- 循环遍历字段列表 -->
        <div v-for="(output, idx) in form?.outputs" :key="idx" class="flex items-center gap-1">
          <div class="w-[20%] shrink-0">
            <el-input v-model="output.name" size="mini" placeholder="请输入参数名" class="px-2!" />
          </div>
          <div class="w-[25%] shrink-0">
            <el-select size="mini" v-model="output.type" class="px-2" :options="variableTypes" />
          </div>
          <div class="w-[47%] shrink-0 flex items-center gap-1">
            <el-input
              v-if="output.type !== 'ref'"
              size="mini"
              v-model="output.content"
              placeholder="请输入参数值"
            />
            <el-select
              v-else
              placeholder="请选择引用变量"
              size="mini"
              v-model="output.ref"
              :options="outputRefOptions"
            />
          </div>
          <div class="w-[8%] text-right">
            <icon-minus-circle
              class="text-gray-500 hover:text-gray-700 cursor-pointer shrink-0"
              @click="() => removeFormField(Number(idx))"
            />
          </div>
        </div>
        <!-- 空数据状态 -->
        <el-empty v-if="form?.outputs.length <= 0" class="my-4">该节点暂无输入数据</el-empty>
      </div>
      <el-divider class="my-4" />
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
    </el-form>
  </div>
</template>

<style>
#end-node-info :deep(.el-select-dropdown__item) {
  font-size: 12px !important;
}
</style>
