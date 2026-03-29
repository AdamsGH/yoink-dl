import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle, CookieIcon, ExternalLink, RefreshCw, ShieldCheck, Trash2, Upload } from 'lucide-react'

import { apiClient } from '@core/lib/api-client'
import { formatDate } from '@core/lib/utils'
import { CookieStatusBadge } from '@core/components/app/StatusBadge'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Input } from '@core/components/ui/input'
import { Item, ItemActions, ItemContent, ItemDescription, ItemMedia, ItemTitle } from '@core/components/ui/item'
import { Label } from '@core/components/ui/label'
import { Skeleton } from '@core/components/ui/skeleton'
import { Switch } from '@core/components/ui/switch'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@core/components/ui/tooltip'
import { toast } from '@core/components/ui/toast'

interface CookieEntry {
  id: number
  domain: string
  is_valid: boolean
  is_pool: boolean
  updated_at: string
  validated_at?: string | null
  inherited?: boolean
}

import { CookieFavicon } from '@dl/components/CookieFavicon'
import { parseDomainFromNetscape } from '@dl/lib/cookie-utils'

export default function CookiesPage() {
  const { t } = useTranslation()
  const [cookies, setCookies] = useState<CookieEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [validating, setValidating] = useState<number | null>(null)
  const [usePool, setUsePool] = useState<boolean | null>(null)
  const [hasPoolAccess, setHasPoolAccess] = useState(false)
  const [poolSaving, setPoolSaving] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadContent, setUploadContent] = useState('')
  const [uploadDomain, setUploadDomain] = useState('')
  const [uploading, setUploading] = useState(false)

  const load = () => {
    setLoading(true)
    apiClient.get<CookieEntry[]>('/dl/cookies')
      .then(r => setCookies(r.data))
      .catch(() => toast.error(t('cookies.load_error', { defaultValue: 'Failed to load cookies' })))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    apiClient.get<{ use_pool_cookies: boolean; has_pool_access: boolean }>('/dl/settings')
      .then(r => {
        setHasPoolAccess(r.data.has_pool_access === true)
        setUsePool(r.data.use_pool_cookies)
      })
      .catch(() => {})
  }, [])

  const togglePool = async (val: boolean) => {
    setPoolSaving(true)
    try {
      await apiClient.patch('/dl/settings', { use_pool_cookies: val })
      setUsePool(val)
    } catch {
      toast.error(t('common.error', { defaultValue: 'Error' }))
    } finally {
      setPoolSaving(false)
    }
  }

  const remove = async (id: number, domain: string) => {
    setDeleting(id)
    try {
      await apiClient.delete(`/dl/cookies/by-id/${id}`)
      toast.success(t('cookies.removed', { defaultValue: 'Removed cookies for {{domain}}', domain }))
      load()
    } catch {
      toast.error(t('cookies.delete_error', { defaultValue: 'Failed to delete' }))
    } finally {
      setDeleting(null)
    }
  }

  const validate = async (id: number) => {
    setValidating(id)
    try {
      const r = await apiClient.post<CookieEntry>(`/dl/cookies/${id}/validate`, {})
      setCookies(prev => prev.map(c => c.id === id ? { ...c, is_valid: r.data.is_valid } : c))
      toast.success(r.data.is_valid
        ? t('cookies.valid_ok', { defaultValue: 'Cookie is valid' })
        : t('cookies.valid_fail', { defaultValue: 'Cookie appears invalid' })
      )
    } catch {
      toast.error(t('cookies.validate_error', { defaultValue: 'Validation failed' }))
    } finally {
      setValidating(null)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadFile(file)
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      setUploadContent(text)
      const domain = parseDomainFromNetscape(text)
      if (domain) setUploadDomain(domain)
    }
    reader.readAsText(file)
  }

  const handleUpload = async () => {
    if (!uploadContent) { toast.error(t('cookies.select_file', { defaultValue: 'Select a file first' })); return }
    if (!uploadDomain) { toast.error(t('cookies.domain_required', { defaultValue: 'Domain is required' })); return }
    setUploading(true)
    try {
      await apiClient.post('/dl/cookies/upload', { domain: uploadDomain, content: uploadContent })
      toast.success(t('cookies.uploaded', { defaultValue: 'Cookie uploaded for {{domain}}', domain: uploadDomain }))
      setUploadFile(null)
      setUploadContent('')
      setUploadDomain('')
      if (fileInputRef.current) fileInputRef.current.value = ''
      load()
    } catch {
      toast.error(t('cookies.upload_error', { defaultValue: 'Upload failed' }))
    } finally {
      setUploading(false)
    }
  }

  const own = cookies.filter(c => !c.inherited)
  const inherited = cookies.filter(c => c.inherited)

  return (
    <TooltipProvider delayDuration={300}>
      <div className="space-y-4">
        {/* Stored list */}
        <Card>
          <CardHeader className="px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <CookieIcon className="h-4 w-4 text-muted-foreground" />
                {loading
                  ? t('cookies.stored', { defaultValue: 'Cookies' })
                  : t('cookies.count_other', { count: own.length, defaultValue: `${own.length} cookies` })}
              </CardTitle>
              <div className="flex items-center gap-2">
                {hasPoolAccess && usePool !== null && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="flex items-center gap-1.5">
                        <ShieldCheck className={`h-3.5 w-3.5 ${usePool ? 'text-primary' : 'text-muted-foreground'}`} />
                        <Switch
                          checked={usePool}
                          onCheckedChange={togglePool}
                          disabled={poolSaving}
                          className="scale-75 origin-right"
                        />
                      </div>
                    </TooltipTrigger>
                    <TooltipContent>
                      {usePool
                        ? t('settings.use_pool_cookies', { defaultValue: 'Shared pool: on' })
                        : t('cookies.pool_off', { defaultValue: 'Shared pool: off' })}
                    </TooltipContent>
                  </Tooltip>
                )}
                <Button
                  size="sm"
                  className="h-7 px-2.5 text-xs"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="mr-1.5 h-3 w-3" />
                  {t('cookies.upload', { defaultValue: 'Upload' })}
                </Button>
              </div>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            {loading ? (
              <div className="divide-y divide-border px-3 py-1">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-3 py-2.5">
                    <Skeleton className="size-8 rounded-md shrink-0" />
                    <div className="flex-1 space-y-1.5">
                      <Skeleton className="h-3.5 w-32" />
                      <Skeleton className="h-3 w-20" />
                    </div>
                    <Skeleton className="h-5 w-14" />
                  </div>
                ))}
              </div>
            ) : own.length === 0 && inherited.length === 0 ? (
              <div className="flex justify-center py-12 text-muted-foreground text-sm">
                {t('cookies.empty', { defaultValue: 'No cookies stored yet' })}
              </div>
            ) : (
              <div className="divide-y divide-border px-3 py-1">
                {own.map((c) => (
                  <Item key={c.id} size="sm" className="py-2.5 rounded-none border-0">
                    <ItemMedia variant="icon" className="size-8 rounded-md bg-muted text-muted-foreground">
                      <CookieFavicon domain={c.domain} />
                    </ItemMedia>
                    <ItemContent>
                      <ItemTitle>{c.domain}</ItemTitle>
                      <ItemDescription>
                        {t('cookies.updated', { defaultValue: 'Updated' })} {formatDate(c.updated_at)}
                      </ItemDescription>
                    </ItemContent>
                    <ItemActions>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span><CookieStatusBadge valid={c.is_valid} /></span>
                        </TooltipTrigger>
                        <TooltipContent>
                          {c.validated_at
                            ? `${t('cookies.validated_col', { defaultValue: 'Validated' })}: ${formatDate(c.validated_at)}`
                            : t('cookies.never', { defaultValue: 'Never validated' })}
                        </TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon" disabled={validating === c.id} onClick={() => validate(c.id)}>
                            {validating === c.id
                              ? <RefreshCw className="h-4 w-4 animate-spin" />
                              : <CheckCircle className="h-4 w-4 text-muted-foreground" />}
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>{t('cookies.validate_btn', { defaultValue: 'Re-validate' })}</TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost" size="icon"
                            className="text-destructive hover:text-destructive"
                            disabled={deleting === c.id}
                            onClick={() => remove(c.id, c.domain)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>{t('common.delete', { defaultValue: 'Delete' })}</TooltipContent>
                      </Tooltip>
                    </ItemActions>
                  </Item>
                ))}

                {inherited.length > 0 && (
                  <>
                    {own.length > 0 && (
                      <div className="flex items-center gap-1.5 py-2 px-1">
                        <ShieldCheck className={`h-3 w-3 shrink-0 ${usePool ? 'text-primary' : 'text-muted-foreground'}`} />
                        <span className="text-xs text-muted-foreground">
                          {t('cookies.pool_label', { defaultValue: 'Cookie pool' })}
                        </span>
                      </div>
                    )}
                    {inherited.map((c) => (
                      <Item key={c.id} size="sm" className={`py-2.5 rounded-none border-0 transition-opacity ${usePool ? 'opacity-80' : 'opacity-35'}`}>
                        <ItemMedia variant="icon" className="size-8 rounded-md bg-muted text-muted-foreground">
                          <CookieFavicon domain={c.domain} />
                        </ItemMedia>
                        <ItemContent>
                          <ItemTitle className="text-muted-foreground">{c.domain}</ItemTitle>
                          <ItemDescription className="flex items-center gap-1">
                            <ShieldCheck className={`h-3 w-3 ${usePool ? 'text-primary' : 'text-muted-foreground'}`} />
                            {usePool
                              ? t('cookies.pool_active', { defaultValue: 'In rotation' })
                              : t('cookies.pool_inactive', { defaultValue: 'Pool disabled' })}
                          </ItemDescription>
                        </ItemContent>
                        <ItemActions>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span><CookieStatusBadge valid={c.is_valid} /></span>
                            </TooltipTrigger>
                            <TooltipContent>
                              {c.validated_at
                                ? `${t('cookies.validated_col', { defaultValue: 'Validated' })}: ${formatDate(c.validated_at)}`
                                : t('cookies.never', { defaultValue: 'Never validated' })}
                            </TooltipContent>
                          </Tooltip>
                        </ItemActions>
                      </Item>
                    ))}
                  </>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Hidden file input - triggered by Upload button */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,text/plain"
          className="hidden"
          onChange={handleFileChange}
        />

        {/* Upload form - shown after file selected */}
        {uploadFile && (
          <Card>
            <CardHeader className="px-4 py-3">
              <CardTitle className="text-base">{uploadFile.name}</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="upload-domain">{t('cookies.domain_label', { defaultValue: 'Domain' })}</Label>
                <Input
                  id="upload-domain"
                  placeholder="youtube.com"
                  value={uploadDomain}
                  onChange={(e) => setUploadDomain(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  {t('cookies.domain_auto', { defaultValue: 'Auto-detected from file. Edit if incorrect.' })}
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => { setUploadFile(null); setUploadContent(''); setUploadDomain(''); if (fileInputRef.current) fileInputRef.current.value = '' }}>
                  {t('common.cancel', { defaultValue: 'Cancel' })}
                </Button>
                <Button size="sm" onClick={handleUpload} disabled={uploading || !uploadDomain}>
                  {uploading ? t('common.loading') : t('cookies.upload_btn', { defaultValue: 'Upload' })}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Get cookies.txt extension */}
        <Card>
          <CardHeader className="px-4 py-3">
            <CardTitle className="text-base">
              {t('cookies.extension_title', { defaultValue: 'Get cookies via browser extension' })}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm px-4 pb-4">
            <p className="text-muted-foreground">
              {t('cookies.extension_hint', {
                defaultValue: 'The easiest way to export cookies from any site is with the "Get cookies.txt LOCALLY" extension.',
              })}
            </p>

            <a
              href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium hover:bg-muted transition-colors"
            >
              <ExternalLink className="h-4 w-4 shrink-0" />
              {t('cookies.extension_link', { defaultValue: 'Get cookies.txt LOCALLY' })}
            </a>

            <div className="space-y-3 pt-1">
              {[
                {
                  n: 1,
                  title: t('cookies.step1_title', { defaultValue: 'Install the extension' }),
                  desc: t('cookies.step1_desc', { defaultValue: 'Available for Chrome, Chromium, and Edge.' }),
                },
                {
                  n: 2,
                  title: t('cookies.step2_title', { defaultValue: 'Log in to the site' }),
                  desc: t('cookies.step2_desc', { defaultValue: 'Open the site (YouTube, Instagram, etc.) and log in.' }),
                },
                {
                  n: 3,
                  title: t('cookies.step3_title', { defaultValue: 'Export cookies' }),
                  desc: t('cookies.step3_desc', { defaultValue: 'Click the extension icon and press "Export" - you\'ll get a cookies.txt file.' }),
                },
                {
                  n: 4,
                  title: t('cookies.step4_title', { defaultValue: 'Upload the file' }),
                  desc: t('cookies.step4_desc', { defaultValue: 'Tap "Upload" above and select the file.' }),
                },
              ].map(({ n, title, desc }) => (
                <div key={n} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">
                    {n}
                  </span>
                  <div>
                    <p className="font-medium">{title}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Auto-sync extension */}
        <Card>
          <CardHeader className="px-4 py-3">
            <CardTitle className="text-base">
              {t('cookies.sync_title', { defaultValue: 'Auto-sync via Yoink Cookie Sync' })}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm px-4 pb-4">
            <p className="text-muted-foreground">
              {t('cookies.sync_hint', { defaultValue: 'For automatic sync, use the Yoink Cookie Sync browser extension.' })}
            </p>
            <div className="space-y-3">
              {[
                {
                  n: 1,
                  title: t('cookies.sync_step1_title', { defaultValue: 'Install the Yoink Cookie Sync extension' }),
                  desc: t('cookies.sync_step1_desc', { defaultValue: 'Available for Chrome, Chromium, Edge. Ask your admin for the .zip file.' }),
                },
                {
                  n: 2,
                  title: t('cookies.sync_step2_title', { defaultValue: 'Log in to your sites' }),
                  desc: t('cookies.sync_step2_desc', { defaultValue: 'Instagram, YouTube, X, TikTok - in the same browser.' }),
                },
                {
                  n: 3,
                  title: t('cookies.sync_step3_title', { defaultValue: 'Get a token from the bot' }),
                  desc: (
                    <>
                      {t('cookies.sync_step3_desc', { defaultValue: 'Send ' })}
                      <code className="bg-muted px-1 rounded">/cookie token</code>
                      {t('cookies.sync_step3_desc2', { defaultValue: ' to the bot in Telegram.' })}
                    </>
                  ),
                },
                {
                  n: 4,
                  title: t('cookies.sync_step4_title', { defaultValue: 'Paste token in the extension' }),
                  desc: t('cookies.sync_step4_desc', { defaultValue: 'Token is valid for 10 minutes and single-use. Repeat when cookies expire.' }),
                },
              ].map(({ n, title, desc }) => (
                <div key={n} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">
                    {n}
                  </span>
                  <div>
                    <p className="font-medium">{title}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  )
}
