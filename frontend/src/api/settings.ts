import { apiClient } from '@core/lib/api-client'
import type { UserSettings as DlUserSettings } from '@dl/types'

export type { DlUserSettings }

export interface DlAdminSettings {
  download_retries: number
  download_timeout: number
  max_file_size_gb: number
  rate_limit_per_minute: number
  rate_limit_per_hour: number
  rate_limit_per_day: number
  max_playlist_count: number
  [key: string]: unknown
}

export const dlSettingsApi = {
  getMine: () =>
    apiClient.get<DlUserSettings>('/dl/settings'),

  patchMine: (body: Partial<DlUserSettings>) =>
    apiClient.patch<DlUserSettings>('/dl/settings', body),

  getAdmin: () =>
    apiClient.get<DlAdminSettings>('/dl/admin/settings'),

  patchAdmin: (body: Partial<DlAdminSettings>) =>
    apiClient.patch<DlAdminSettings>('/dl/admin/settings', body),
}
