import { get, post } from './fetch'
import type { AuthData, LoginParams, RegisterParams, UserInfo } from './types'

export const authApi = {
  register: (params: RegisterParams): Promise<AuthData> => {
    return post<AuthData>('/auth/register', params)
  },

  login: (params: LoginParams): Promise<AuthData> => {
    return post<AuthData>('/auth/password-login', params)
  },

  me: (): Promise<UserInfo> => {
    return get<UserInfo>('/auth/me')
  },

  logout: (): Promise<void> => {
    return post<void>('/auth/logout', {})
  },
}
