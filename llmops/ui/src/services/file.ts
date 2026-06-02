import { del, get, patch, post, upload } from '@/utils/request'
import type { FileResponse, GetFilesResponse } from '@/models/file'

export const getFiles = (params: { parent_id?: string; search_word?: string } = {}) => {
  return get<GetFilesResponse>('/files', { params })
}

export const createFolder = (body: { name: string; parent_id?: string | null }) => {
  return post<FileResponse>('/files/folders', { body })
}

export const updateFile = (fileId: string, body: { name: string }) => {
  return patch<FileResponse>(`/files/${fileId}`, { body })
}

export const deleteFile = (fileId: string) => {
  return del<FileResponse>(`/files/${fileId}`)
}

export const uploadManagedFile = (file: File, parentId?: string | null) => {
  const formData = new FormData()
  formData.append('file', file)
  const suffix = parentId ? `?parent_id=${encodeURIComponent(parentId)}` : ''
  return upload<FileResponse>(`/files/upload${suffix}`, { data: formData })
}
