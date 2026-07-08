const TOKEN_KEY = 'agentic_access_token'

export function getAuthToken(): string {
  return window.localStorage.getItem(TOKEN_KEY) || ''
}

export function setAuthToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function clearAuthToken(): void {
  window.localStorage.removeItem(TOKEN_KEY)
}
