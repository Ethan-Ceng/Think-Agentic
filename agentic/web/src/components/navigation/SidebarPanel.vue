<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { Command, Plus, Search, X } from 'lucide-vue-next'
import SessionSections from '@/components/navigation/SessionSections.vue'

const props = defineProps<{
  expanded: boolean
}>()

const emit = defineEmits<{
  create: []
  close: []
}>()

const query = ref('')
const searchInput = ref<HTMLInputElement | null>(null)

function focusSearch() {
  void nextTick(() => searchInput.value?.focus())
}

watch(() => props.expanded, (expanded) => {
  if (!expanded) query.value = ''
})

defineExpose({ focusSearch })
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

      <label class="sidebar-search">
        <Search :size="16" aria-hidden="true" />
        <input
          ref="searchInput"
          v-model="query"
          type="search"
          placeholder="搜索任务"
          aria-label="搜索任务"
        >
        <button v-if="query" type="button" aria-label="清空搜索" @click="query = ''">
          <X :size="14" />
        </button>
      </label>

      <div class="sidebar-section-heading">
        <span>任务历史</span>
        <span class="sidebar-status-dot" title="会话流已连接" />
      </div>

      <SessionSections :query="query" />
    </div>
  </div>
</template>
