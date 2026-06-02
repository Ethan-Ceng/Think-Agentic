import type { BaseResponse } from '@/models/base'

export type AccountSetting = {
  id: string
  account_id: string
  category: string
  key: string
  value: Record<string, any>
  enabled: boolean
  created_at: number
  updated_at: number
}

export type GetSettingsResponse = BaseResponse<AccountSetting[]>
export type GetSettingResponse = BaseResponse<AccountSetting>

export type SettingUpsertRequest = {
  value: Record<string, any>
  enabled?: boolean
}
