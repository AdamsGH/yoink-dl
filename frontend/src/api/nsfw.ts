import { apiClient } from '@core/lib/api-client'

export interface NsfwDomain {
  id: number
  domain: string
  note: string | null
  created_at: string
}

export interface NsfwKeyword {
  id: number
  keyword: string
  note: string | null
  created_at: string
}

export interface NsfwCheckResponse {
  url: string
  is_nsfw: boolean
  matched_domain: string | null
  matched_keyword: string | null
  matched_keywords?: string[]
}

export const nsfwApi = {
  getDomains: () =>
    apiClient.get<NsfwDomain[]>('/dl/nsfw/domains'),

  getKeywords: () =>
    apiClient.get<NsfwKeyword[]>('/dl/nsfw/keywords'),

  addDomain: (domain: string, note?: string | null) =>
    apiClient.post<NsfwDomain>('/dl/nsfw/domains', { domain, note: note ?? null }),

  addKeyword: (keyword: string, note?: string | null) =>
    apiClient.post<NsfwKeyword>('/dl/nsfw/keywords', { keyword, note: note ?? null }),

  updateDomain: (id: number, domain: string, note?: string | null) =>
    apiClient.patch<NsfwDomain>(`/dl/nsfw/domains/${id}`, { domain, note: note ?? null }),

  updateKeyword: (id: number, keyword: string, note?: string | null) =>
    apiClient.patch<NsfwKeyword>(`/dl/nsfw/keywords/${id}`, { keyword, note: note ?? null }),

  deleteDomain: (id: number) =>
    apiClient.delete(`/dl/nsfw/domains/${id}`),

  deleteKeyword: (id: number) =>
    apiClient.delete(`/dl/nsfw/keywords/${id}`),

  check: (url: string) =>
    apiClient.post<NsfwCheckResponse>('/dl/nsfw/check', { url }),

  import: (body: { domains?: Array<{ domain: string; note?: string }>; keywords?: Array<{ keyword: string; note?: string }> }) =>
    apiClient.post('/dl/nsfw/import', body),

  exportUrl: () =>
    `${apiClient.defaults.baseURL}/dl/nsfw/export`,

  export: () =>
    apiClient.get<unknown>('/dl/nsfw/export'),
}
