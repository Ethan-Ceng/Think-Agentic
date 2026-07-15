export type ThemePreference = 'system' | 'light' | 'dark'

const THEME_STORAGE_KEY = 'agentic.theme.preference'

export function getThemePreference(): ThemePreference {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  return stored === 'light' || stored === 'dark' ? stored : 'system'
}

export function applyThemePreference(preference: ThemePreference) {
  if (preference === 'system') {
    document.documentElement.removeAttribute('data-theme')
  } else {
    document.documentElement.dataset.theme = preference
  }
}

export function saveThemePreference(preference: ThemePreference) {
  if (preference === 'system') window.localStorage.removeItem(THEME_STORAGE_KEY)
  else window.localStorage.setItem(THEME_STORAGE_KEY, preference)
  applyThemePreference(preference)
}

export function initializeTheme() {
  applyThemePreference(getThemePreference())
}
