import type { InjectionKey, Ref } from 'vue'
import { inject, provide } from 'vue'

export type SidebarContext = {
  open: Ref<boolean>
  section: Ref<SidebarSection>
  mobile: Ref<boolean>
  toggle: (section?: SidebarSection) => void
  close: () => void
  openSidebar: (section?: SidebarSection) => void
}

export type SidebarSection = 'sessions' | 'skills'

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
