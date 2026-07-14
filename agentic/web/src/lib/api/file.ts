import { API_BASE_URL, del, get, patch, post } from './fetch'
import { getAuthToken } from './auth-token'
import type { FileInfo, FileUploadParams, FolderTreeItem, ManagedFile, ManagedFilesData } from './types'

export const fileApi = {
  uploadFile: async (params: FileUploadParams): Promise<FileInfo> => {
    const formData = new FormData()
    formData.append('file', params.file)

    if (params.session_id) {
      formData.append('session_id', params.session_id)
    }
    if (params.parent_id) formData.append('parent_id', params.parent_id)

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

  listFiles: (params: { parent_id?: string; search_word?: string; file_kind?: string; source_type?: string; current_page?: number; page_size?: number } = {}): Promise<ManagedFilesData> =>
    get<ManagedFilesData>('/files', params),

  listFolders: (): Promise<FolderTreeItem[]> => get<FolderTreeItem[]>('/files/folders/tree'),

  createFolder: (name: string, parent_id?: string | null): Promise<ManagedFile> =>
    post<ManagedFile>('/files/folders', { name, parent_id }),

  updateFile: (fileId: string, data: { name?: string; parent_id?: string | null }): Promise<ManagedFile> =>
    patch<ManagedFile>(`/files/${fileId}`, data),

  deleteFile: (fileId: string): Promise<ManagedFile> => del<ManagedFile>(`/files/${fileId}`),

  batchMove: (file_ids: string[], parent_id?: string | null): Promise<ManagedFile[]> =>
    post<ManagedFile[]>('/files/batch-move', { file_ids, parent_id }),

  batchDelete: (file_ids: string[]): Promise<ManagedFile[]> =>
    post<ManagedFile[]>('/files/batch-delete', { file_ids }),

  previewFile: async (fileId: string): Promise<Blob> => {
    const token = getAuthToken()
    const response = await fetch(`${API_BASE_URL}/files/${fileId}/preview`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    if (!response.ok) throw new Error(`预览失败: ${response.statusText}`)
    return response.blob()
  },
}
