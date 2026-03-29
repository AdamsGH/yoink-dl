import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { apiClient } from '@core/lib/api-client'
import { Button, Input, Skeleton, Slider } from '@ui'
import { toast } from '@core/components/ui/toast'
import { SettingRow } from '@app'

interface DlAdminSettings {
  download_retries: number
  download_timeout: number
  max_file_size_gb: number
  rate_limit_per_minute: number
  rate_limit_per_hour: number
  rate_limit_per_day: number
  max_playlist_count: number
}


// Numeric input — no spinners, right-aligned text, free editing
function NumInput({ value, onChange, min, max }: { value: number; onChange: (v: number) => void; min?: number; max?: number }) {
  const [raw, setRaw] = useState(String(value))

  // Sync when external value changes (e.g. after load/save)
  useEffect(() => { setRaw(String(value)) }, [value])

  return (
    <Input
      className="w-20 h-8 text-xs text-right [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
      type="text"
      inputMode="numeric"
      value={raw}
      onChange={e => {
        setRaw(e.target.value)
        const n = parseInt(e.target.value, 10)
        if (!isNaN(n) && (min === undefined || n >= min) && (max === undefined || n <= max)) onChange(n)
      }}
      onBlur={() => {
        // Snap back to last valid value if field left empty/invalid
        const n = parseInt(raw, 10)
        if (isNaN(n)) setRaw(String(value))
      }}
    />
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
      .catch(() => toast.error('Failed to load downloader settings'))
  }, [])

  const set = <K extends keyof DlAdminSettings>(key: K, value: DlAdminSettings[K]) =>
    setDirty(prev => ({ ...prev, [key]: value }))

  const val = <K extends keyof DlAdminSettings>(key: K): DlAdminSettings[K] =>
    (dirty[key] ?? data?.[key]) as DlAdminSettings[K]

  const save = async () => {
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
      <div>
        {[...Array(6)].map((_, i) => (
          <div key={i} className="flex items-center justify-between py-1.5">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-8 w-20" />
          </div>
        ))}
      </div>
    )
  }

  const isDirty = Object.keys(dirty).length > 0

  return (
    <div>
      <SettingRow label="Download retries" hint="Retry on ffmpeg crash or network glitch">
        <NumInput value={val('download_retries')} min={1} max={10} onChange={v => set('download_retries', v)} />
      </SettingRow>

      <SettingRow label="Download timeout (s)" hint="Max seconds per job before it's killed">
        <NumInput value={val('download_timeout')} min={60} onChange={v => set('download_timeout', v)} />
      </SettingRow>

      <div className="py-1.5 space-y-1.5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm">Max file size</p>
            <p className="text-xs text-muted-foreground">Telegram bot limit is 2 GB</p>
          </div>
          <span className="text-sm font-medium tabular-nums">{val('max_file_size_gb')} GB</span>
        </div>
        <Slider
          min={0.5} max={2} step={0.5}
          value={[val('max_file_size_gb')]}
          onValueChange={([v]) => set('max_file_size_gb', v)}
        />
      </div>

      <SettingRow label="Rate limit / minute">
        <NumInput value={val('rate_limit_per_minute')} min={1} onChange={v => set('rate_limit_per_minute', v)} />
      </SettingRow>

      <SettingRow label="Rate limit / hour">
        <NumInput value={val('rate_limit_per_hour')} min={1} onChange={v => set('rate_limit_per_hour', v)} />
      </SettingRow>

      <SettingRow label="Rate limit / day">
        <NumInput value={val('rate_limit_per_day')} min={1} onChange={v => set('rate_limit_per_day', v)} />
      </SettingRow>

      <SettingRow label="Max playlist items">
        <NumInput value={val('max_playlist_count')} min={1} max={500} onChange={v => set('max_playlist_count', v)} />
      </SettingRow>

      {isDirty && (
        <div className="pt-2">
          <Button className="w-full h-8 text-xs" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      )}
    </div>
  )
}
