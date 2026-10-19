import { apiClient } from '@core/lib/api-client'
import type { PaginatedResponse } from '@core/types/api'
import type { DownloadLog } from '@dl/types'

export type { DownloadLog }

export interface RetryResponse {
  status: string
  message?: string
}

export interface DownloadsQuery {
  page?: number
  offset?: number
  limit?: number
  search?: string
  domain?: string
  status?: string
  media_type?: string
  period?: string
  date_from?: string
}

export const downloadsApi = {
  list: (params: DownloadsQuery) =>
    apiClient.get<PaginatedResponse<DownloadLog>>('/dl/downloads', { params }),

  getDomains: () =>
    apiClient.get<{ domains: string[] }>('/dl/downloads/domains'),

  retry: (id: DownloadLog['id']) =>
    apiClient.post<RetryResponse>(`/dl/downloads/${id}/retry`),
}
