import { readonly, ref } from 'vue'

const open = ref(false)

export function useSettingsModal() {
  return {
    open: readonly(open),
    openSettings: () => {
      open.value = true
    },
    closeSettings: () => {
      open.value = false
    },
  }
}
