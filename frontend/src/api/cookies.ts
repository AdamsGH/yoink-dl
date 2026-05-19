import { apiClient } from '@core/lib/api-client'
import type { Cookie } from '@dl/types'
import type { User, PaginatedResponse } from '@core/types/api'

export interface YttvOAuthStartResponse {
  session_id: string
  verification_url: string
  user_code: string
  expires_in: number
  interval: number
}

export interface YttvOAuthPollResponse {
  status: 'pending' | 'expired' | 'error' | 'ok'
  detail?: string
}

export interface CookieTokenResponse {
  token: string
  expires_in: number
  submit_url: string
}

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

  getToken: () =>
    apiClient.post<CookieTokenResponse>('/dl/cookies/token', {}),

  refreshLabels: () =>
    apiClient.post<{ updated: number }>('/dl/cookies/pool/refresh-labels', {}),

  yttvOAuthStart: () =>
    apiClient.post<YttvOAuthStartResponse>('/dl/cookies/yttv/start', {}),

  yttvOAuthPoll: (sessionId: string) =>
    apiClient.get<YttvOAuthPollResponse>(`/dl/cookies/yttv/poll/${sessionId}`),

  listUsers: () =>
    apiClient.get<PaginatedResponse<User>>('/users', { params: { limit: 200 } }),
}
