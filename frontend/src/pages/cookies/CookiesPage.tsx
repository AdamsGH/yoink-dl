import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle, ChevronDown, Copy, CookieIcon, ExternalLink, Key, LogIn, RefreshCw, ShieldCheck, Trash2, Upload } from 'lucide-react'

import { cookiesApi } from '@dl/api/cookies'
import type { CookieTokenResponse, YttvOAuthStartResponse } from '@dl/api/cookies'
import { dlSettingsApi } from '@dl/api/settings'
import { formatDate } from '@core/lib/utils'
import { Button, Card, CardContent, CardHeader, CardTitle, Collapsible, CollapsibleContent, CollapsibleTrigger, Input, Item, ItemActions, ItemContent, ItemDescription, ItemMedia, ItemTitle, Label, Skeleton, Switch, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@ui'
import { CookieStatusBadge } from '@app'
import { toast } from '@core/components/ui/toast'
import { CookieFavicon } from '@dl/components/CookieFavicon'
import { parseDomainFromNetscape } from '@dl/lib/cookie-utils'

interface CookieEntry {
  id: number
  domain: string
  is_valid: boolean
  is_pool: boolean
  is_oauth: boolean
  updated_at: string
  validated_at?: string | null
  inherited?: boolean
}

function StepList({ steps }: { steps: { n: number; title: string; desc: string }[] }) {
  return (
    <div className="space-y-3">
      {steps.map(({ n, title, desc }) => (
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
  )
}

function HelpCard({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card>
        <CollapsibleTrigger asChild>
          <CardHeader className="px-4 py-3 cursor-pointer select-none hover:bg-muted/30 transition-colors rounded-t-lg">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-base">{title}</CardTitle>
              <ChevronDown className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
            </div>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="space-y-4 text-sm px-4 pb-4">
            {children}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}

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

  const [pasteMode, setPasteMode] = useState(false)
  const [pasteContent, setPasteContent] = useState('')
  const [pasteDomain, setPasteDomain] = useState('')

  const [syncToken, setSyncToken] = useState<CookieTokenResponse | null>(null)
  const [tokenLoading, setTokenLoading] = useState(false)
  const [tokenCopied, setTokenCopied] = useState(false)

  const [yttvFlow, setYttvFlow] = useState<YttvOAuthStartResponse | null>(null)
  const [yttvLoading, setYttvLoading] = useState(false)
  const [yttvPolling, setYttvPolling] = useState(false)
  const [yttvCodeCopied, setYttvCodeCopied] = useState(false)
  const yttvPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopYttvPoll = () => {
    if (yttvPollRef.current) { clearInterval(yttvPollRef.current); yttvPollRef.current = null }
  }

  const startYttvFlow = async () => {
    stopYttvPoll()
    setYttvFlow(null)
    setYttvLoading(true)
    try {
      const r = await cookiesApi.yttvOAuthStart()
      setYttvFlow(r.data)
      setYttvPolling(true)
      yttvPollRef.current = setInterval(async () => {
        try {
          const poll = await cookiesApi.yttvOAuthPoll(r.data.session_id)
          if (poll.data.status === 'ok') {
            stopYttvPoll(); setYttvPolling(false); setYttvFlow(null)
            toast.success('YouTube authorized successfully')
            load()
          } else if (poll.data.status === 'expired' || poll.data.status === 'error') {
            stopYttvPoll(); setYttvPolling(false); setYttvFlow(null)
            toast.error(poll.data.status === 'expired' ? 'Authorization expired' : (poll.data.detail ?? 'Authorization failed'))
          }
        } catch { stopYttvPoll(); setYttvPolling(false) }
      }, (r.data.interval + 1) * 1000)
    } catch {
      toast.error('Failed to start authorization')
    } finally {
      setYttvLoading(false)
    }
  }

  const cancelYttvFlow = () => { stopYttvPoll(); setYttvPolling(false); setYttvFlow(null) }

  useEffect(() => () => stopYttvPoll(), [])

  const load = () => {
    setLoading(true)
    cookiesApi.listMine()
      .then(r => setCookies(r.data))
      .catch(() => toast.error(t('cookies.load_error', { defaultValue: 'Failed to load cookies' })))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    dlSettingsApi.getMine()
      .then(r => { setHasPoolAccess(r.data.has_pool_access === true); setUsePool(r.data.use_pool_cookies) })
      .catch(() => {})
  }, [])

  const togglePool = async (val: boolean) => {
    setPoolSaving(true)
    try {
      await dlSettingsApi.patchMine({ use_pool_cookies: val })
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
      await cookiesApi.deleteById(id)
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
      const r = await cookiesApi.validate(id)
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

  const generateToken = async () => {
    setTokenLoading(true); setSyncToken(null)
    try {
      const r = await cookiesApi.getToken()
      setSyncToken(r.data)
    } catch {
      toast.error(t('cookies.token_error', { defaultValue: 'Failed to generate token' }))
    } finally {
      setTokenLoading(false)
    }
  }

  const copyToken = async () => {
    if (!syncToken) return
    await navigator.clipboard.writeText(syncToken.token)
    setTokenCopied(true)
    setTimeout(() => setTokenCopied(false), 2000)
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
      await cookiesApi.uploadPersonal({ domain: uploadDomain, content: uploadContent })
      toast.success(t('cookies.uploaded', { defaultValue: 'Cookie uploaded for {{domain}}', domain: uploadDomain }))
      setUploadFile(null); setUploadContent(''); setUploadDomain('')
      if (fileInputRef.current) fileInputRef.current.value = ''
      load()
    } catch {
      toast.error(t('cookies.upload_error', { defaultValue: 'Upload failed' }))
    } finally {
      setUploading(false)
    }
  }

  const handlePasteContentChange = (text: string) => {
    setPasteContent(text)
    if (!pasteDomain) {
      const domain = parseDomainFromNetscape(text)
      if (domain) setPasteDomain(domain)
    }
  }

  const handlePasteUpload = async () => {
    if (!pasteContent) { toast.error(t('cookies.select_file', { defaultValue: 'Select a file first' })); return }
    if (!pasteDomain) { toast.error(t('cookies.domain_required', { defaultValue: 'Domain is required' })); return }
    setUploading(true)
    try {
      await cookiesApi.uploadPersonal({ domain: pasteDomain, content: pasteContent })
      toast.success(t('cookies.uploaded', { defaultValue: 'Cookie uploaded for {{domain}}', domain: pasteDomain }))
      setPasteContent(''); setPasteDomain(''); setPasteMode(false)
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

        {/* Stored cookies */}
        <Card>
          <CardHeader className="px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="flex min-w-0 items-center gap-2 text-base">
                <CookieIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="truncate">
                  {loading ? t('cookies.stored', { defaultValue: 'Cookies' }) : own.length}
                </span>
              </CardTitle>
              <div className="flex shrink-0 items-center gap-1.5">
                {hasPoolAccess && usePool !== null && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="flex items-center gap-1">
                        <ShieldCheck className={`h-3.5 w-3.5 shrink-0 ${usePool ? 'text-primary' : 'text-muted-foreground'}`} />
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
                  variant="outline"
                  className="h-7 px-2.5 text-xs"
                  onClick={() => { setPasteMode(true); setUploadFile(null) }}
                >
                  {t('cookies.paste_btn', { defaultValue: 'Paste' })}
                </Button>
                <Button
                  size="sm"
                  className="h-7 px-2.5 text-xs"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="mr-1 h-3 w-3" />
                  {t('cookies.upload', { defaultValue: 'Upload' })}
                </Button>
              </div>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            {loading ? (
              <div className="divide-y divide-border px-3 py-1">
                {Array.from({ length: 2 }).map((_, i) => (
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
              <div className="flex justify-center py-10 text-muted-foreground text-sm">
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
                      <ItemTitle className="flex items-center gap-1.5">
                        {c.domain}
                        {c.is_oauth && (
                          <span className="rounded text-[10px] font-medium px-1 py-0.5 bg-primary/10 text-primary leading-none">
                            OAuth
                          </span>
                        )}
                      </ItemTitle>
                      <ItemDescription>
                        {c.is_oauth
                          ? 'YouTube TV authorization'
                          : `${t('cookies.updated', { defaultValue: 'Updated' })} ${formatDate(c.updated_at)}`}
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
                      {!c.is_oauth && (
                        <Button
                          variant="ghost" size="sm" className="h-7 w-7 p-0"
                          disabled={validating === c.id}
                          onClick={() => validate(c.id)}
                        >
                          {validating === c.id
                            ? <RefreshCw className="h-4 w-4 animate-spin" />
                            : <CheckCircle className="h-4 w-4 text-muted-foreground" />}
                        </Button>
                      )}
                      <Button
                        variant="ghost" size="sm" className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                        disabled={deleting === c.id}
                        onClick={() => remove(c.id, c.domain)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
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

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,text/plain"
          className="hidden"
          onChange={handleFileChange}
        />

        {/* File upload form */}
        {uploadFile && !pasteMode && (
          <Card>
            <CardHeader className="px-4 py-3">
              <CardTitle className="text-base truncate">{uploadFile.name}</CardTitle>
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
                <Button variant="outline" size="sm" className="flex-1" onClick={() => { setUploadFile(null); setUploadContent(''); setUploadDomain(''); if (fileInputRef.current) fileInputRef.current.value = '' }}>
                  {t('common.cancel', { defaultValue: 'Cancel' })}
                </Button>
                <Button size="sm" className="flex-1" onClick={handleUpload} disabled={uploading || !uploadDomain}>
                  {uploading ? t('common.loading') : t('cookies.upload_btn', { defaultValue: 'Upload' })}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Paste form */}
        {pasteMode && (
          <Card>
            <CardHeader className="px-4 py-3">
              <CardTitle className="text-base">
                {t('cookies.paste_title', { defaultValue: 'Paste cookies.txt content' })}
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="paste-content">{t('cookies.paste_label', { defaultValue: 'Netscape cookie file content' })}</Label>
                <textarea
                  id="paste-content"
                  className="flex min-h-[120px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring font-mono resize-y"
                  placeholder={'# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t...'}
                  value={pasteContent}
                  onChange={(e) => handlePasteContentChange(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="paste-domain">{t('cookies.domain_label', { defaultValue: 'Domain' })}</Label>
                <Input
                  id="paste-domain"
                  placeholder="youtube.com"
                  value={pasteDomain}
                  onChange={(e) => setPasteDomain(e.target.value)}
                />
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="flex-1" onClick={() => { setPasteMode(false); setPasteContent(''); setPasteDomain('') }}>
                  {t('common.cancel', { defaultValue: 'Cancel' })}
                </Button>
                <Button size="sm" className="flex-1" onClick={handlePasteUpload} disabled={uploading || !pasteDomain || !pasteContent}>
                  {uploading ? t('common.loading') : t('cookies.upload_btn', { defaultValue: 'Upload' })}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Get cookies.txt extension - collapsible */}
        <HelpCard title={t('cookies.extension_title', { defaultValue: 'Get cookies via browser extension' })}>
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
          <StepList steps={[
            { n: 1, title: t('cookies.step1_title', { defaultValue: 'Install the extension' }), desc: t('cookies.step1_desc', { defaultValue: 'Available for Chrome, Chromium, and Edge.' }) },
            { n: 2, title: t('cookies.step2_title', { defaultValue: 'Log in to the site' }), desc: t('cookies.step2_desc', { defaultValue: 'Open the site (YouTube, Instagram, etc.) and log in.' }) },
            { n: 3, title: t('cookies.step3_title', { defaultValue: 'Export cookies' }), desc: t('cookies.step3_desc', { defaultValue: 'Click the extension icon and press "Export" - you\'ll get a cookies.txt file.' }) },
            { n: 4, title: t('cookies.step4_title', { defaultValue: 'Upload the file' }), desc: t('cookies.step4_desc', { defaultValue: 'Tap "Upload" above and select the file.' }) },
          ]} />
        </HelpCard>

        {/* Auto-sync - collapsible */}
        <HelpCard title={t('cookies.sync_title', { defaultValue: 'Auto-sync via Yoink Cookie Sync' })}>
          <p className="text-muted-foreground">
            {t('cookies.sync_hint', { defaultValue: 'For automatic sync, use the Yoink Cookie Sync browser extension.' })}
          </p>

          <div className="rounded-md border bg-muted/30 p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium flex items-center gap-1.5">
                <Key className="h-3.5 w-3.5 text-muted-foreground" />
                {t('cookies.token_label', { defaultValue: 'Sync token' })}
              </span>
              <Button
                size="sm" variant="outline" className="h-7 px-2.5 text-xs"
                onClick={generateToken} disabled={tokenLoading}
              >
                {tokenLoading
                  ? <RefreshCw className="h-3 w-3 animate-spin" />
                  : t('cookies.token_generate', { defaultValue: 'Generate' })}
              </Button>
            </div>
            {syncToken && (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded bg-muted px-2 py-1.5 text-xs font-mono break-all select-all">
                    {syncToken.token}
                  </code>
                  <Button size="sm" variant="ghost" className="h-7 w-7 shrink-0 p-0" onClick={copyToken}>
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  {tokenCopied
                    ? t('cookies.token_copied', { defaultValue: 'Copied!' })
                    : t('cookies.token_hint', { defaultValue: 'Valid for {{sec}}s, single-use. Paste into the extension.', sec: syncToken.expires_in })}
                </p>
              </div>
            )}
          </div>

          <StepList steps={[
            { n: 1, title: t('cookies.sync_step1_title', { defaultValue: 'Install the Yoink Cookie Sync extension' }), desc: t('cookies.sync_step1_desc', { defaultValue: 'Available for Chrome, Chromium, Edge. Ask your admin for the .zip file.' }) },
            { n: 2, title: t('cookies.sync_step2_title', { defaultValue: 'Log in to your sites' }), desc: t('cookies.sync_step2_desc', { defaultValue: 'Instagram, YouTube, X, TikTok - in the same browser.' }) },
            { n: 3, title: t('cookies.sync_step3_title', { defaultValue: 'Get a token' }), desc: t('cookies.sync_step3_desc_web', { defaultValue: 'Click "Generate" above, or send /cookie token to the bot in Telegram.' }) },
            { n: 4, title: t('cookies.sync_step4_title', { defaultValue: 'Paste token in the extension' }), desc: t('cookies.sync_step4_desc', { defaultValue: 'Token is valid for 10 minutes and single-use. Repeat when cookies expire.' }) },
          ]} />
        </HelpCard>

        {/* YouTube TV OAuth2 - collapsible */}
        <HelpCard title="Authorize via YouTube TV">
          <p className="text-muted-foreground">
            Sign in with your Google account using the TV device flow. Works on any device without a browser extension.
          </p>
          <p className="text-muted-foreground text-xs">
            After authorization, go to <b>Settings → Cookies → YouTube auth method</b> and switch to <b>YouTube TV OAuth</b> to use this account for downloads.
          </p>

          {!yttvFlow ? (
            <Button size="sm" onClick={startYttvFlow} disabled={yttvLoading}>
              {yttvLoading
                ? <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                : <LogIn className="mr-1.5 h-3.5 w-3.5" />}
              {yttvLoading ? 'Starting...' : 'Start authorization'}
            </Button>
          ) : (
            <div className="space-y-3">
              <div className="rounded-md border bg-muted/30 p-3 space-y-2">
                <p className="text-xs text-muted-foreground">1. Open this URL in any browser:</p>
                <a
                  href={yttvFlow.verification_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
                >
                  <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                  {yttvFlow.verification_url}
                </a>
                <p className="text-xs text-muted-foreground pt-1">2. Enter this code:</p>
                <div className="flex items-center gap-2">
                  <code className="rounded bg-muted px-3 py-1.5 text-lg font-mono font-bold tracking-widest select-all">
                    {yttvFlow.user_code}
                  </code>
                  <Button
                    size="sm" variant="ghost" className="h-7 w-7 shrink-0 p-0"
                    onClick={async () => {
                      await navigator.clipboard.writeText(yttvFlow.user_code)
                      setYttvCodeCopied(true)
                      setTimeout(() => setYttvCodeCopied(false), 2000)
                    }}
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                  {yttvCodeCopied && <span className="text-xs text-muted-foreground">Copied!</span>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {yttvPolling && (
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <RefreshCw className="h-3 w-3 animate-spin" />
                    Waiting for authorization...
                  </span>
                )}
                <Button variant="ghost" size="sm" className="h-7 text-xs ml-auto" onClick={cancelYttvFlow}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </HelpCard>

      </div>
    </TooltipProvider>
  )
}
