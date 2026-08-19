import { readonly, ref } from 'vue'
import type { SettingTab } from '@/lib/settings'

const open = ref(false)
const requestedTab = ref<SettingTab>('appearance')

export function useSettingsModal() {
  return {
    open: readonly(open),
    requestedTab: readonly(requestedTab),
    openSettings: (tab: SettingTab = 'appearance') => {
      if (!open.value) requestedTab.value = tab
      open.value = true
    },
    closeSettings: () => {
      open.value = false
    },
  }
}
