import type { InjectionKey, Ref } from 'vue'
import { inject, provide } from 'vue'

export type SidebarContext = {
  open: Ref<boolean>
  toggle: () => void
  close: () => void
  openSidebar: () => void
}

const SidebarKey: InjectionKey<SidebarContext> = Symbol('SidebarContext')

export function provideSidebar(context: SidebarContext): void {
  provide(SidebarKey, context)
}

export function useSidebar(): SidebarContext {
  const context = inject(SidebarKey)
  if (!context) {
    throw new Error('useSidebar must be used after provideSidebar')
  }
  return context
}
