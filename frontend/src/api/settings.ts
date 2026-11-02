import { apiClient } from '@core/lib/api-client'
import type { UserSettings as DlUserSettings } from '@dl/types'
import type { SettingsPatch } from './settings-values'

export type { DlUserSettings }

export interface DlAdminSettings {
  download_retries: number
  download_timeout: number
  max_file_size_mb: number
  rate_limit_per_minute: number
  rate_limit_per_hour: number
  rate_limit_per_day: number
  max_playlist_count: number
  [key: string]: unknown
}

export const dlSettingsApi = {
  getMine: () =>
    apiClient.get<DlUserSettings>('/dl/settings'),

  patchMine: (body: SettingsPatch, etag: string) =>
    apiClient.patch<DlUserSettings>('/dl/settings', body, { headers: { 'If-Match': etag } }),

  getAdmin: () =>
    apiClient.get<DlAdminSettings>('/dl/admin/settings'),

  patchAdmin: (body: Partial<DlAdminSettings>) =>
    apiClient.patch<DlAdminSettings>('/dl/admin/settings', body),
}
