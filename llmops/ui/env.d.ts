/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_PREFIX: string
  readonly VITE_TITLE?: string
  readonly VITE_DESCRIPTION?: string
  /** 侧边栏 Logo 图片 URL 或 public 下路径，如 `/brand.svg` */
  readonly VITE_APP_LOGO?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
