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

// 2.定义输入变量引用选项
const inputRefOptions = computed(() => {
  return getReferencedVariables(cloneDeep(nodes.value), cloneDeep(edges.value), props.node.id)
})

// 2.定义添加表单字段函数
const addFormInputField = (meta_type: string) => {
  if (meta_type === 'params') {
    form.value?.paramsInputs.push({ name: '', type: 'string', content: '', ref: '', meta_type })
  } else if (meta_type === 'headers') {
    form.value?.headersInputs.push({ name: '', type: 'string', content: '', ref: '', meta_type })
  } else if (meta_type === 'body') {
    form.value?.bodyInputs.push({ name: '', type: 'string', content: '', ref: '', meta_type })
  }
  ElMessage.success('新增输入字段成功')
}

// 3.定义移除表单字段函数
const removeFormInputField = (meta_type: string, idx: number) => {
  if (meta_type === 'params') {
    form.value?.paramsInputs.splice(idx, 1)
  } else if (meta_type === 'headers') {
    form.value?.headersInputs.splice(idx, 1)
  } else if (meta_type === 'body') {
    form.value?.bodyInputs.splice(idx, 1)
  }
}

// 4.定义表单提交函数
const formRef = ref<FormInstance>()
const onSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  // 4.2 深度拷贝表单数据内容
  const cloneInputs = [
    ...cloneDeep(form.value.headersInputs),
    ...cloneDeep(form.value.paramsInputs),
    ...cloneDeep(form.value.bodyInputs),
  ]

  // 4.3 数据校验通过，通过事件触发数据更新
  emits('updateNode', {
    id: props.node.id,
    title: form.value.title,
    description: form.value.description,
    method: form.value.method,
    url: form.value.url,
    inputs: cloneInputs.map((input) => {
      return {
        name: input.name,
        description: '',
        required: true,
        type: input.type === 'ref' ? 'string' : input.type,
        value: {
          type: input.type === 'ref' ? 'ref' : 'literal',
          content:
            input.type === 'ref'
              ? {
                  ref_node_id: input.ref.split('/')[0] || '',
                  ref_var_name: input.ref.split('/')[1] || '',
                }
              : input.content,
        },
        meta: {
          type: input.meta_type,
        },
      }
    }),
    outputs: cloneDeep(form.value.outputs),
  })
}

// 5.监听数据，将数据映射到表单模型上
watch(
  () => props.node,
  (newNode) => {
    const cloneInputs = cloneDeep(newNode.data.inputs).map((input: any) => {
      // 5.1 计算引用的变量值信息
      const ref =
        input.value.type === 'ref'
          ? `${input.value.content.ref_node_id}/${input.value.content.ref_var_name}`
          : ''
      // 5.2 判断引用的变量值信息是否存在
      let refExists = false
      if (input.value.type === 'ref') {
        for (const inputRefOption of inputRefOptions.value) {
          for (const option of inputRefOption.options) {
            if (option.value === ref) {
              refExists = true
              break
            }
          }
        }
      }
      return {
        name: input.name, // 变量名
        type: input.value.type === 'literal' ? input.type : 'ref', // 数据类型(涵盖ref/string/int/float/boolean
        content: input.value.type === 'literal' ? input.value.content : '', // 变量值内容
        ref: input.value.type === 'ref' && refExists ? ref : '', // 变量引用信息，存储引用节点id+引用变量名
        meta_type: input.meta.type,
      }
    })

    form.value = {
      id: newNode.id,
      type: newNode.type,
      title: newNode.data.title,
      description: newNode.data.description,
      method: newNode.data.method ?? 'get',
      url: newNode.data.url,
      paramsInputs: cloneInputs.filter((input: any) => input.meta_type === 'params'),
      headersInputs: cloneInputs.filter((input: any) => input.meta_type === 'headers'),
      bodyInputs: cloneInputs.filter((input: any) => input.meta_type === 'body'),
      outputs: [
        { name: 'status_code', type: 'int', value: { type: 'generated', content: 0 } },
        { name: 'text', type: 'string', value: { type: 'generated', content: '' } },
      ],
    }
  },
  { immediate: true },
)
</script>

<template>
  <div
    v-if="props.visible"
    id="llm-node-info"
    class="absolute top-0 right-0 bottom-0 w-[400px] border-l z-50 bg-white overflow-scroll scrollbar-y-sleek p-3"
  >
    <!-- 顶部标题信息 -->
    <div class="flex items-center justify-between gap-3 mb-2">
      <!-- 左侧标题 -->
      <div class="flex items-center gap-1 flex-1">
        <el-avatar :size="30" shape="square" class="bg-rose-500 rounded-lg shrink-0">
          <icon-link />
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
      <!-- 请求基础信息 -->
      <div class="flex flex-col gap-2">
        <!-- 标题&操作按钮 -->
        <div class="flex items-center justify-between">
          <!-- 标题 -->
          <div class="flex items-center gap-2 text-gray-700 font-semibold">
            <div class="">基本信息</div>
            <el-tooltip content="配置请求的基础方法与基础URL地址">
              <icon-question-circle />
            </el-tooltip>
          </div>
        </div>
        <!-- 字段信息 -->
        <div class="flex items-center gap-2">
          <div class="w-[25%] shrink-0">
            <el-select
              v-model="form.method"
              size="small"
              placeholder="请选择请求方法"
              class="px-2"
            >
              <el-option label="GET" value="get" />
              <el-option label="POST" value="post" />
              <el-option label="PUT" value="put" />
              <el-option label="PATCH" value="patch" />
              <el-option label="DELETE" value="delete" />
              <el-option label="HEAD" value="head" />
              <el-option label="OPTIONS" value="options" />
            </el-select>
          </div>
          <div class="w-[75%] shrink-0">
            <el-input v-model="form.url" size="mini" placeholder="请填写请求URL" />
          </div>
        </div>
      </div>
      <el-divider class="my-4" />
      <!-- HEADERS参数 -->
      <div class="flex flex-col gap-2">
        <!-- 标题&操作按钮 -->
        <div class="flex items-center justify-between">
          <!-- 左侧标题 -->
          <div class="flex items-center gap-2 text-gray-700 font-semibold">
            <div class="">HEADERS参数</div>
            <el-tooltip content="附加到URL中headers的参数信息">
              <icon-question-circle />
            </el-tooltip>
          </div>
          <!-- 右侧新增字段按钮 -->
          <el-button
            type="text"
            size="mini"
            class="text-gray-700!"
            @click="() => addFormInputField('headers')"
          >
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
        <div v-for="(input, idx) in form?.headersInputs" :key="idx" class="flex items-center gap-1">
          <div class="w-[20%] shrink-0">
            <el-input v-model="input.name" size="mini" placeholder="请输入参数名" class="px-2!" />
          </div>
          <div class="w-[25%] shrink-0">
            <el-select size="mini" v-model="input.type" class="px-2" :options="variableTypes" />
          </div>
          <div class="w-[47%] shrink-0 flex items-center gap-1">
            <el-input
              v-if="input.type !== 'ref'"
              size="mini"
              v-model="input.content"
              placeholder="请输入参数值"
            />
            <el-select
              v-else
              placeholder="请选择引用变量"
              size="mini"
              v-model="input.ref"
              :options="inputRefOptions"
            />
          </div>
          <div class="w-[8%] text-right">
            <icon-minus-circle
              class="text-gray-500 hover:text-gray-700 cursor-pointer shrink-0"
              @click="() => removeFormInputField('headers', Number(idx))"
            />
          </div>
        </div>
        <!-- 空数据状态 -->
        <el-empty v-if="form?.headersInputs.length <= 0" class="my-4">该节点暂无HEADERS参数</el-empty>
      </div>
      <el-divider class="my-4" />
      <!-- PARAMS参数 -->
      <div class="flex flex-col gap-2">
        <!-- 标题&操作按钮 -->
        <div class="flex items-center justify-between">
          <!-- 左侧标题 -->
          <div class="flex items-center gap-2 text-gray-700 font-semibold">
            <div class="">PARAMS参数</div>
            <el-tooltip content="附加到URL中query中的参数信息">
              <icon-question-circle />
            </el-tooltip>
          </div>
          <!-- 右侧新增字段按钮 -->
          <el-button
            type="text"
            size="mini"
            class="text-gray-700!"
            @click="() => addFormInputField('params')"
          >
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
        <div v-for="(input, idx) in form?.paramsInputs" :key="idx" class="flex items-center gap-1">
          <div class="w-[20%] shrink-0">
            <el-input v-model="input.name" size="mini" placeholder="请输入参数名" class="px-2!" />
          </div>
          <div class="w-[25%] shrink-0">
            <el-select size="mini" v-model="input.type" class="px-2" :options="variableTypes" />
          </div>
          <div class="w-[47%] shrink-0 flex items-center gap-1">
            <el-input
              v-if="input.type !== 'ref'"
              size="mini"
              v-model="input.content"
              placeholder="请输入参数值"
            />
            <el-select
              v-else
              placeholder="请选择引用变量"
              size="mini"
              v-model="input.ref"
              :options="inputRefOptions"
            />
          </div>
          <div class="w-[8%] text-right">
            <icon-minus-circle
              class="text-gray-500 hover:text-gray-700 cursor-pointer shrink-0"
              @click="() => removeFormInputField('params', Number(idx))"
            />
          </div>
        </div>
        <!-- 空数据状态 -->
        <el-empty v-if="form?.paramsInputs.length <= 0" class="my-4">该节点暂无PARAMS参数</el-empty>
      </div>
      <el-divider class="my-4" />
      <!-- BODY参数 -->
      <div class="flex flex-col gap-2">
        <!-- 标题&操作按钮 -->
        <div class="flex items-center justify-between">
          <!-- 左侧标题 -->
          <div class="flex items-center gap-2 text-gray-700 font-semibold">
            <div class="">BODY参数</div>
            <el-tooltip content="附加到URL中body的参数信息">
              <icon-question-circle />
            </el-tooltip>
          </div>
          <!-- 右侧新增字段按钮 -->
          <el-button
            type="text"
            size="mini"
            class="text-gray-700!"
            @click="() => addFormInputField('body')"
          >
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
        <div v-for="(input, idx) in form?.bodyInputs" :key="idx" class="flex items-center gap-1">
          <div class="w-[20%] shrink-0">
            <el-input v-model="input.name" size="mini" placeholder="请输入参数名" class="px-2!" />
          </div>
          <div class="w-[25%] shrink-0">
            <el-select size="mini" v-model="input.type" class="px-2" :options="variableTypes" />
          </div>
          <div class="w-[47%] shrink-0 flex items-center gap-1">
            <el-input
              v-if="input.type !== 'ref'"
              size="mini"
              v-model="input.content"
              placeholder="请输入参数值"
            />
            <el-select
              v-else
              placeholder="请选择引用变量"
              size="mini"
              v-model="input.ref"
              :options="inputRefOptions"
            />
          </div>
          <div class="w-[8%] text-right">
            <icon-minus-circle
              class="text-gray-500 hover:text-gray-700 cursor-pointer shrink-0"
              @click="() => removeFormInputField('body', Number(idx))"
            />
          </div>
        </div>
        <!-- 空数据状态 -->
        <el-empty v-if="form?.bodyInputs.length <= 0" class="my-4">该节点暂无BODY参数</el-empty>
      </div>
      <el-divider class="my-4" />
      <!-- 输出参数 -->
      <div class="flex flex-col gap-2">
        <!-- 输出标题 -->
        <div class="font-semibold text-gray-700">输出数据</div>
        <!-- 字段标题 -->
        <div class="text-gray-500 text-xs">参数名</div>
        <!-- 输出参数列表 -->
        <div v-for="(output, idx) in form?.outputs" :key="idx" class="flex flex-col gap-2">
          <div class="flex items-center gap-2">
            <div class="text-gray-700">{{ output.name }}</div>
            <div class="text-gray-500 bg-gray-200 px-1 py-0.5 rounded-sm">{{ output.type }}</div>
          </div>
        </div>
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

<style scoped></style>
