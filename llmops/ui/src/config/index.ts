// api请求接口前缀
export const apiPrefix: string = import.meta.env.VITE_API_PREFIX || '/api'

/** 应用名（与 `.env` 中 `VITE_TITLE`、`index.html` 标题一致） */
export const appTitle: string = import.meta.env.VITE_TITLE || 'LLMOps'

/** 一句话描述，用于侧栏品牌副文案 */
export const appDescription: string = import.meta.env.VITE_DESCRIPTION || ''

/**
 * 侧栏 Logo 图片地址；留空则使用内置图标样式。
 * 可设为 public 资源路径，例如 `/logo.png`，或任意可访问的图片 URL。
 */
export const appLogoUrl: string = import.meta.env.VITE_APP_LOGO?.trim() || ''

// 业务状态码
export const httpCode = {
  success: 'success',
  fail: 'fail',
  notFound: 'not_found',
  unauthorized: 'unauthorized',
  forbidden: 'forbidden',
  validateError: 'validate_error',
}

// 类型字符串与中文映射
export const typeMap: { [key: string]: string } = {
  str: '字符串',
  int: '整型',
  float: '浮点型',
  bool: '布尔值',
}

// 智能体事件类型
export const QueueEvent = {
  longTermMemoryRecall: 'long_term_memory_recall',
  agentThought: 'agent_thought',
  agentMessage: 'agent_message',
  agentAction: 'agent_action',
  datasetRetrieval: 'dataset_retrieval',
  agentEnd: 'agent_ent',
  stop: 'stop',
  error: 'error',
  timeout: 'timeout',
  ping: 'ping',
}
