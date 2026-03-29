import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { apiClient } from '@core/lib/api-client'
import { Input } from '@core/components/ui/input'
import { Button } from '@core/components/ui/button'
import { Skeleton } from '@core/components/ui/skeleton'
import { toast } from '@core/components/ui/toast'

interface DlAdminSettings {
  download_retries: number
  download_timeout: number
  max_file_size_gb: number
  rate_limit_per_minute: number
  rate_limit_per_hour: number
  rate_limit_per_day: number
  max_playlist_count: number
}

function SettingRow({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="text-sm">{label}</p>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </div>
      <div className="shrink-0 w-24">{children}</div>
    </div>
  )
}

export function DlSettingsSection() {
  const { t } = useTranslation()
  const [data, setData] = useState<DlAdminSettings | null>(null)
  const [dirty, setDirty] = useState<Partial<DlAdminSettings>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    apiClient.get<DlAdminSettings>('/dl/admin/settings')
      .then(r => setData(r.data))
      .catch(() => toast.error(t('common.load_error', { defaultValue: 'Failed to load' })))
  }, [])

  const set = <K extends keyof DlAdminSettings>(key: K, raw: string) => {
    const num = key === 'max_file_size_gb' ? parseFloat(raw) : parseInt(raw, 10)
    if (!isNaN(num)) setDirty(prev => ({ ...prev, [key]: num }))
  }

  const val = <K extends keyof DlAdminSettings>(key: K): string => {
    const v = dirty[key] ?? data?.[key]
    return v !== undefined ? String(v) : ''
  }

  const save = async () => {
    if (!Object.keys(dirty).length) return
    setSaving(true)
    try {
      const updated = await apiClient.patch<DlAdminSettings>('/dl/admin/settings', dirty)
      setData(updated.data)
      setDirty({})
      toast.success(t('bot_settings.save_ok', { defaultValue: 'Saved' }))
    } catch {
      toast.error(t('bot_settings.save_error', { defaultValue: 'Save failed' }))
    } finally {
      setSaving(false)
    }
  }

  if (!data) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="flex items-center justify-between py-2.5">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-8 w-24" />
          </div>
        ))}
      </div>
    )
  }

  const isDirty = Object.keys(dirty).length > 0

  return (
    <div>
      <SettingRow
        label={t('bot_settings.dl_retries', { defaultValue: 'Download retries' })}
        hint={t('bot_settings.dl_retries_hint', { defaultValue: 'Retry transient errors (ffmpeg crash, network glitch)' })}
      >
        <Input className="h-8 text-xs text-right" type="number" min={1} max={10} value={val('download_retries')} onChange={e => set('download_retries', e.target.value)} />
      </SettingRow>
      <SettingRow
        label={t('bot_settings.dl_timeout', { defaultValue: 'Download timeout (s)' })}
        hint={t('bot_settings.dl_timeout_hint', { defaultValue: 'Max seconds per download job' })}
      >
        <Input className="h-8 text-xs text-right" type="number" min={60} value={val('download_timeout')} onChange={e => set('download_timeout', e.target.value)} />
      </SettingRow>
      <SettingRow
        label={t('bot_settings.dl_max_size', { defaultValue: 'Max file size (GB)' })}
      >
        <Input className="h-8 text-xs text-right" type="number" min={0.1} max={4} step={0.1} value={val('max_file_size_gb')} onChange={e => set('max_file_size_gb', e.target.value)} />
      </SettingRow>
      <SettingRow
        label={t('bot_settings.dl_rl_min', { defaultValue: 'Rate limit / minute' })}
      >
        <Input className="h-8 text-xs text-right" type="number" min={1} value={val('rate_limit_per_minute')} onChange={e => set('rate_limit_per_minute', e.target.value)} />
      </SettingRow>
      <SettingRow
        label={t('bot_settings.dl_rl_hour', { defaultValue: 'Rate limit / hour' })}
      >
        <Input className="h-8 text-xs text-right" type="number" min={1} value={val('rate_limit_per_hour')} onChange={e => set('rate_limit_per_hour', e.target.value)} />
      </SettingRow>
      <SettingRow
        label={t('bot_settings.dl_rl_day', { defaultValue: 'Rate limit / day' })}
      >
        <Input className="h-8 text-xs text-right" type="number" min={1} value={val('rate_limit_per_day')} onChange={e => set('rate_limit_per_day', e.target.value)} />
      </SettingRow>
      <SettingRow
        label={t('bot_settings.dl_playlist', { defaultValue: 'Max playlist items' })}
      >
        <Input className="h-8 text-xs text-right" type="number" min={1} max={500} value={val('max_playlist_count')} onChange={e => set('max_playlist_count', e.target.value)} />
      </SettingRow>

      <div className={`flex justify-end pt-3 transition-opacity ${isDirty ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
        <Button size="sm" className="h-7 px-3 text-xs" onClick={save} disabled={saving || !isDirty}>
          {saving ? t('common.loading', { defaultValue: 'Saving…' }) : t('common.save', { defaultValue: 'Save' })}
        </Button>
      </div>
    </div>
  )
}
