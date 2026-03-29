import type { UserRole } from '@core/types/api'

export interface UserSettings {
  user_id: number
  language: string
  quality: string
  codec: string
  container: string
  proxy_enabled: boolean
  proxy_url: string | null
  subs_enabled: boolean
  subs_auto: boolean
  subs_always_ask: boolean
  subs_lang: string
  split_size: number
  nsfw_blur: boolean
  mediainfo: boolean
  send_as_file: boolean
  gallery_zip: boolean
  use_pool_cookies: boolean
  theme: string
  keyboard: string
  args_json: Record<string, unknown>
  updated_at: string
}

export interface DownloadLog {
  id: number
  user_id: number
  url: string
  domain: string | null
  title: string | null
  quality: string | null
  file_size: number | null
  duration: number | null
  file_count: number | null
  status: string
  error_msg: string | null
  group_id: number | null
  group_title: string | null
  thread_id: number | null
  message_id: number | null
  clip_start: number | null
  clip_end: number | null
  created_at: string
  media_type: 'video' | 'audio' | 'gallery' | 'clip' | 'error'
}

export interface Cookie {
  id: number
  user_id: number
  domain: string
  is_valid: boolean
  is_pool: boolean
  label: string | null
  avatar_url: string | null
  validated_at: string | null
  created_at: string
  updated_at: string
  inherited?: boolean
}

export interface Group {
  id: number
  title: string | null
  enabled: boolean
  auto_grant_role: UserRole
  allow_pm: boolean
  nsfw_allowed: boolean
  storage_chat_id: number | null
  storage_thread_id: number | null
  created_at: string
  thread_policies: ThreadPolicy[]
}

export interface ThreadPolicy {
  id: number
  group_id: number
  thread_id: number | null
  name: string | null
  enabled: boolean
}

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

export interface NsfwCheckRequest {
  url: string
  title?: string
  description?: string
}

export interface NsfwCheckResponse {
  url: string
  is_nsfw: boolean
  matched_domain: string | null
  matched_keywords: string[]
}

export interface StatsOverview {
  total_downloads: number
  downloads_today: number
  cache_hits_today: number
  errors_today: number
  top_domains: Array<{ domain: string; count: number }>
  downloads_by_day: Array<{ date: string; count: number }>
}

export interface RetryResponse {
  status: string
  url: string
  log_id: number
}

export interface GroupCreateRequest {
  id: number
  title?: string | null
  enabled?: boolean
  auto_grant_role?: UserRole
  allow_pm?: boolean
  nsfw_allowed?: boolean
}

export interface GroupUpdateRequest {
  title?: string | null
  enabled?: boolean
  auto_grant_role?: UserRole
  allow_pm?: boolean
  nsfw_allowed?: boolean
  storage_chat_id?: number | null
  storage_thread_id?: number | null
}

export interface BotSetting {
  key: string
  value: string | null
}

export interface UserStatsResponse {
  total: number
  this_week: number
  today: number
  top_domains: Array<{ domain: string; count: number }>
  member_since: string
}
