<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Component } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  ArrowLeft,
  Bot,
  Database,
  Languages,
  LayoutGrid,
  Palette,
  Settings,
  ShieldAlert,
  Wrench,
} from 'lucide-vue-next'
import StorageSettings from '@/components/StorageSettings.vue'
import SettingsA2aPanel from '@/components/settings/SettingsA2aPanel.vue'
import SettingsAppearancePanel from '@/components/settings/SettingsAppearancePanel.vue'
import SettingsApiToolsPanel from '@/components/settings/SettingsApiToolsPanel.vue'
import SettingsGeneralPanel from '@/components/settings/SettingsGeneralPanel.vue'
import SettingsMcpPanel from '@/components/settings/SettingsMcpPanel.vue'
import SettingsModelPanel from '@/components/settings/SettingsModelPanel.vue'
import type { SettingsPanelHandle } from '@/components/settings/types'
import { useSettingsModal } from '@/composables/useSettingsModal'

type SettingTab = 'appearance' | 'common' | 'llm' | 'storage' | 'tools' | 'a2a' | 'mcp'
type SettingNavItem = { key: SettingTab; icon: Component; title: string; description: string }
type SettingNavGroup = { label: string; description: string; tabs: SettingNavItem[] }

const settingsModal = useSettingsModal()
const activeTab = ref<SettingTab>('appearance')
const activePanel = ref<SettingsPanelHandle | null>(null)
const mobilePanelOpen = ref(false)
const saving = ref(false)
const activeDirty = ref(false)

const groups: SettingNavGroup[] = [
  {
    label: '个人',
    description: '仅影响当前用户与浏览器',
    tabs: [
      { key: 'appearance' as const, icon: Palette, title: '外观', description: '浅色、深色与系统主题' },
    ],
  },
  {
    label: '模型与运行时',
    description: '任务行为与默认模型',
    tabs: [
      { key: 'common' as const, icon: Settings, title: '运行设置', description: '迭代、重试与能力预检' },
      { key: 'llm' as const, icon: Languages, title: '模型提供商', description: 'API 地址、密钥与生成参数' },
    ],
  },
  {
    label: '系统与运行时',
    description: '存储、工具与外部连接',
    tabs: [
      { key: 'storage' as const, icon: Database, title: '文件存储', description: '本地、COS 与 OSS' },
      { key: 'tools' as const, icon: ShieldAlert, title: 'API Tools', description: 'Provider、Operation 与风险' },
      { key: 'a2a' as const, icon: LayoutGrid, title: 'A2A Agent', description: '远程 Agent 连接' },
      { key: 'mcp' as const, icon: Wrench, title: 'MCP 服务器', description: '外部工具服务器' },
    ],
  },
]

const currentTab = computed(() => groups.flatMap((group) => group.tabs).find((tab) => tab.key === activeTab.value)!)
const showSave = computed(() => ['appearance', 'common', 'llm', 'storage', 'tools'].includes(activeTab.value))

async function confirmDiscard() {
  if (!activeDirty.value) return true
  try {
    await ElMessageBox.confirm(
      `「${currentTab.value.title}」还有尚未保存的修改，离开后这些修改会丢失。`,
      '放弃未保存的修改？',
      { confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning' },
    )
    activeDirty.value = false
    return true
  } catch {
    return false
  }
}

async function selectTab(tab: SettingTab) {
  if (tab === activeTab.value) {
    mobilePanelOpen.value = true
    return
  }
  if (!(await confirmDiscard())) return
  activeTab.value = tab
  activeDirty.value = false
  mobilePanelOpen.value = true
}

async function backToCategories() {
  if (!(await confirmDiscard())) return
  mobilePanelOpen.value = false
}

async function requestClose() {
  if (saving.value || !(await confirmDiscard())) return
  settingsModal.closeSettings()
}

function handleDialogUpdate(open: boolean) {
  if (!open) void requestClose()
}

async function handleSave() {
  if (!activePanel.value || saving.value) return
  saving.value = true
  try {
    if (await activePanel.value.save()) activeDirty.value = false
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ElDialog
    :model-value="settingsModal.open.value"
    width="min(1040px, calc(100vw - 24px))"
    append-to-body
    align-center
    class="settings-dialog settings-center-dialog"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @update:model-value="handleDialogUpdate"
  >
    <template #header>
      <div class="settings-dialog-header">
        <div class="settings-brand-mark"><Bot :size="20" /></div>
        <div><h2>MoocManus 设置</h2><p>管理个人偏好、运行时能力与外部连接。</p></div>
      </div>
    </template>

    <div class="settings-layout" :class="{ 'mobile-panel-open': mobilePanelOpen }">
      <nav class="settings-nav" aria-label="设置分类">
        <div v-for="group in groups" :key="group.label" class="settings-nav-group">
          <div class="settings-nav-group-heading"><strong>{{ group.label }}</strong><span>{{ group.description }}</span></div>
          <button
            v-for="tab in group.tabs"
            :key="tab.key"
            class="settings-nav-button"
            :class="{ active: activeTab === tab.key }"
            type="button"
            :aria-current="activeTab === tab.key ? 'page' : undefined"
            @click="selectTab(tab.key)"
          >
            <component :is="tab.icon" :size="18" />
            <span class="settings-tab-copy"><strong>{{ tab.title }}</strong><small>{{ tab.description }}</small></span>
          </button>
        </div>
      </nav>

      <main class="settings-main">
        <button class="settings-mobile-back" type="button" @click="backToCategories"><ArrowLeft :size="17" />设置分类</button>
        <SettingsAppearancePanel v-if="activeTab === 'appearance'" ref="activePanel" @dirty-change="activeDirty = $event" />
        <SettingsGeneralPanel v-else-if="activeTab === 'common'" ref="activePanel" @dirty-change="activeDirty = $event" />
        <SettingsModelPanel v-else-if="activeTab === 'llm'" ref="activePanel" @dirty-change="activeDirty = $event" />
        <StorageSettings v-else-if="activeTab === 'storage'" ref="activePanel" @dirty-change="activeDirty = $event" />
        <SettingsApiToolsPanel v-else-if="activeTab === 'tools'" ref="activePanel" @dirty-change="activeDirty = $event" />
        <SettingsA2aPanel v-else-if="activeTab === 'a2a'" ref="activePanel" />
        <SettingsMcpPanel v-else ref="activePanel" />
      </main>
    </div>

    <template #footer>
      <div class="settings-footer-status" aria-live="polite">
        <span v-if="activeDirty" class="settings-unsaved-dot"></span>
        {{ activeDirty ? '有未保存的修改' : '所有修改均已保存' }}
      </div>
      <div class="settings-footer-actions">
        <ElButton :disabled="saving" @click="requestClose">关闭</ElButton>
        <ElButton v-if="showSave" type="primary" :loading="saving" :disabled="!activeDirty" @click="handleSave">保存修改</ElButton>
      </div>
    </template>
  </ElDialog>
</template>
