import { del, get, post, put, ssePost } from '@/utils/request'
import type {
  GetConversationMessagesWithPageRequest,
  GetConversationMessagesWithPageResponse,
} from '@/models/conversation'
import type {
  GetWebAppConversationsResponse,
  GetWebAppResponse,
  WebAppChatRequest,
} from '@/models/web-app'
import type { BaseResponse } from '@/models/base'

// 根据标识获取指定 WebApp 基础信息
export const getWebApp = (token: string) => {
  return get<GetWebAppResponse>(`/web-apps/${token}`)
}

// 与指定 WebApp 进行对话
export const webAppChat = (
  token: string,
  req: WebAppChatRequest,
  onData: (event_response: Record<string, any>) => void,
) => {
  return ssePost(`/web-apps/${token}/chat`, { body: req }, onData)
}

// 停止与指定 WebApp 进行对话
export const stopWebAppChat = (token: string, task_id: string) => {
  return post<BaseResponse<any>>(`/web-apps/${token}/stop/${task_id}`)
}

// 获取指定应用的会话列表
export const getWebAppConversations = (token: string, is_pinned: boolean = false) => {
  return get<GetWebAppConversationsResponse>(`/web-apps/${token}/conversations`, {
    params: { is_pinned },
  })
}

export const getWebAppConversationMessages = (
  token: string,
  conversation_id: string,
  req: GetConversationMessagesWithPageRequest,
) => {
  return get<GetConversationMessagesWithPageResponse>(
    `/web-apps/${token}/conversations/${conversation_id}/messages`,
    { params: req },
  )
}

export const deleteWebAppConversation = (token: string, conversation_id: string) => {
  return del<BaseResponse<any>>(`/web-apps/${token}/conversations/${conversation_id}`)
}

export const updateWebAppConversationIsPinned = (
  token: string,
  conversation_id: string,
  is_pinned: boolean,
) => {
  return put<BaseResponse<any>>(`/web-apps/${token}/conversations/${conversation_id}/is-pinned`, {
    body: { is_pinned },
  })
}

export const updateWebAppConversationName = (
  token: string,
  conversation_id: string,
  name: string,
) => {
  return put<BaseResponse<any>>(`/web-apps/${token}/conversations/${conversation_id}/name`, {
    body: { name },
  })
}

export const generateWebAppSuggestedQuestions = (token: string, message_id: string) => {
  return post<BaseResponse<string[]>>(`/web-apps/${token}/suggested-questions`, {
    body: { message_id },
  })
}
