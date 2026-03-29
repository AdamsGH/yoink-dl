import { apiClient } from '@core/lib/api-client'
import type { StatsOverview } from '@dl/types'

export const dlStatsApi = {
  getOverview: (days: number, signal?: AbortSignal) =>
    apiClient.get<StatsOverview>('/dl/stats/overview', { params: { days }, signal }),
}
