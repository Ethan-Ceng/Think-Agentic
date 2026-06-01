import type { ApiResponse } from './types'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const API_CONFIG = {
  baseURL: API_BASE_URL,
  timeout: 30000,
} as const

export class ApiError extends Error {
  code: number
  data: unknown

  constructor(code: number, msg: string, data: unknown = null) {
    super(msg)
    this.name = 'ApiError'
    this.code = code
    this.data = data
  }
}

type RequestOptions = RequestInit & {
  timeout?: number
  skipErrorHandler?: boolean
}

async function parseResponse<T>(response: Response): Promise<ApiResponse<T>> {
  const contentType = response.headers.get('content-type')

  if (contentType?.includes('application/json')) {
    return await response.json()
  }

  const text = await response.text()
  return {
    code: response.ok ? 0 : response.status,
    msg: response.ok ? 'success' : text || response.statusText,
    data: text as T,
  }
}

async function handleErrorResponse(response: Response): Promise<never> {
  let errorData: ApiResponse

  try {
    errorData = await parseResponse(response)
  } catch {
    errorData = {
      code: response.status,
      msg: response.statusText || '请求失败',
      data: null,
    }
  }

  throw new ApiError(errorData.code, errorData.msg, errorData.data)
}

function fetchWithTimeout(
  url: string,
  options: RequestOptions = {},
  timeout: number = API_CONFIG.timeout,
): Promise<Response> {
  return new Promise((resolve, reject) => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      controller.abort()
      reject(new ApiError(408, '请求超时'))
    }, timeout)

    fetch(url, {
      ...options,
      signal: controller.signal,
    })
      .then((response) => {
        window.clearTimeout(timeoutId)
        resolve(response)
      })
      .catch((error) => {
        window.clearTimeout(timeoutId)
        if (error instanceof Error && error.name === 'AbortError') {
          reject(new ApiError(408, '请求超时'))
        } else {
          reject(error)
        }
      })
  })
}

export async function request<T = unknown>(
  endpoint: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_CONFIG.baseURL}${endpoint}`

  const {
    timeout = API_CONFIG.timeout,
    skipErrorHandler = false,
    headers = {},
    ...fetchOptions
  } = options

  const mergedHeaders: HeadersInit = {
    'Content-Type': 'application/json',
    ...headers,
  }

  if (fetchOptions.body instanceof FormData) {
    delete (mergedHeaders as Record<string, string>)['Content-Type']
  }

  try {
    const response = await fetchWithTimeout(
      url,
      {
        ...fetchOptions,
        headers: mergedHeaders,
      },
      timeout,
    )

    if (!response.ok) {
      if (skipErrorHandler) {
        return parseResponse<T>(response) as Promise<T>
      }
      await handleErrorResponse(response)
    }

    const result = await parseResponse<T>(response)

    if (result.code !== 0 && result.code !== 200) {
      if (skipErrorHandler) {
        return result.data as T
      }
      throw new ApiError(result.code, result.msg, result.data)
    }

    return result.data as T
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }

    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      throw new ApiError(500, '网络连接失败，请检查网络设置')
    }

    throw new ApiError(500, error instanceof Error ? error.message : '未知错误')
  }
}

export function get<T = unknown>(
  endpoint: string,
  params?: Record<string, string | number | boolean | undefined | null>,
  options?: RequestOptions,
): Promise<T> {
  let url = endpoint

  if (params) {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value))
      }
    })
    const queryString = searchParams.toString()
    if (queryString) {
      url += `?${queryString}`
    }
  }

  return request<T>(url, {
    ...options,
    method: 'GET',
  })
}

export function post<T = unknown>(
  endpoint: string,
  data?: unknown,
  options?: RequestOptions,
): Promise<T> {
  return request<T>(endpoint, {
    ...options,
    method: 'POST',
    body: data instanceof FormData ? data : JSON.stringify(data),
  })
}

export function put<T = unknown>(
  endpoint: string,
  data?: unknown,
  options?: RequestOptions,
): Promise<T> {
  return request<T>(endpoint, {
    ...options,
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function del<T = unknown>(endpoint: string, options?: RequestOptions): Promise<T> {
  return request<T>(endpoint, {
    ...options,
    method: 'DELETE',
  })
}

export async function createSSEStream(
  endpoint: string,
  data?: unknown,
  options?: RequestOptions,
): Promise<ReadableStream<Uint8Array>> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_CONFIG.baseURL}${endpoint}`

  const {
    timeout = API_CONFIG.timeout,
    headers = {},
    signal: externalSignal,
    ...fetchOptions
  } = options || {}

  const mergedHeaders: HeadersInit = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
    ...headers,
  }

  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => {
    controller.abort()
  }, timeout)

  if (externalSignal) {
    if (externalSignal.aborted) {
      window.clearTimeout(timeoutId)
      controller.abort()
    } else {
      externalSignal.addEventListener(
        'abort',
        () => {
          window.clearTimeout(timeoutId)
          controller.abort()
        },
        { once: true },
      )
    }
  }

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      method: 'POST',
      headers: mergedHeaders,
      body: JSON.stringify(data),
      signal: controller.signal,
    })

    window.clearTimeout(timeoutId)

    if (!response.ok) {
      await handleErrorResponse(response)
    }

    if (!response.body) {
      throw new ApiError(500, '响应体为空')
    }

    return response.body
  } catch (error) {
    window.clearTimeout(timeoutId)
    if (error instanceof Error && error.name === 'AbortError') {
      throw error
    }
    if (error instanceof ApiError) {
      throw error
    }
    throw new ApiError(500, error instanceof Error ? error.message : '未知错误')
  }
}

export async function parseSSEStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: MessageEvent) => void,
  onError?: (error: Error) => void,
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()

      if (done) {
        if (buffer.trim()) {
          processSSEBuffer(buffer, onEvent, onError)
        }
        break
      }

      buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n')

      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''

      for (const part of parts) {
        if (part.trim()) {
          processSSEEvent(part, onEvent, onError)
        }
      }
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return
    }
    onError?.(error instanceof Error ? error : new Error('读取流失败'))
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // noop
    }
  }
}

function processSSEEvent(
  eventText: string,
  onEvent: (event: MessageEvent) => void,
  onError?: (error: Error) => void,
): void {
  let eventType = 'message'
  let eventData = ''
  let eventId = ''

  for (const line of eventText.split('\n')) {
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      const dataLine = line.slice(5)
      eventData = eventData ? `${eventData}\n${dataLine}` : dataLine
    } else if (line.startsWith('id:')) {
      eventId = line.slice(3).trim()
    }
  }

  if (!eventData) return

  try {
    const data = JSON.parse(eventData.trim())
    onEvent(
      new MessageEvent(eventType, {
        data,
        lastEventId: eventId,
      }),
    )
  } catch (error) {
    onError?.(
      error instanceof Error ? error : new Error(`解析 SSE 数据失败: ${eventData}`),
    )
  }
}

function processSSEBuffer(
  buffer: string,
  onEvent: (event: MessageEvent) => void,
  onError?: (error: Error) => void,
): void {
  const events = buffer.split('\n\n').filter((event) => event.trim())
  for (const event of events) {
    processSSEEvent(event, onEvent, onError)
  }
}
