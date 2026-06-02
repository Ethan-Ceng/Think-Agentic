import { type BaseResponse } from '@/models/base'

// 上传图片响应结构
export type UploadImageResponse = BaseResponse<{
  image_url: string
}>

// 上传文件响应结构
export type UploadFileResponse = BaseResponse<{
  id: string
  account_id: string
  name: string
  key: string
  file_path: string
  storage_provider: string
  size: number
  extension: string
  mime_type: string
  created_at: number
}>
