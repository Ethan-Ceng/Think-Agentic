/** 与 BasePaginatorResponse 中 paginator 字段一致 */
export type PaginatorState = {
  current_page: number
  page_size: number
  total_page: number
  total_record: number
}

/**
 * 部分 FastAPI 列表接口把分页字段摊在 data 顶层；另一部分使用 data.paginator（如 PageModel）。
 * 统一为 { list, paginator }，避免前端读错结构导致分页器为 undefined、列表不渲染。
 */
export function normalizeListPaginator<T>(data: {
  list?: T[]
  paginator?: Partial<PaginatorState> | null
  current_page?: number
  page_size?: number
  total_page?: number
  total_record?: number
}): { list: T[]; paginator: PaginatorState } {
  const list = (data?.list ?? []) as T[]
  const nested = data?.paginator
  if (nested && typeof nested === 'object') {
    return {
      list,
      paginator: {
        current_page: Number(nested.current_page ?? 1),
        page_size: Number(nested.page_size ?? 20),
        total_page: Number(nested.total_page ?? 0),
        total_record: Number(nested.total_record ?? 0),
      },
    }
  }
  return {
    list,
    paginator: {
      current_page: Number(data?.current_page ?? 1),
      page_size: Number(data?.page_size ?? 20),
      total_page: Number(data?.total_page ?? 0),
      total_record: Number(data?.total_record ?? 0),
    },
  }
}
