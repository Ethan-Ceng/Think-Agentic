import { get, put } from '@/utils/request'
import type { GetWechatConfigResponse, UpdateWechatConfigRequest } from '@/models/platform'
import type { BaseResponse } from '@/models/base'


// 获取指定 Agent 的微信公众号发布配置信息
export const getWechatConfig = (app_id: string) => {
  return get<GetWechatConfigResponse>(`/apps/${app_id}/platforms/wechat`)
}

// 更新指定 Agent 的微信公众号发布配置
export const updateWechatConfig = (app_id: string, req: UpdateWechatConfigRequest) => {
  return put<BaseResponse<any>>(`/apps/${app_id}/platforms/wechat`, { body: req })
}
