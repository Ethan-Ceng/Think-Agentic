import { apiPrefix } from '@/config'

/**
 * 将后端返回的静态资源 URL 对齐到当前 `apiPrefix`。
 * 开发环境常见：历史数据里存了 `http://localhost:3000/upload-files/...`，与真实 API 端口不一致导致图片 404/拒绝连接。
 */
export function resolveApiAssetUrl(src: string | undefined | null): string {
  if (src == null || src === '') return ''
  const marker = '/upload-files'
  const i = src.indexOf(marker)
  if (i === -1) return src
  const path = src.slice(i)
  const base = apiPrefix.endsWith('/') ? apiPrefix.slice(0, -1) : apiPrefix
  return `${base}${path}`
}
