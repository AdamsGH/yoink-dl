import { useEffect, useState } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Coffee, Ghost, Moon, Sun } from 'lucide-react'

import { apiClient } from '@core/lib/api-client'
import { cn } from '@core/lib/utils'
import { setLanguage, SUPPORTED_LANGUAGES, type SupportedLanguage } from '@core/lib/i18n'
import type { UserSettings } from '@dl/types'
import { Button } from '@core/components/ui/button'
import { Input } from '@core/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Label } from '@core/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@core/components/ui/select'
import { Switch } from '@core/components/ui/switch'
import { toast } from '@core/components/ui/toast'
import { useTelegram, type CatppuccinFlavor } from '@core/layout/TelegramProvider'

// language and theme are managed via core /settings; updated_at is read-only
type FormValues = Omit<UserSettings, 'user_id' | 'args_json' | 'theme' | 'language' | 'updated_at'>

const THEME_OPTIONS: { value: CatppuccinFlavor; label: string; icon: React.ReactNode; dark: boolean }[] = [
  { value: 'latte',     label: 'Latte',     icon: <Sun className="h-3.5 w-3.5" />,    dark: false },
  { value: 'frappe',    label: 'Frappé',    icon: <Coffee className="h-3.5 w-3.5" />,  dark: true  },
  { value: 'macchiato', label: 'Macchiato', icon: <Moon className="h-3.5 w-3.5" />,   dark: true  },
  { value: 'mocha',     label: 'Mocha',     icon: <Ghost className="h-3.5 w-3.5" />,  dark: true  },
]

const QUALITY_OPTIONS = [
  { value: 'best',  label: 'Best available' },
  { value: 'ask',   label: 'Ask every time' },
  { value: '4320',  label: '8K (4320p)' },
  { value: '2160',  label: '4K (2160p)' },
  { value: '1440',  label: '1440p' },
  { value: '1080',  label: '1080p' },
  { value: '720',   label: '720p' },
  { value: '480',   label: '480p' },
  { value: '360',   label: '360p' },
]

const CODEC_OPTIONS = [
  { value: 'avc1', label: 'H.264 (avc1)  - most compatible' },
  { value: 'av01', label: 'AV1 (av01)  - best compression' },
  { value: 'vp9',  label: 'VP9  - good compression' },
  { value: 'any',  label: 'Any  - let yt-dlp choose' },
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
  { value: String(2000 * 1024 * 1024), label: '2 GB (Telegram limit)' },
]

const KEYBOARD_OPTIONS = [
  { value: 'OFF',  label: 'Off  - no reply keyboard' },
  { value: '1x3',  label: '1×3  - single column' },
  { value: '2x3',  label: '2×3  - grid (default)' },
  { value: 'FULL', label: 'Full width buttons' },
]

const SUBS_LANG_OPTIONS = ['en', 'ru', 'de', 'fr', 'es', 'it', 'pt', 'ja', 'zh', 'ko']

interface FieldRowProps {
  label: string
  hint?: string
  children: React.ReactNode
}

function FieldRow({ label, hint, children }: FieldRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-0.5">
      <div className="min-w-0">
        <p className="text-sm font-medium">{label}</p>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

interface ControlledSelectProps {
  name: keyof FormValues
  options: { value: string; label: string }[]
  control: ReturnType<typeof useForm<FormValues>>['control']
}

function ControlledSelect({ name, options, control }: ControlledSelectProps) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field }) => (
        <Select
          value={String(field.value ?? '')}
          onValueChange={(v: string) => field.onChange(name === 'split_size' ? Number(v) : v)}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    />
  )
}

interface ControlledSwitchProps {
  name: keyof FormValues
  label: string
  hint?: string
  control: ReturnType<typeof useForm<FormValues>>['control']
}

function ControlledSwitch({ name, label, hint, control }: ControlledSwitchProps) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field }) => (
        <FieldRow label={label} hint={hint}>
          <Switch
            checked={!!field.value}
            onCheckedChange={field.onChange}
          />
        </FieldRow>
      )}
    />
  )
}

interface SectionProps {
  title: string
  children: React.ReactNode
}

function Section({ title, children }: SectionProps) {
  return (
    <Card>
      <CardHeader className="pb-3 pt-4">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 pb-4">
        {children}
      </CardContent>
    </Card>
  )
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [currentLang, setCurrentLang] = useState<SupportedLanguage>('en')
  const [langSaving, setLangSaving] = useState(false)
  const { t } = useTranslation()
  const { flavor, setFlavor } = useTelegram()
  const { handleSubmit, reset, watch, control, formState: { isSubmitting, isDirty } } =
    useForm<FormValues>()

  const subsEnabled = watch('subs_enabled')
  const proxyEnabled = watch('proxy_enabled')

  useEffect(() => {
    // Load dl-specific settings and core language in parallel
    const dlPromise = apiClient
      .get<UserSettings>('/dl/settings')
      .then((res) => {
        const { user_id: _uid, args_json: _args, theme: _theme, language: _lang, updated_at: _ua, ...rest } = res.data
        reset(rest)
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
      .catch(() => {/* non-critical */})

    Promise.all([dlPromise, corePromise]).finally(() => setLoading(false))
  }, [reset, t])

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

  if (loading) {
    return <div className="flex justify-center py-24 text-muted-foreground">{t('common.loading')}</div>
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
      <Section title={t('settings.video_quality')}>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label>{t('settings.resolution_label')}</Label>
            <ControlledSelect name="quality" options={QUALITY_OPTIONS} control={control} />
          </div>
          <div className="space-y-1.5">
            <Label>{t('settings.codec_label')}</Label>
            <ControlledSelect name="codec" options={CODEC_OPTIONS} control={control} />
          </div>
          <div className="space-y-1.5">
            <Label>{t('settings.container_label')}</Label>
            <ControlledSelect name="container" options={CONTAINER_OPTIONS} control={control} />
          </div>
        </div>
      </Section>

      <Section title={t('settings.delivery')}>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>{t('settings.split_label')}</Label>
            <ControlledSelect name="split_size" options={SPLIT_OPTIONS} control={control} />
          </div>
          <div className="space-y-1.5">
            <Label>{t('settings.keyboard_label')}</Label>
            <ControlledSelect name="keyboard" options={KEYBOARD_OPTIONS} control={control} />
          </div>
        </div>

        <div className="space-y-3 border-t pt-3">
          <ControlledSwitch name="send_as_file" label={t('settings.send_as_file')} hint={t('settings.send_as_file_hint')} control={control} />
          <ControlledSwitch name="nsfw_blur" label={t('settings.nsfw_blur')} hint={t('settings.nsfw_blur_hint')} control={control} />
          <ControlledSwitch name="mediainfo" label={t('settings.mediainfo')} hint={t('settings.mediainfo_hint')} control={control} />
          <ControlledSwitch name="gallery_zip" label={t('settings.gallery_zip')} hint={t('settings.gallery_zip_hint')} control={control} />
        </div>
      </Section>

      <Section title={t('settings.subtitles')}>
        <ControlledSwitch name="subs_enabled" label={t('settings.subs_enabled')} hint={t('settings.subs_enabled_hint')} control={control} />

        {subsEnabled && (
          <div className="space-y-3 border-t pt-3">
            <div className="space-y-1.5">
              <Label>{t('settings.subs_lang_label')}</Label>
              <ControlledSelect name="subs_lang" options={SUBS_LANG_OPTIONS.map((c) => ({ value: c, label: c }))} control={control} />
            </div>
            <ControlledSwitch name="subs_auto" label={t('settings.subs_auto')} hint={t('settings.subs_auto_hint')} control={control} />
            <ControlledSwitch name="subs_always_ask" label={t('settings.subs_ask')} control={control} />
          </div>
        )}
      </Section>

      <Section title={t('settings.network')}>
        <ControlledSwitch
          name="proxy_enabled"
          label={t('settings.use_proxy')}
          hint={t('settings.use_proxy_hint')}
          control={control}
        />
        {proxyEnabled && (
          <div className="space-y-1.5 border-t pt-3">
            <Label htmlFor="proxy_url">Proxy URL</Label>
            <Controller
              name="proxy_url"
              control={control}
              render={({ field }) => (
                <Input
                  id="proxy_url"
                  placeholder="socks5://user:pass@host:port or http://host:port"
                  value={field.value ?? ''}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => field.onChange(e.target.value || null)}
                />
              )}
            />
            <p className="text-xs text-muted-foreground">
              {t('settings.proxy_url_hint')}
            </p>
          </div>
        )}
      </Section>

      <Section title={t('settings.interface')}>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label>{t('settings.theme_label')}</Label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {THEME_OPTIONS.map((th) => (
                <Button
                  key={th.value}
                  variant="outline"
                  type="button"
                  onClick={() => setFlavor(th.value)}
                  className={cn(
                    'flex items-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium transition-all h-auto',
                    flavor === th.value
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-muted/30 text-muted-foreground hover:border-primary/50 hover:text-foreground'
                  )}
                >
                  {th.icon}
                  {th.label}
                </Button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {t('settings.theme_hint')}
            </p>
          </div>

          <div className="space-y-1.5 border-t pt-3">
            <Label>{t('settings.language_label')}</Label>
            <Select
              value={currentLang}
              onValueChange={(v) => handleLangChange(v as SupportedLanguage)}
              disabled={langSaving}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SUPPORTED_LANGUAGES.map((lang) => (
                  <SelectItem key={lang} value={lang}>
                    {lang === 'en' ? 'English' : 'Русский'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {t('settings.language_hint')}
            </p>
          </div>
        </div>
      </Section>

      <div className={cn(
        'flex justify-end border-t pt-4 transition-opacity',
        isDirty ? 'opacity-100' : 'pointer-events-none opacity-0',
      )}>
        <Button type="submit" disabled={isSubmitting || !isDirty} className="w-full sm:w-auto">
          {isSubmitting ? t('common.loading') : t('common.save')}
        </Button>
      </div>
    </form>
  )
}
