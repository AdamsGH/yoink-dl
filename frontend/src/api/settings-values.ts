import type { UserSettings } from '../types'

export const SETTING_FIELDS = [
  'quality', 'codec', 'container', 'audio_codec', 'proxy_enabled', 'proxy_url',
  'keyboard', 'subs_enabled', 'subs_auto', 'subs_always_ask', 'subs_lang',
  'split_size', 'nsfw_blur', 'mediainfo', 'send_as_file', 'gallery_zip',
  'use_pool_cookies', 'youtube_auth_mode',
] as const satisfies readonly (keyof UserSettings)[]

export type SettingsValues = Pick<UserSettings, typeof SETTING_FIELDS[number]>
export type SettingsPatch = Partial<SettingsValues>

export function settingsValues(settings: UserSettings): SettingsValues {
  return Object.fromEntries(SETTING_FIELDS.map((field) => [field, settings[field]])) as SettingsValues
}

export function settingsChanges(values: SettingsValues, saved: SettingsValues): SettingsPatch {
  return Object.fromEntries(SETTING_FIELDS
    .filter((field) => values[field] !== saved[field])
    .map((field) => [field, values[field]])) as SettingsPatch
}

export const CODEC_OPTIONS = [
  { value: 'avc1', label: 'H.264' },
  { value: 'av01', label: 'AV1' },
  { value: 'vp09', label: 'VP9' },
]

export const CONTAINER_OPTIONS = [
  { value: 'mp4', label: 'MP4' },
  { value: 'mkv', label: 'MKV' },
]

export const SPLIT_OPTIONS = [
  { value: '524288000', label: '500 MiB' },
  { value: '1073741824', label: '1 GiB' },
  { value: '1610612736', label: '1.5 GiB' },
  { value: '2043000000', label: '2 GB' },
]

export function settingsEtag(headers: unknown): string {
  const etag = headers && typeof headers === 'object' && 'etag' in headers ? headers.etag : undefined
  if (typeof etag !== 'string' || !/^"[0-9]+"$/.test(etag)) {
    throw new Error('Missing settings revision')
  }
  return etag
}
