import { get, put } from '@/utils/request'
import type { GetSettingResponse, GetSettingsResponse, SettingUpsertRequest } from '@/models/setting'

export const getSettings = (category?: string) => {
  return get<GetSettingsResponse>('/settings', { params: category ? { category } : {} })
}

export const getSetting = (category: string, key: string) => {
  return get<GetSettingResponse>(`/settings/${category}/${key}`)
}

export const upsertSetting = (category: string, key: string, body: SettingUpsertRequest) => {
  return put<GetSettingResponse>(`/settings/${category}/${key}`, { body })
}
