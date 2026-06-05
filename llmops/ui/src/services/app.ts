import { del, get, patch, post, put, ssePost } from '@/utils/request'
import type {
  BindPlannerWorkerRequest,
  CapabilitySummaryResponse,
  CreateAppRequest,
  GetAppResponse,
  GetAppsWithPageRequest,
  GetAppsWithPageResponse,
  GetDebugConversationMessagesWithPageRequest,
  GetDebugConversationMessagesWithPageResponse,
  GetDraftAppConfigResponse,
  GetPlannerWorkersResponse,
  GetPublishedConfigResponse,
  GetPublishHistoriesWithPageResponse,
  PatchCapabilitySummaryRequest,
  PlannerDryRunRequest,
  PlannerDryRunResponse,
  PlannerPreflightRequest,
  PlannerPreflightResponse,
  RegenerateWebAppTokenResponse,
  RefreshCapabilitySummaryRequest,
  RoutingPolicyRequest,
  RoutingPolicyResponse,
  RoutingPolicyValidateResponse,
  UpdateAppRequest,
  UpdateDraftAppConfigRequest,
  UpdatePlannerWorkerBindingRequest,
} from '@/models/app'
import type { BasePaginatorRequest, BaseResponse } from '@/models/base' // 获取应用基础信息

// 获取应用基础信息
export const getApp = (app_id: string) => {
  return get<GetAppResponse>(`/apps/${app_id}`)
}

// 在个人空间下新增应用
export const createApp = (req: CreateAppRequest) => {
  return post<BaseResponse<{ id: string }>>(`/apps`, { body: req })
}

// 修改指定应用
export const updateApp = (app_id: string, req: UpdateAppRequest) => {
  return put<BaseResponse<any>>(`/apps/${app_id}`, { body: req })
}

// 删除指定应用
export const deleteApp = (app_id: string) => {
  return del<BaseResponse<any>>(`/apps/${app_id}`)
}

// 拷贝指定的应用
export const copyApp = (app_id: string) => {
  return post<BaseResponse<{ id: string }>>(`/apps/${app_id}/copy`)
}

// 获取应用分页列表数据（后端查询参数为 page，与 BasePaginatorRequest 的 current_page 对应）
export const getAppsWithPage = (req: GetAppsWithPageRequest) => {
  return get<GetAppsWithPageResponse>(`/apps`, {
    params: {
      page: req.current_page,
      page_size: req.page_size,
      search_word: req.search_word,
      agent_type: req.agent_type || '',
    },
  })
}

// 获取特定应用的草稿配置信息
export const getDraftAppConfig = (app_id: string) => {
  return get<GetDraftAppConfigResponse>(`/apps/${app_id}/draft-app-config`)
}

// 更新特定应用的草稿配置信息
export const updateDraftAppConfig = (app_id: string, req: UpdateDraftAppConfigRequest) => {
  return post<BaseResponse<any>>(`/apps/${app_id}/draft-app-config`, { body: req })
}

// 获取应用的调试长记忆
export const getDebugConversationSummary = (app_id: string) => {
  return get<BaseResponse<{ summary: string }>>(`/apps/${app_id}/debug-conversation-summary`)
}

// 更新应用的调试长记忆
export const updateDebugConversationSummary = (app_id: string, summary: string) => {
  return put<BaseResponse<any>>(`/apps/${app_id}/debug-conversation-summary`, { body: { summary } })
}

// 应用调试对话，该接口为流式事件输出
export const debugChat = (
  app_id: string,
  query: string,
  image_urls: string[],
  onData: (event_response: Record<string, any>) => void,
) => {
  return ssePost(`/apps/${app_id}/debug-chat`, { body: { query, image_urls } }, onData)
}

// 停止某次应用的调试会话
export const stopDebugChat = (app_id: string, task_id: string) => {
  return post<BaseResponse<any>>(`/apps/${app_id}/stop-debug-chat/${task_id}`)
}

// 获取应用的调试会话消息列表
export const getDebugConversationMessagesWithPage = (
  app_id: string,
  req?: GetDebugConversationMessagesWithPageRequest,
) => {
  return get<GetDebugConversationMessagesWithPageResponse>(
    `/apps/${app_id}/debug-conversation-messages`,
    { params: req },
  )
}

// 清空应用的调试会话记录
export const deleteDebugConversation = (app_id: string) => {
  return del<BaseResponse<any>>(`/apps/${app_id}/debug-conversation`)
}

// 更新/发布应用的配置信息
export const publish = (app_id: string) => {
  return post<BaseResponse<any>>(`/apps/${app_id}/publish`)
}

// 取消指定应用的发布
export const cancelPublish = (app_id: string) => {
  return post<BaseResponse<any>>(`/apps/${app_id}/cancel-publish`)
}

// 获取应用的发布历史列表信息
export const getPublishHistoriesWithPage = (app_id: string, req: BasePaginatorRequest) => {
  return get<GetPublishHistoriesWithPageResponse>(`/apps/${app_id}/publish-histories`, {
    params: req,
  })
}

// 回退指定的历史配置到草稿
export const fallbackHistoryToDraft = (app_id: string, app_config_version_id: string) => {
  return post<BaseResponse<any>>(`/apps/${app_id}/fallback-history`, {
    body: { app_config_version_id },
  })
}

// 获取指定应用的发布配置信息
export const getPublishedConfig = (app_id: string) => {
  return get<GetPublishedConfigResponse>(`/apps/${app_id}/published-config`)
}

// 重新生成 WebApp 的凭证标识
export const regenerateWebAppToken = (app_id: string) => {
  return post<RegenerateWebAppTokenResponse>(`/apps/${app_id}/regenerate-web-app-token`)
}

export const getPlannerWorkers = (app_id: string) => {
  return get<GetPlannerWorkersResponse>(`/apps/${app_id}/planner/workers`)
}

export const bindPlannerWorker = (app_id: string, req: BindPlannerWorkerRequest) => {
  return post<BaseResponse<{ id: string }>>(`/apps/${app_id}/planner/workers`, { body: req })
}

export const updatePlannerWorkerBinding = (
  app_id: string,
  binding_id: string,
  req: UpdatePlannerWorkerBindingRequest,
) => {
  return patch<BaseResponse<any>>(`/apps/${app_id}/planner/workers/${binding_id}`, { body: req })
}

export const deletePlannerWorkerBinding = (app_id: string, binding_id: string) => {
  return del<BaseResponse<any>>(`/apps/${app_id}/planner/workers/${binding_id}`)
}

export const getAppCapabilitySummary = (app_id: string) => {
  return get<CapabilitySummaryResponse>(`/apps/${app_id}/capability-summary`)
}

export const refreshAppCapabilitySummary = (
  app_id: string,
  req: RefreshCapabilitySummaryRequest = { preserve_manual_overrides: true },
) => {
  return post<CapabilitySummaryResponse>(`/apps/${app_id}/capability-summary/refresh`, { body: req })
}

export const patchAppCapabilitySummary = (app_id: string, req: PatchCapabilitySummaryRequest) => {
  return patch<CapabilitySummaryResponse>(`/apps/${app_id}/capability-summary`, { body: req })
}

export const getPlannerRoutingPolicy = (app_id: string) => {
  return get<RoutingPolicyResponse>(`/apps/${app_id}/planner/routing-policy`)
}

export const savePlannerRoutingPolicy = (app_id: string, req: RoutingPolicyRequest) => {
  return put<RoutingPolicyResponse>(`/apps/${app_id}/planner/routing-policy`, { body: req })
}

export const validatePlannerRoutingPolicy = (app_id: string, req: RoutingPolicyRequest) => {
  return post<RoutingPolicyValidateResponse>(`/apps/${app_id}/planner/routing-policy/validate`, {
    body: req,
  })
}

export const preflightPlannerWorkers = (app_id: string, req: PlannerPreflightRequest) => {
  return post<PlannerPreflightResponse>(`/apps/${app_id}/planner/preflight`, { body: req })
}

export const dryRunPlanner = (app_id: string, req: PlannerDryRunRequest) => {
  return post<PlannerDryRunResponse>(`/apps/${app_id}/planner/dry-run`, { body: req })
}
