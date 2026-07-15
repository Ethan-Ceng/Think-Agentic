export interface SettingsPanelHandle {
  isDirty: () => boolean
  save: () => Promise<boolean>
}

export type SettingsPanelEmits = {
  (event: 'dirty-change', dirty: boolean): void
}
