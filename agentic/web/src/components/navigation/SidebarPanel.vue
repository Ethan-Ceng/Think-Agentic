<script setup lang="ts">
import { ref, watch } from 'vue'
import { Command, Plus, Search, X } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import SessionSections from '@/components/navigation/SessionSections.vue'

defineProps<{
  expanded: boolean
}>()

const emit = defineEmits<{
  create: []
  close: []
}>()

const route = useRoute()
const router = useRouter()
const query = ref('')

watch(
  () => route.query.q,
  (value) => {
    query.value = typeof value === 'string' ? value : ''
  },
  { immediate: true },
)

function submitSearch() {
  const value = query.value.trim()
  void router.push({ name: 'search', query: value ? { q: value } : {} })
  if (window.innerWidth <= 900) emit('close')
}

</script>

<template>
  <div class="sidebar-panel" :aria-hidden="!expanded" :inert="!expanded">
    <header class="sidebar-panel-header">
      <RouterLink class="sidebar-wordmark" to="/">
        <span>Mooc</span>Manus
      </RouterLink>
      <button class="panel-close-button" type="button" aria-label="关闭侧边栏" @click="emit('close')">
        <X :size="17" />
      </button>
    </header>

    <div class="sidebar-panel-body">
      <button class="sidebar-create-button" type="button" @click="emit('create')">
        <span><Plus :size="17" />新建任务</span>
        <kbd><Command :size="12" /> K</kbd>
      </button>

      <form class="sidebar-search" role="search" @submit.prevent="submitSearch">
        <Search :size="16" aria-hidden="true" />
        <input
          v-model="query"
          type="search"
          placeholder="搜索全部内容"
          aria-label="搜索全部内容"
        >
        <button v-if="query" type="button" aria-label="清空搜索" @click="query = ''">
          <X :size="14" />
        </button>
      </form>

      <div class="sidebar-section-heading">
        <span>任务历史</span>
        <span class="sidebar-status-dot" title="会话流已连接" />
      </div>

      <SessionSections />
    </div>
  </div>
</template>
