<script setup lang="ts">
import CodeHighLight from '@/components/CodeHighLight.vue'
import {
  blockApiOutput,
  blockApiShell,
  streamApiOutput,
  streamApiShell,
} from '@/views/openapi/quick-start'
</script>

<template>
  <div
    class="scrollbar-y-sleek h-full min-h-0 overflow-y-auto rounded-xl border border-slate-200/60 bg-white p-6 shadow-sm shadow-slate-900/[0.03]"
  >
    <h2 class="mb-4 text-base font-semibold text-slate-800">概览</h2>
    <p class="mb-4 text-sm leading-relaxed text-slate-600">
      LLMOps API 是慕课 LLMOps 平台面向开发者提供的专业技术交互能力，致力于通过 API
      实现开发者更高效更全面的述求，不仅如此，扣子 API
      将提供更加灵活的和高精度的模型、工作流、知识库和扩展插件等能力的扩展，让定制化 Agent
      更加的精确、高效和智能。
    </p>
    <h2 class="mb-4 text-base font-semibold text-slate-800">准备工作</h2>
    <p class="mb-4 text-sm leading-relaxed text-slate-600">
      在开始之前，您需 需要创建个人访问令牌，其次需要在 LLMOps 上完成 Agent 的创建与发布。
    </p>
    <h2 class="mb-4 text-base font-semibold text-slate-800">基础使用</h2>
    <el-tabs class="openapi-quick-tabs">
      <el-tab-pane label="非流式Chat" name="block">
        <p class="mb-4 text-sm text-slate-600">请求CURL</p>
        <code-high-light language="shell">{{ blockApiShell }}</code-high-light>
        <p class="mb-4 mt-4 text-sm text-slate-600">返回结果示例</p>
        <code-high-light language="json">{{ blockApiOutput }}</code-high-light>
      </el-tab-pane>
      <el-tab-pane label="流式Chat" name="stream">
        <p class="mb-4 text-sm text-slate-600">请求CURL</p>
        <code-high-light language="shell">{{ streamApiShell }}</code-high-light>
        <p class="mb-4 mt-4 text-sm text-slate-600">返回结果示例</p>
        <code-high-light language="json">{{ streamApiOutput }}</code-high-light>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.openapi-quick-tabs :deep(.el-tabs__header) {
  margin-bottom: 1rem;
}
.openapi-quick-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background-color: rgb(226 232 240 / 0.9);
}
</style>
