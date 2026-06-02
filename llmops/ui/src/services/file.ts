import { del, get, patch, post, upload } from '@/utils/request'
import type {
  FileBatchResponse,
  FileResponse,
  GetFileFolderTreeResponse,
  GetFilesResponse,
  GetFilesWithPageResponse,
} from '@/models/file'

export type GetFilesParams = {
  parent_id?: string
  search_word?: string
  file_kind?: string
  source?: string
}

export type GetFilesWithPageParams = GetFilesParams & {
  current_page: number
  page_size: number
}

export const getFiles = (params: GetFilesParams = {}) => {
  return get<GetFilesResponse>('/files', { params })
}

export const getFilesWithPage = (params: GetFilesWithPageParams) => {
  return get<GetFilesWithPageResponse>('/files', { params })
}

export const getFileFolderTree = () => {
  return get<GetFileFolderTreeResponse>('/files/folders/tree')
}

export const createFolder = (body: { name: string; parent_id?: string | null }) => {
  return post<FileResponse>('/files/folders', { body })
}

export const updateFile = (fileId: string, body: { name?: string; parent_id?: string | null }) => {
  return patch<FileResponse>(`/files/${fileId}`, { body })
}

export const deleteFile = (fileId: string) => {
  return del<FileResponse>(`/files/${fileId}`)
}

export const batchMoveFiles = (body: { file_ids: string[]; parent_id?: string | null }) => {
  return post<FileBatchResponse>('/files/batch-move', { body })
}

export const batchDeleteFiles = (fileIds: string[]) => {
  return post<FileBatchResponse>('/files/batch-delete', { body: { file_ids: fileIds } })
}

export const uploadManagedFile = (file: File, parentId?: string | null) => {
  const formData = new FormData()
  formData.append('file', file)
  const suffix = parentId ? `?parent_id=${encodeURIComponent(parentId)}` : ''
  return upload<FileResponse>(`/files/upload${suffix}`, { data: formData })
}
