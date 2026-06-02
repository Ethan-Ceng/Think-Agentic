import type { BaseResponse } from '@/models/base'

export type FileItem = {
  id: string
  parent_id: string | null
  type: 'file' | 'folder'
  name: string
  extension: string
  mime_type: string
  size: number
  storage_provider: string
  file_path: string
  source: string
  status: string
  url: string
  download_url: string
  preview_url: string
  created_at: number
  updated_at: number
}

export type GetFilesResponse = BaseResponse<FileItem[]>
export type FileResponse = BaseResponse<FileItem>
