import { useEffect, useState } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useGetIdentity } from '@refinedev/core'
import { Coffee, Ghost, Moon, ShieldCheck, Sun } from 'lucide-react'

import { apiClient } from '@core/lib/api-client'
import { cn } from '@core/lib/utils'
import { setLanguage, SUPPORTED_LANGUAGES, type SupportedLanguage } from '@core/lib/i18n'
import { SettingRow } from '@core/components/app/SettingRow'
import type { UserSettings } from '@dl/types'
import type { User } from '@core/types/api'
import { Button } from '@core/components/ui/button'
import { Input } from '@core/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Label } from '@core/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@core/components/ui/select'
import { Switch } from '@core/components/ui/switch'
import { Skeleton } from '@core/components/ui/skeleton'
import { toast } from '@core/components/ui/toast'
import { useTelegram, type CatppuccinFlavor } from '@core/layout/TelegramProvider'

type FormValues = Omit<UserSettings, 'user_id' | 'args_json' | 'theme' | 'language' | 'updated_at'>

const THEME_OPTIONS: { value: CatppuccinFlavor; label: string; icon: React.ReactNode }[] = [
  { value: 'latte',     label: 'Latte',     icon: <Sun className="h-3.5 w-3.5" /> },
  { value: 'frappe',    label: 'Frappé',    icon: <Coffee className="h-3.5 w-3.5" /> },
  { value: 'macchiato', label: 'Macchiato', icon: <Moon className="h-3.5 w-3.5" /> },
  { value: 'mocha',     label: 'Mocha',     icon: <Ghost className="h-3.5 w-3.5" /> },
]

const QUALITY_OPTIONS = [
  { value: 'best',  label: 'Best available' },
  { value: 'ask',   label: 'Ask every time' },
  { value: '2160',  label: '4K (2160p)' },
  { value: '1440',  label: '1440p' },
  { value: '1080',  label: '1080p' },
  { value: '720',   label: '720p' },
  { value: '480',   label: '480p' },
  { value: '360',   label: '360p' },
]

const CODEC_OPTIONS = [
  { value: 'avc1', label: 'H.264 (avc1)' },
  { value: 'av01', label: 'AV1 (av01)' },
  { value: 'vp9',  label: 'VP9' },
  { value: 'any',  label: 'Any' },
]

const CONTAINER_OPTIONS = [
  { value: 'mp4',  label: 'MP4' },
  { value: 'mkv',  label: 'MKV' },
  { value: 'webm', label: 'WebM' },
]

const SPLIT_OPTIONS = [
  { value: String(500 * 1024 * 1024),  label: '500 MB' },
  { value: String(1000 * 1024 * 1024), label: '1 GB' },
  { value: String(1500 * 1024 * 1024), label: '1.5 GB' },
  { value: '2043000000',               label: '2 GB (max)' },
]

const KEYBOARD_OPTIONS = [
  { value: 'OFF',  label: 'Off' },
  { value: '1x3',  label: '1×3' },
  { value: '2x3',  label: '2×3 (default)' },
  { value: 'FULL', label: 'Full width' },
]

const SUBS_LANG_OPTIONS = ['en', 'ru', 'de', 'fr', 'es', 'it', 'pt', 'ja', 'zh', 'ko']


function ControlledSelect({
  name, options, control, className,
}: {
  name: keyof FormValues
  options: { value: string; label: string }[]
  control: ReturnType<typeof useForm<FormValues>>['control']
  className?: string
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field }) => (
        <Select
          value={String(field.value ?? '')}
          onValueChange={(v) => field.onChange(name === 'split_size' ? Number(v) : v)}
        >
          <SelectTrigger className={cn('h-8 text-xs', className ?? 'w-36')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.value} value={o.value} className="text-xs">{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    />
  )
}

function ControlledSwitch({ name, label, hint, control }: {
  name: keyof FormValues
  label: string
  hint?: string
  control: ReturnType<typeof useForm<FormValues>>['control']
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field }) => (
        <SettingRow label={label} hint={hint}>
          <Switch checked={!!field.value} onCheckedChange={field.onChange} />
        </SettingRow>
      )}
    />
  )
}

function SettingsSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3, 4].map((i) => (
        <Card key={i}>
          <CardHeader className="px-4 py-3"><Skeleton className="h-4 w-28" /></CardHeader>
          <CardContent className="px-4 pb-4 space-y-3">
            {[1, 2, 3].map((j) => (
              <div key={j} className="flex items-center justify-between py-2.5 border-b border-border last:border-0">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-8 w-24" />
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [currentLang, setCurrentLang] = useState<SupportedLanguage>('en')
  const [langSaving, setLangSaving] = useState(false)
  const { t } = useTranslation()
  const { flavor, setFlavor } = useTelegram()
  const { data: identity } = useGetIdentity<User>()
  const { handleSubmit, reset, watch, control, formState: { isSubmitting, isDirty } } = useForm<FormValues>()

  const subsEnabled = watch('subs_enabled')
  const proxyEnabled = watch('proxy_enabled')

  // Only show use_pool_cookies if user has pool access (admin/owner or shared_cookies perm)
  // We detect this by checking if the setting comes back from the API
  const [hasPoolAccess, setHasPoolAccess] = useState(false)

  useEffect(() => {
    const dlPromise = apiClient
      .get<UserSettings>('/dl/settings')
      .then((res) => {
        const { user_id: _uid, args_json: _args, theme: _theme, language: _lang, updated_at: _ua, ...rest } = res.data
        reset(rest)
        setHasPoolAccess(res.data.has_pool_access === true)
      })
      .catch(() => toast.error(t('settings.save_error')))

    const corePromise = apiClient
      .get<{ language: string }>('/settings')
      .then((res) => {
        const lang = res.data.language
        if (SUPPORTED_LANGUAGES.includes(lang as SupportedLanguage)) {
          setCurrentLang(lang as SupportedLanguage)
        }
      })
      .catch(() => {})

    Promise.all([dlPromise, corePromise]).finally(() => setLoading(false))
  }, [reset, t, identity?.role])

  const onSubmit = async (values: FormValues) => {
    try {
      await apiClient.patch('/dl/settings', values)
      toast.success(t('settings.saved'))
      reset(values)
    } catch {
      toast.error(t('settings.save_error'))
    }
  }

  const handleLangChange = async (lang: SupportedLanguage) => {
    if (lang === currentLang) return
    setLangSaving(true)
    try {
      await apiClient.patch('/settings', { language: lang })
      setCurrentLang(lang)
      setLanguage(lang)
    } catch {
      toast.error(t('settings.save_error'))
    } finally {
      setLangSaving(false)
    }
  }

  if (loading) return <SettingsSkeleton />

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">

      {/* Video quality */}
      <Card>
        <CardHeader className="px-4 py-3">
          <CardTitle className="text-base">{t('settings.video_quality')}</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-1">
          <SettingRow label={t('settings.resolution_label')}>
            <ControlledSelect name="quality" options={QUALITY_OPTIONS} control={control} />
          </SettingRow>
          <SettingRow label={t('settings.codec_label')}>
            <ControlledSelect name="codec" options={CODEC_OPTIONS} control={control} />
          </SettingRow>
          <SettingRow label={t('settings.container_label')}>
            <ControlledSelect name="container" options={CONTAINER_OPTIONS} control={control} />
          </SettingRow>
        </CardContent>
      </Card>

      {/* Delivery */}
      <Card>
        <CardHeader className="px-4 py-3">
          <CardTitle className="text-base">{t('settings.delivery')}</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-1">
          <SettingRow label={t('settings.split_label')}>
            <ControlledSelect name="split_size" options={SPLIT_OPTIONS} control={control} />
          </SettingRow>
          <SettingRow label={t('settings.keyboard_label')}>
            <ControlledSelect name="keyboard" options={KEYBOARD_OPTIONS} control={control} />
          </SettingRow>
          <ControlledSwitch name="send_as_file" label={t('settings.send_as_file')} hint={t('settings.send_as_file_hint')} control={control} />
          <ControlledSwitch name="nsfw_blur" label={t('settings.nsfw_blur')} hint={t('settings.nsfw_blur_hint')} control={control} />
          <ControlledSwitch name="mediainfo" label={t('settings.mediainfo')} hint={t('settings.mediainfo_hint')} control={control} />
          <ControlledSwitch name="gallery_zip" label={t('settings.gallery_zip')} hint={t('settings.gallery_zip_hint')} control={control} />
        </CardContent>
      </Card>

      {/* Cookies */}
      {hasPoolAccess && (
        <Card>
          <CardHeader className="px-4 py-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="h-4 w-4 text-muted-foreground" />
              {t('settings.cookies', { defaultValue: 'Cookies' })}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-1">
            <ControlledSwitch
              name="use_pool_cookies"
              label={t('settings.use_pool_cookies', { defaultValue: 'Use shared cookie pool' })}
              hint={t('settings.use_pool_cookies_hint', { defaultValue: 'Include shared accounts in rotation alongside your personal cookies' })}
              control={control}
            />
          </CardContent>
        </Card>
      )}

      {/* Subtitles */}
      <Card>
        <CardHeader className="px-4 py-3">
          <CardTitle className="text-base">{t('settings.subtitles')}</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-1">
          <ControlledSwitch name="subs_enabled" label={t('settings.subs_enabled')} hint={t('settings.subs_enabled_hint')} control={control} />
          {subsEnabled && (
            <>
              <SettingRow label={t('settings.subs_lang_label')}>
                <ControlledSelect
                  name="subs_lang"
                  options={SUBS_LANG_OPTIONS.map((c) => ({ value: c, label: c }))}
                  control={control}
                />
              </SettingRow>
              <ControlledSwitch name="subs_auto" label={t('settings.subs_auto')} hint={t('settings.subs_auto_hint')} control={control} />
              <ControlledSwitch name="subs_always_ask" label={t('settings.subs_ask')} control={control} />
            </>
          )}
        </CardContent>
      </Card>

      {/* Network */}
      <Card>
        <CardHeader className="px-4 py-3">
          <CardTitle className="text-base">{t('settings.network')}</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-1">
          <ControlledSwitch name="proxy_enabled" label={t('settings.use_proxy')} hint={t('settings.use_proxy_hint')} control={control} />
          {proxyEnabled && (
            <div className="py-3 space-y-1.5">
              <Label htmlFor="proxy_url" className="text-xs">Proxy URL</Label>
              <Controller
                name="proxy_url"
                control={control}
                render={({ field }) => (
                  <Input
                    id="proxy_url"
                    className="h-8 text-xs"
                    placeholder="socks5://user:pass@host:port"
                    value={field.value ?? ''}
                    onChange={(e) => field.onChange(e.target.value || null)}
                  />
                )}
              />
              <p className="text-xs text-muted-foreground">{t('settings.proxy_url_hint')}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Interface */}
      <Card>
        <CardHeader className="px-4 py-3">
          <CardTitle className="text-base">{t('settings.interface')}</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <div className="py-2.5 space-y-2">
            <p className="text-sm">{t('settings.theme_label')}</p>
            <div className="grid grid-cols-4 gap-2">
              {THEME_OPTIONS.map((th) => (
                <button
                  key={th.value}
                  type="button"
                  onClick={() => setFlavor(th.value)}
                  className={cn(
                    'flex flex-col items-center gap-1.5 rounded-lg border px-2 py-2.5 text-xs font-medium transition-all',
                    flavor === th.value
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-muted/30 text-muted-foreground hover:border-primary/50 hover:text-foreground'
                  )}
                >
                  {th.icon}
                  {th.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">{t('settings.theme_hint')}</p>
          </div>


          <SettingRow label={t('settings.language_label')}>
            <Select
              value={currentLang}
              onValueChange={(v) => handleLangChange(v as SupportedLanguage)}
              disabled={langSaving}
            >
              <SelectTrigger className="h-8 text-xs w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SUPPORTED_LANGUAGES.map((lang) => (
                  <SelectItem key={lang} value={lang} className="text-xs">
                    {lang === 'en' ? 'English' : 'Русский'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingRow>
        </CardContent>
      </Card>

      <div className={cn(
        'flex justify-end pb-4 transition-opacity',
        isDirty ? 'opacity-100' : 'pointer-events-none opacity-0',
      )}>
        <Button type="submit" disabled={isSubmitting || !isDirty} className="w-full">
          {isSubmitting ? t('common.loading') : t('common.save')}
        </Button>
      </div>
    </form>
  )
}
