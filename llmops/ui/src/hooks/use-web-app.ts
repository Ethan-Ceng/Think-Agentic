import { ref } from 'vue'
import {
  deleteWebAppConversation,
  generateWebAppSuggestedQuestions,
  getWebApp,
  getWebAppConversationMessages,
  getWebAppConversations,
  stopWebAppChat,
  updateWebAppConversationIsPinned,
  updateWebAppConversationName,
  webAppChat,
} from '@/services/web-app'
import type { WebAppChatRequest } from '@/models/web-app'
import type { GetConversationMessagesWithPageResponse } from '@/models/conversation'
import { confirmWarning } from '@/utils/confirm'
import { ElMessage } from 'element-plus'

export const useGetWebApp = () => {
  // 1.定义自定义hooks所需数据
  const loading = ref(false)
  const web_app = ref<Record<string, any>>({})

  // 2.定义加载数据处理器
  const loadWebApp = async (token: string) => {
    try {
      loading.value = true
      const resp = await getWebApp(token)
      web_app.value = resp.data
    } finally {
      loading.value = false
    }
  }

  return { loading, web_app, loadWebApp }
}

export const useWebAppChat = () => {
  // 1.定义hooks所需数据
  const loading = ref(false)

  // 2.定义WebApp对话处理器
  const handleWebAppChat = async (
    token: string,
    req: WebAppChatRequest,
    onData: (event_response: Record<string, any>) => void,
  ) => {
    try {
      loading.value = true
      await webAppChat(token, req, onData)
    } finally {
      loading.value = false
    }
  }

  return { loading, handleWebAppChat }
}

export const useStopWebAppChat = () => {
  // 1.定义hooks所需数据
  const loading = ref(false)

  // 2.定义停止WebApp对话处理器
  const handleStopWebAppChat = async (token: string, task_id: string) => {
    try {
      loading.value = true
      await stopWebAppChat(token, task_id)
    } finally {
      loading.value = false
    }
  }

  return { loading, handleStopWebAppChat }
}

export const useGetAppConversations = () => {
  // 1.定义hooks所需数据
  const loading = ref(false)
  const pinned_conversations = ref<Record<string, any>[]>([])
  const unpinned_conversations = ref<Record<string, any>[]>([])

  // 2.定义加载数据处理器
  const loadWebAppConversations = async (token: string) => {
    try {
      loading.value = true
      const [pinned_resp, unpinned_resp] = await Promise.all([
        getWebAppConversations(token, true),
        getWebAppConversations(token, false),
      ])

      pinned_conversations.value = pinned_resp.data
      unpinned_conversations.value = unpinned_resp.data
    } finally {
      loading.value = false
    }
  }

  return { loading, pinned_conversations, unpinned_conversations, loadWebAppConversations }
}

export const useGetWebAppConversationMessagesWithPage = () => {
  const loading = ref(false)
  const messages = ref<GetConversationMessagesWithPageResponse['data']['list']>([])
  const created_at = ref(0)
  const defaultPaginator = {
    current_page: 1,
    page_size: 5,
    total_page: 0,
    total_record: 0,
  }
  const paginator = ref({ ...defaultPaginator })

  const loadConversationMessagesWithPage = async (
    token: string,
    conversation_id: string,
    init: boolean = false,
  ) => {
    if (init) {
      paginator.value = { ...defaultPaginator }
      created_at.value = 0
    } else if (paginator.value.current_page > paginator.value.total_page) {
      return
    }

    try {
      loading.value = true
      const resp = await getWebAppConversationMessages(token, conversation_id, {
        current_page: paginator.value.current_page,
        page_size: paginator.value.page_size,
        created_at: created_at.value,
      })
      const data = resp.data

      paginator.value = data.paginator

      if (paginator.value.current_page <= paginator.value.total_page) {
        paginator.value.current_page += 1
      }

      if (init) {
        messages.value = data.list
      } else {
        messages.value.push(...data.list)
        created_at.value = data.list[0]?.created_at ?? 0
      }
    } finally {
      loading.value = false
    }
  }

  return { loading, messages, paginator, loadConversationMessagesWithPage }
}

export const useDeleteWebAppConversation = () => {
  const handleDeleteConversation = (
    token: string,
    conversation_id: string,
    success_callback?: () => void,
  ) => {
    confirmWarning(
      '要删除该会话吗?',
      '删除会话信息后，该会话下的所有聊天记录将被永久删除，无法找回。',
      async () => {
        const resp = await deleteWebAppConversation(token, conversation_id)
        ElMessage.success(resp.message)
        success_callback && success_callback()
      },
    )
  }

  return { handleDeleteConversation }
}

export const useUpdateWebAppConversationIsPinned = () => {
  const loading = ref(false)

  const handleUpdateConversationIsPinned = async (
    token: string,
    conversation_id: string,
    is_pinned: boolean = false,
    success_callback?: () => void,
  ) => {
    try {
      loading.value = true
      const resp = await updateWebAppConversationIsPinned(token, conversation_id, is_pinned)
      ElMessage.success(resp.message)
      success_callback && success_callback()
    } finally {
      loading.value = false
    }
  }

  return { loading, handleUpdateConversationIsPinned }
}

export const useUpdateWebAppConversationName = () => {
  const loading = ref(false)

  const handleUpdateConversationName = async (
    token: string,
    conversation_id: string,
    name: string,
  ) => {
    try {
      loading.value = true
      const resp = await updateWebAppConversationName(token, conversation_id, name)
      ElMessage.success(resp.message)
    } finally {
      loading.value = false
    }
  }

  return { loading, handleUpdateConversationName }
}

export const useGenerateWebAppSuggestedQuestions = () => {
  const loading = ref(false)
  const suggested_questions = ref<string[]>([])

  const handleGenerateSuggestedQuestions = async (token: string, message_id: string) => {
    try {
      loading.value = true
      const resp = await generateWebAppSuggestedQuestions(token, message_id)
      suggested_questions.value = resp.data
    } finally {
      loading.value = false
    }
  }

  return { loading, suggested_questions, handleGenerateSuggestedQuestions }
}
