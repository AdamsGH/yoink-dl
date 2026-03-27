import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle, ExternalLink, RefreshCw, Trash2, Upload } from 'lucide-react'

import { apiClient } from '@core/lib/api-client'
import { formatDate } from '@core/lib/utils'
import { Badge } from '@core/components/ui/badge'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Input } from '@core/components/ui/input'
import { Label } from '@core/components/ui/label'
import { toast } from '@core/components/ui/toast'

interface CookieEntry {
  id: number
  domain: string
  is_valid: boolean
  updated_at: string
}

function parseDomainFromNetscape(text: string): string {
  for (const line of text.split('\n')) {
    const t = line.trim()
    if (!t || t.startsWith('#')) continue
    const parts = t.split('\t')
    if (parts.length >= 7) {
      const host = parts[0].replace(/^\./, '')
      const dot = host.lastIndexOf('.')
      if (dot > 0) {
        const prev = host.lastIndexOf('.', dot - 1)
        return prev >= 0 ? host.slice(prev + 1) : host
      }
    }
  }
  return ''
}

export default function CookiesPage() {
  const { t } = useTranslation()
  const [cookies, setCookies] = useState<CookieEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [validating, setValidating] = useState<number | null>(null)

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

  useEffect(() => { load() }, [])

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

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">{t('cookies.title', { defaultValue: 'My Cookies' })}</h1>

      {/* Stored list */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('cookies.stored', { defaultValue: 'Stored cookies' })}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex justify-center py-10 text-muted-foreground text-sm">
              {t('common.loading')}
            </div>
          ) : cookies.length === 0 ? (
            <div className="flex justify-center py-10 text-muted-foreground text-sm">
              {t('cookies.empty', { defaultValue: 'No cookies stored yet' })}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {cookies.map(c => (
                <div key={c.id} className="flex items-center justify-between px-4 py-3 gap-3">
                  <div className="min-w-0 space-y-0.5">
                    <p className="text-sm font-medium">{c.domain}</p>
                    <div className="flex items-center gap-2 pt-0.5">
                      <Badge variant={c.is_valid ? 'success' : 'destructive'} className="text-xs">
                        {c.is_valid
                          ? t('cookies.valid', { defaultValue: 'valid' })
                          : t('cookies.invalid', { defaultValue: 'invalid' })}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {t('cookies.updated', { defaultValue: 'Updated' })} {formatDate(c.updated_at)}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      variant="ghost" size="icon"
                      title={t('cookies.validate_btn', { defaultValue: 'Re-validate' })}
                      disabled={validating === c.id}
                      onClick={() => validate(c.id)}
                    >
                      {validating === c.id
                        ? <RefreshCw className="h-4 w-4 animate-spin" />
                        : <CheckCircle className="h-4 w-4 text-muted-foreground" />
                      }
                    </Button>
                    <Button
                      variant="ghost" size="icon"
                      className="text-destructive hover:text-destructive"
                      disabled={deleting === c.id}
                      onClick={() => remove(c.id, c.domain)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Manual file upload */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('cookies.upload_title', { defaultValue: 'Upload cookie file' })}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {t('cookies.upload_hint', { defaultValue: 'Upload a Netscape cookies.txt file exported from your browser.' })}
          </p>
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,text/plain"
              className="hidden"
              onChange={handleFileChange}
            />
            <div
              className="flex cursor-pointer items-center gap-3 rounded-md border border-dashed px-4 py-3 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="h-4 w-4 shrink-0" />
              {uploadFile ? uploadFile.name : t('cookies.select_file_btn', { defaultValue: 'Click to select .txt file...' })}
            </div>
          </div>
          {uploadFile && (
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
          )}
          {uploadFile && (
            <Button onClick={handleUpload} disabled={uploading || !uploadDomain} size="sm">
              {uploading
                ? t('common.loading')
                : t('cookies.upload_btn', { defaultValue: 'Upload' })}
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Get cookies.txt extension */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t('cookies.extension_title', { defaultValue: 'Get cookies via browser extension' })}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
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
            {t('cookies.extension_link', { defaultValue: 'Get cookies.txt LOCALLY - Chrome Web Store' })}
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
                title: t('cookies.step4_title', { defaultValue: 'Upload the file above' }),
                desc: t('cookies.step4_desc', { defaultValue: 'Use the upload form above to save it to the bot.' }),
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

      {/* Extension (Yoink Cookie Sync) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t('cookies.sync_title', { defaultValue: 'Auto-sync via Yoink Cookie Sync' })}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
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
  )
}
