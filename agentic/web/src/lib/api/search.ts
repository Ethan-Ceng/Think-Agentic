import { get } from './fetch'
import type { SearchResults } from './types'

export const searchApi = {
  search: (params: { q: string; current_page?: number; page_size?: number }): Promise<SearchResults> =>
    get<SearchResults>('/search', params),
}
