import { readonly, ref } from 'vue'
import type { FailureInfo } from '@/lib/api/types'
import type { SettingTab } from '@/lib/settings'

const open = ref(false)
const requestedTab = ref<SettingTab>('appearance')
const failureContext = ref<{
  tab: SettingTab
  failure: FailureInfo
} | null>(null)

export function useSettingsModal() {
  return {
    open: readonly(open),
    requestedTab: readonly(requestedTab),
    failureContext: readonly(failureContext),
    openSettings: (
      tab: SettingTab = 'appearance',
      failure: FailureInfo | null = null,
    ) => {
      if (!open.value) requestedTab.value = tab
      failureContext.value = failure ? { tab, failure } : null
      open.value = true
    },
    closeSettings: () => {
      open.value = false
      failureContext.value = null
    },
  }
}
