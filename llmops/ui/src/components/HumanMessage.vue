<script setup lang="ts">
import { resolveApiAssetUrl } from '@/utils/api-asset-url'

// 1.定义自定义组件所需数据
const props = defineProps({
  account: {
    type: Object,
    default: () => {
      return {}
    },
    required: true,
  },
  query: { type: String, default: '', required: true },
  image_urls: { type: Array, default: () => [] },
})
</script>

<template>
  <div class="flex gap-2">
    <!-- 左侧头像 -->
    <el-avatar
      :size="30"
      shape="circle"
      class="shrink-0"
      :src="resolveApiAssetUrl(String(props.account?.avatar ?? ''))"
    />
    <!-- 右侧昵称与消息 -->
    <div class="flex flex-col items-start gap-2">
      <!-- 账号昵称 -->
      <div class="text-gray-700 font-bold">{{ props.account?.name }}</div>
      <!-- 人类消息 -->
      <div class="bg-blue-100 border border-blue-200 text-gray-700 px-4 py-3 rounded-2xl break-all">
        <el-image
          v-for="(image_url, idx) in props.image_urls"
          :key="idx"
          :src="resolveApiAssetUrl(String(image_url))"
        />
        {{ props.query }}
      </div>
    </div>
  </div>
</template>

<style scoped></style>
