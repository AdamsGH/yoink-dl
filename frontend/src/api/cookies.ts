import { apiClient } from '@core/lib/api-client'
import type { Cookie } from '@dl/types'
import type { User, PaginatedResponse } from '@core/types/api'

export interface CookieUploadBody {
  user_id: number
  domain: string
  content: string
}

export interface CookiePoolAddBody {
  domain: string
  content: string
}

export const cookiesApi = {
  listMine: () =>
    apiClient.get<Cookie[]>('/dl/cookies'),

  listAll: () =>
    apiClient.get<Cookie[]>('/dl/cookies/all'),

  listPool: () =>
    apiClient.get<Cookie[]>('/dl/cookies/pool'),

  upload: (body: CookieUploadBody) =>
    apiClient.post<Cookie>('/dl/cookies', body),

  addPool: (body: CookiePoolAddBody) =>
    apiClient.post<Cookie>('/dl/cookies/pool', body),

  uploadPersonal: (body: { domain: string; content: string }) =>
    apiClient.post<Cookie>('/dl/cookies/upload', body),

  validate: (id: number) =>
    apiClient.post<Cookie>(`/dl/cookies/${id}/validate`, {}),

  deleteById: (id: number) =>
    apiClient.delete(`/dl/cookies/by-id/${id}`),

  deletePoolById: (id: number) =>
    apiClient.delete(`/dl/cookies/pool/${id}`),

  refreshLabels: () =>
    apiClient.post<{ updated: number }>('/dl/cookies/pool/refresh-labels', {}),

  listUsers: () =>
    apiClient.get<PaginatedResponse<User>>('/users', { params: { limit: 200 } }),
}
