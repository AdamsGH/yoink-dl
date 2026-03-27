import { useRef, useEffect, useState } from 'react'
import { CheckCircle, RefreshCw, Trash2, Upload } from 'lucide-react'
import type { AxiosError } from 'axios'
import { useGetIdentity } from '@refinedev/core'
import { useTranslation } from 'react-i18next'

import { apiClient } from '@core/lib/api-client'
import { formatDate } from '@core/lib/utils'
import type { Cookie } from '@dl/types'
import { Badge } from '@core/components/ui/badge'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@core/components/ui/dialog'
import { Input } from '@core/components/ui/input'
import { Label } from '@core/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@core/components/ui/table'
import { toast } from '@core/components/ui/toast'

type Identity = { id: number; role: string }

function parseDomainFromNetscape(content: string): string | null {
  for (const line of content.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const parts = trimmed.split('\t')
    if (parts.length >= 7) {
      return parts[0].replace(/^\./, '')
    }
  }
  return null
}

export default function AdminCookiesPage() {
  const { t } = useTranslation()
  const { data: identity } = useGetIdentity<Identity>()

  const [items, setItems] = useState<Cookie[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [validating, setValidating] = useState<number | null>(null)

  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadContent, setUploadContent] = useState('')
  const [uploadDomain, setUploadDomain] = useState('')
  const [uploadUserId, setUploadUserId] = useState('')
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = () => {
    setLoading(true)
    apiClient
      .get<Cookie[]>('/dl/cookies/all')
      .then((res) => setItems(res.data))
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (uploadOpen && identity?.id && !uploadUserId) {
      setUploadUserId(String(identity.id))
    }
  }, [uploadOpen, identity, uploadUserId])

  const validate = async (id: number) => {
    setValidating(id)
    try {
      const r = await apiClient.post<Cookie>(`/dl/cookies/${id}/validate`, {})
      setItems((prev: Cookie[]) => prev.map((c: Cookie) => c.id === id ? { ...c, is_valid: r.data.is_valid } : c))
      toast.success(r.data.is_valid ? 'Cookie is valid' : 'Cookie appears invalid')
    } catch {
      toast.error('Validation failed')
    } finally {
      setValidating(null)
    }
  }

  const remove = async (id: number) => {
    if (!confirm('Delete this cookie?')) return
    setDeleting(id)
    try {
      await apiClient.delete(`/dl/cookies/by-id/${id}`)
      toast.success('Cookie deleted')
      load()
    } catch {
      toast.error('Failed to delete cookie')
    } finally {
      setDeleting(null)
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
    if (!uploadContent) { toast.error('Select a file first'); return }
    if (!uploadDomain) { toast.error('Domain is required'); return }
    const uid = parseInt(uploadUserId, 10)
    if (!uid) { toast.error('User ID is required'); return }

    setUploading(true)
    try {
      await apiClient.post('/dl/cookies', {
        user_id: uid,
        domain: uploadDomain,
        content: uploadContent,
      })
      toast.success(`Cookie uploaded for ${uploadDomain}`)
      setUploadOpen(false)
      resetUpload()
      load()
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail
      toast.error(detail ?? 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const resetUpload = () => {
    setUploadFile(null)
    setUploadContent('')
    setUploadDomain('')
    setUploadUserId(identity?.id ? String(identity.id) : '')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-sm font-medium">
            {t('cookies.count_other', { count: items.length })}
          </CardTitle>
          <Button size="sm" onClick={() => setUploadOpen(true)}>
            <Upload className="mr-1.5 h-3.5 w-3.5" />
            {t('cookies.upload')}
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex justify-center py-12 text-muted-foreground">{t('common.loading')}</div>
          ) : items.length === 0 ? (
            <div className="flex justify-center py-12 text-muted-foreground">{t('cookies.empty')}</div>
          ) : (
            <>
              {/* Desktop table */}
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t('cookies.domain')}</TableHead>
                      <TableHead>{t('cookies.user_id_col')}</TableHead>
                      <TableHead>{t('cookies.valid_col')}</TableHead>
                      <TableHead>{t('cookies.updated')}</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((cookie) => (
                      <TableRow key={cookie.id}>
                        <TableCell className="font-medium">{cookie.domain}</TableCell>
                        <TableCell className="font-mono text-xs">{cookie.user_id}</TableCell>
                        <TableCell>
                          <Badge variant={cookie.is_valid ? 'success' : 'destructive'}>
                            {cookie.is_valid ? t('cookies.valid') : t('cookies.invalid')}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDate(cookie.updated_at)}
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Button
                              variant="ghost" size="icon"
                              title={t('cookies.revalidate')}
                              disabled={validating === cookie.id}
                              onClick={() => validate(cookie.id)}
                            >
                              {validating === cookie.id
                                ? <RefreshCw className="h-4 w-4 animate-spin" />
                                : <CheckCircle className="h-4 w-4 text-muted-foreground" />}
                            </Button>
                            <Button
                              variant="ghost" size="icon"
                              className="text-destructive hover:text-destructive"
                              disabled={deleting === cookie.id}
                              onClick={() => remove(cookie.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Mobile cards */}
              <div className="md:hidden divide-y divide-border">
                {items.map((cookie) => (
                  <div key={cookie.id} className="flex items-center justify-between px-4 py-3 gap-3">
                    <div className="min-w-0 space-y-0.5">
                      <p className="text-sm font-medium">{cookie.domain}</p>
                      <p className="font-mono text-xs text-muted-foreground">{t('cookies.uid', { id: cookie.user_id })}</p>
                      <div className="flex items-center gap-2 pt-0.5">
                        <Badge variant={cookie.is_valid ? 'success' : 'destructive'} className="text-xs">
                          {cookie.is_valid ? t('cookies.valid') : t('cookies.invalid')}
                        </Badge>
                        <span className="text-xs text-muted-foreground">{formatDate(cookie.updated_at)}</span>
                      </div>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <Button
                        variant="ghost" size="icon"
                        title={t('cookies.revalidate')}
                        disabled={validating === cookie.id}
                        onClick={() => validate(cookie.id)}
                      >
                        {validating === cookie.id
                          ? <RefreshCw className="h-4 w-4 animate-spin" />
                          : <CheckCircle className="h-4 w-4 text-muted-foreground" />}
                      </Button>
                      <Button
                        variant="ghost" size="icon"
                        className="text-destructive hover:text-destructive"
                        disabled={deleting === cookie.id}
                        onClick={() => remove(cookie.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Dialog open={uploadOpen} onOpenChange={(open: boolean) => { setUploadOpen(open); if (!open) resetUpload() }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('cookies.upload_title')}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>{t('cookies.file_label')}</Label>
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
                {uploadFile ? uploadFile.name : t('cookies.file_select')}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="cookie-domain">{t('cookies.domain')}</Label>
              <Input
                id="cookie-domain"
                placeholder="youtube.com"
                value={uploadDomain}
                onChange={(e) => setUploadDomain(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t('cookies.domain_hint')}</p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="cookie-uid">{t('cookies.user_id_label')}</Label>
              <Input
                id="cookie-uid"
                type="number"
                placeholder="123456789"
                value={uploadUserId}
                onChange={(e) => setUploadUserId(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t('cookies.user_id_hint')}</p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleUpload} disabled={uploading || !uploadFile}>
              {uploading ? t('cookies.uploading') : t('cookies.upload')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
