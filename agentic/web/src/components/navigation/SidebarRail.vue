<script setup lang="ts">
import { computed } from 'vue'
import { Bot, Files, History, PanelLeftClose, PanelLeftOpen, Plus, Search, Sparkles } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import SettingsButton from '@/components/SettingsButton.vue'
import UserMenu from '@/components/UserMenu.vue'
import type { SidebarSection } from '@/composables/useSidebar'

const props = defineProps<{
  expanded: boolean
  section: SidebarSection
}>()

const emit = defineEmits<{
  toggle: [section?: SidebarSection]
  search: []
}>()

const route = useRoute()
const router = useRouter()
const filesActive = computed(() => route.name === 'files')
const homeActive = computed(() => route.name === 'home')
const searchActive = computed(() => route.name === 'search')

function createTask() {
  void router.push('/')
}
</script>

<template>
  <nav class="sidebar-rail" aria-label="主要导航">
    <div class="rail-top">
      <RouterLink class="rail-brand" to="/" aria-label="MoocManus 首页">
        <Bot :size="20" stroke-width="2.2" />
      </RouterLink>

      <ElTooltip content="新建任务" placement="right" :show-after="400">
        <button
          class="rail-button rail-create"
          :class="{ active: homeActive }"
          type="button"
          aria-label="新建任务"
          :aria-current="homeActive ? 'page' : undefined"
          @click="createTask"
        >
          <Plus :size="20" />
        </button>
      </ElTooltip>

      <ElTooltip content="全局搜索" placement="right" :show-after="400">
        <button
          class="rail-button"
          :class="{ active: searchActive }"
          type="button"
          aria-label="全局搜索"
          :aria-current="searchActive ? 'page' : undefined"
          @click="emit('search')"
        >
          <Search :size="19" />
        </button>
      </ElTooltip>

      <ElTooltip content="任务历史" placement="right" :show-after="400">
        <button
          class="rail-button"
          :class="{ active: expanded && section === 'sessions' }"
          type="button"
          aria-label="任务历史"
          :aria-expanded="expanded"
          @click="emit('toggle', 'sessions')"
        >
          <History :size="19" />
        </button>
      </ElTooltip>

      <ElTooltip content="Skills" placement="right" :show-after="400">
        <button
          class="rail-button"
          :class="{ active: expanded && section === 'skills' }"
          type="button"
          aria-label="Skills"
          :aria-expanded="expanded && section === 'skills'"
          @click="emit('toggle', 'skills')"
        >
          <Sparkles :size="19" />
        </button>
      </ElTooltip>

      <ElTooltip content="文件" placement="right" :show-after="400">
        <RouterLink
          class="rail-button"
          :class="{ active: filesActive }"
          to="/files"
          aria-label="文件"
          :aria-current="filesActive ? 'page' : undefined"
        >
          <Files :size="19" />
        </RouterLink>
      </ElTooltip>
    </div>

    <div class="rail-bottom">
      <ElTooltip content="设置" placement="right" :show-after="400">
        <SettingsButton />
      </ElTooltip>
      <ElTooltip content="账号" placement="right" :show-after="400">
        <UserMenu compact />
      </ElTooltip>
      <ElTooltip :content="expanded ? '收起侧栏' : '展开侧栏'" placement="right" :show-after="400">
        <button
          class="rail-button"
          type="button"
          :aria-label="expanded ? '收起侧栏' : '展开侧栏'"
          :aria-expanded="expanded"
          @click="emit('toggle')"
        >
          <PanelLeftClose v-if="expanded" :size="19" />
          <PanelLeftOpen v-else :size="19" />
        </button>
      </ElTooltip>
    </div>
  </nav>
</template>
