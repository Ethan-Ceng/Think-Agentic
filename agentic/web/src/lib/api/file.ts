import { API_BASE_URL, get, post } from './fetch'
import { getAuthToken } from './auth-token'
import type { FileInfo, FileUploadParams } from './types'

export const fileApi = {
  uploadFile: async (params: FileUploadParams): Promise<FileInfo> => {
    const formData = new FormData()
    formData.append('file', params.file)

    if (params.session_id) {
      formData.append('session_id', params.session_id)
    }

    return post<FileInfo>('/files', formData)
  },

  getFileInfo: (fileId: string): Promise<FileInfo> => {
    return get<FileInfo>(`/files/${fileId}`)
  },

  downloadFile: async (fileId: string): Promise<Blob> => {
    const token = getAuthToken()
    const response = await fetch(`${API_BASE_URL}/files/${fileId}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })

    if (!response.ok) {
      throw new Error(`下载失败: ${response.statusText}`)
    }

    return response.blob()
  },

  getFileDownloadUrl: (fileId: string): string => {
    return `${API_BASE_URL}/files/${fileId}/download`
  },
}
