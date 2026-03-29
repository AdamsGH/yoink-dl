import { useEffect, useRef, useState } from 'react'
import { CheckCircle, CookieIcon, Database, RefreshCw, Trash2, Upload } from 'lucide-react'
import type { AxiosError } from 'axios'
import { useGetIdentity } from '@refinedev/core'
import { useTranslation } from 'react-i18next'

import { apiClient } from '@core/lib/api-client'
import { formatDate } from '@core/lib/utils'
import type { Cookie } from '@dl/types'
import type { User, PaginatedResponse } from '@core/types/api'
import { CookieStatusBadge, RoleBadge } from '@core/components/app/StatusBadge'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Combobox, ComboboxContent, ComboboxEmpty, ComboboxInput, ComboboxItem, ComboboxList } from '@core/components/ui/combobox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@core/components/ui/dialog'
import { Input } from '@core/components/ui/input'
import { Item, ItemActions, ItemContent, ItemDescription, ItemMedia, ItemTitle } from '@core/components/ui/item'
import { Label } from '@core/components/ui/label'
import { Skeleton } from '@core/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@core/components/ui/tooltip'
import { toast } from '@core/components/ui/toast'
import { useTelegramWebApp } from '@core/hooks/useTelegramWebApp'

const faviconCache = new Map<string, string | null>()

function useFavicon(domain: string): string | null {
  const [src, setSrc] = useState<string | null>(() => faviconCache.get(domain) ?? null)
  useEffect(() => {
    if (faviconCache.has(domain)) { setSrc(faviconCache.get(domain)!); return }
    const url = `https://www.google.com/s2/favicons?sz=32&domain=${domain}`
    const img = new Image()
    img.onload = () => { faviconCache.set(domain, url); setSrc(url) }
    img.onerror = () => { faviconCache.set(domain, null); setSrc(null) }
    img.src = url
  }, [domain])
  return src
}

function CookieFavicon({ domain }: { domain: string }) {
  const src = useFavicon(domain)
  if (src) return <img src={src} alt="" className="size-4 rounded-sm object-contain" />
  return <CookieIcon className="size-4" />
}

type Identity = { id: number; role: string }

function parseDomainFromNetscape(content: string): string | null {
  for (const line of content.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const parts = trimmed.split('\t')
    if (parts.length >= 7) return parts[0].replace(/^\./, '')
  }
  return null
}

function UserCombobox({
  value,
  onChange,
  users,
}: {
  value: string
  onChange: (v: string) => void
  users: User[]
}) {
  const { t } = useTranslation()
  const selected = users.find((u) => String(u.id) === value) ?? null

  return (
    <Combobox
      value={selected}
      onValueChange={(u: User | null) => onChange(u ? String(u.id) : '')}
      items={users}
      itemToStringLabel={(u: User) => u.first_name ?? u.username ?? String(u.id)}
      itemToStringValue={(u: User) => String(u.id)}
    >
      <ComboboxInput placeholder={t('cookies.select_user', { defaultValue: 'Select user…' })} />
      <ComboboxContent>
        <ComboboxEmpty>{t('common.no_results', { defaultValue: 'No users found.' })}</ComboboxEmpty>
        <ComboboxList>
          {(u: User) => (
            <ComboboxItem key={u.id} value={u}>
              <span className="flex-1 truncate">
                {u.first_name ?? u.username ?? String(u.id)}
              </span>
              <span className="ml-auto font-mono text-xs text-muted-foreground">{u.id}</span>
              <RoleBadge role={u.role} />
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}

function UploadDialog({
  open,
  onClose,
  onDone,
  identity,
  users,
}: {
  open: boolean
  onClose: () => void
  onDone: () => void
  identity: Identity | undefined
  users: User[]
}) {
  const { t } = useTranslation()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const defaultUserId = () => identity?.id ? String(identity.id) : ''

  const [file, setFile] = useState<File | null>(null)
  const [content, setContent] = useState('')
  const [domain, setDomain] = useState('')
  const [userId, setUserId] = useState(defaultUserId)
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    if (open) setUserId(defaultUserId())
  }, [open, identity?.id])

  const reset = () => {
    setFile(null)
    setContent('')
    setDomain('')
    setUserId(defaultUserId())
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleFile = (f: File | undefined) => {
    if (!f) return
    setFile(f)
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      setContent(text)
      const d = parseDomainFromNetscape(text)
      if (d) setDomain(d)
    }
    reader.readAsText(f)
  }

  const handleUpload = async () => {
    if (!content) { toast.error(t('cookies.err_no_file', { defaultValue: 'Select a file first' })); return }
    if (!domain)  { toast.error(t('cookies.err_no_domain', { defaultValue: 'Domain is required' })); return }
    const uid = parseInt(userId, 10)
    if (!uid)     { toast.error(t('cookies.err_no_uid', { defaultValue: 'User ID is required' })); return }

    setUploading(true)
    try {
      await apiClient.post('/dl/cookies', { user_id: uid, domain, content })
      toast.success(t('cookies.uploaded_ok', { domain, defaultValue: `Cookie uploaded for ${domain}` }))
      onClose()
      reset()
      onDone()
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail
      toast.error(detail ?? t('cookies.err_upload', { defaultValue: 'Upload failed' }))
    } finally {
      setUploading(false)
    }
  }

  const canUpload = !!file && !!domain && !!userId && !uploading

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { reset(); onClose() } }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('cookies.upload_title')}</DialogTitle>
          <DialogDescription>
            {t('cookies.upload_hint', { defaultValue: 'Upload a Netscape-format cookie file (.txt).' })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>{t('cookies.file_label')}</Label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,text/plain"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
            <div
              className="flex cursor-pointer items-center gap-3 rounded-md border border-dashed px-4 py-3 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="h-4 w-4 shrink-0" />
              {file ? file.name : t('cookies.file_select')}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cookie-domain">{t('cookies.domain')}</Label>
            <Input
              id="cookie-domain"
              placeholder="youtube.com"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">{t('cookies.domain_hint')}</p>
          </div>

          <div className="space-y-1.5">
            <Label>{t('cookies.user_id_label')}</Label>
            <UserCombobox value={userId} onChange={setUserId} users={users} />
            <p className="text-xs text-muted-foreground">{t('cookies.user_id_hint')}</p>
          </div>
        </div>

        <DialogFooter className="flex-row gap-2 sm:space-x-0">
          <Button variant="outline" className="flex-1" onClick={() => { reset(); onClose() }}>
            {t('common.cancel')}
          </Button>
          <Button className="flex-1" onClick={handleUpload} disabled={!canUpload}>
            {uploading ? t('cookies.uploading') : t('cookies.upload')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AddPoolDialog({
  open,
  onClose,
  onDone,
}: {
  open: boolean
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useTranslation()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [content, setContent] = useState('')
  const [domain, setDomain] = useState('')
  const [uploading, setUploading] = useState(false)

  const reset = () => {
    setFile(null)
    setContent('')
    setDomain('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleFile = (f: File | undefined) => {
    if (!f) return
    setFile(f)
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      setContent(text)
      const d = parseDomainFromNetscape(text)
      if (d) setDomain(d)
    }
    reader.readAsText(f)
  }

  const handleAdd = async () => {
    if (!content) { toast.error(t('cookies.err_no_file', { defaultValue: 'Select a file first' })); return }
    if (!domain)  { toast.error(t('cookies.err_no_domain', { defaultValue: 'Domain is required' })); return }

    setUploading(true)
    try {
      await apiClient.post('/dl/cookies/pool', { domain, content })
      toast.success(t('cookies.uploaded_ok', { domain, defaultValue: `Cookie uploaded for ${domain}` }))
      onClose()
      reset()
      onDone()
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail
      toast.error(detail ?? t('cookies.err_upload', { defaultValue: 'Upload failed' }))
    } finally {
      setUploading(false)
    }
  }

  const canAdd = !!file && !!domain && !uploading

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { reset(); onClose() } }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('cookies.pool_add_title', { defaultValue: 'Add Pool Cookie' })}</DialogTitle>
          <DialogDescription>
            {t('cookies.upload_hint', { defaultValue: 'Upload a Netscape-format cookie file (.txt).' })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>{t('cookies.file_label')}</Label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,text/plain"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
            <div
              className="flex cursor-pointer items-center gap-3 rounded-md border border-dashed px-4 py-3 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="h-4 w-4 shrink-0" />
              {file ? file.name : t('cookies.file_select')}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="pool-cookie-domain">{t('cookies.domain')}</Label>
            <Input
              id="pool-cookie-domain"
              placeholder="youtube.com"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">{t('cookies.domain_hint')}</p>
          </div>
        </div>

        <DialogFooter className="flex-row gap-2 sm:space-x-0">
          <Button variant="outline" className="flex-1" onClick={() => { reset(); onClose() }}>
            {t('common.cancel')}
          </Button>
          <Button className="flex-1" onClick={handleAdd} disabled={!canAdd}>
            {uploading ? t('cookies.uploading') : t('cookies.upload')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function AdminCookiesPage() {
  const { t } = useTranslation()
  const { data: identity } = useGetIdentity<Identity>()
  const { showConfirm } = useTelegramWebApp()

  const [poolItems, setPoolItems] = useState<Cookie[]>([])
  const [poolLoading, setPoolLoading] = useState(true)
  const [poolFetching, setPoolFetching] = useState(false)

  const [personalItems, setPersonalItems] = useState<Cookie[]>([])
  const [personalLoading, setPersonalLoading] = useState(true)
  const [personalFetching, setPersonalFetching] = useState(false)

  const [deleting, setDeleting] = useState<number | null>(null)
  const [validating, setValidating] = useState<number | null>(null)
  const [addPoolOpen, setAddPoolOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [users, setUsers] = useState<User[]>([])

  const userMap = new Map(users.map((u) => [u.id, u]))

  const poolDomainCounts = poolItems.reduce<Map<string, number>>((acc, c) => {
    acc.set(c.domain, (acc.get(c.domain) ?? 0) + 1)
    return acc
  }, new Map())

  const poolDomains = Array.from(
    poolItems.reduce<Map<string, Cookie>>((acc, c) => {
      if (!acc.has(c.domain)) acc.set(c.domain, c)
      return acc
    }, new Map()).values()
  )

  const loadPool = (isInitial = false) => {
    if (isInitial) setPoolLoading(true)
    else setPoolFetching(true)
    apiClient
      .get<Cookie[]>('/dl/cookies/pool')
      .then((res) => setPoolItems(res.data))
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => { setPoolLoading(false); setPoolFetching(false) })
  }

  const loadPersonal = (isInitial = false) => {
    if (isInitial) setPersonalLoading(true)
    else setPersonalFetching(true)
    apiClient
      .get<Cookie[]>('/dl/cookies/all')
      .then((res) => setPersonalItems(res.data.filter((c) => !c.is_pool)))
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => { setPersonalLoading(false); setPersonalFetching(false) })
  }

  useEffect(() => {
    loadPool(true)
    loadPersonal(true)
    apiClient
      .get<PaginatedResponse<User>>('/users', { params: { limit: 200 } })
      .then((res) => setUsers(res.data.items))
      .catch(() => {})
  }, [])

  const validate = async (id: number) => {
    setValidating(id)
    try {
      const r = await apiClient.post<Cookie>(`/dl/cookies/${id}/validate`, {})
      const updater = (prev: Cookie[]) => prev.map((c) => c.id === id ? { ...c, is_valid: r.data.is_valid } : c)
      setPoolItems(updater)
      setPersonalItems(updater)
      toast.success(
        r.data.is_valid
          ? t('cookies.valid_ok', { defaultValue: 'Cookie is valid' })
          : t('cookies.invalid_msg', { defaultValue: 'Cookie appears invalid' })
      )
    } catch {
      toast.error(t('cookies.validate_error', { defaultValue: 'Validation failed' }))
    } finally {
      setValidating(null)
    }
  }

  const removePool = async (id: number) => {
    const ok = await showConfirm(t('cookies.delete_confirm', { defaultValue: 'Delete this cookie?' }))
    if (!ok) return
    setDeleting(id)
    try {
      await apiClient.delete(`/dl/cookies/pool/${id}`)
      toast.success(t('cookies.deleted', { defaultValue: 'Cookie deleted' }))
      loadPool()
    } catch {
      toast.error(t('cookies.delete_error', { defaultValue: 'Failed to delete' }))
    } finally {
      setDeleting(null)
    }
  }

  const removePersonal = async (id: number) => {
    const ok = await showConfirm(t('cookies.delete_confirm', { defaultValue: 'Delete this cookie?' }))
    if (!ok) return
    setDeleting(id)
    try {
      await apiClient.delete(`/dl/cookies/by-id/${id}`)
      toast.success(t('cookies.deleted', { defaultValue: 'Cookie deleted' }))
      loadPersonal()
    } catch {
      toast.error(t('cookies.delete_error', { defaultValue: 'Failed to delete' }))
    } finally {
      setDeleting(null)
    }
  }

  const poolRepresentative = (domain: string): Cookie | undefined =>
    poolItems.find((c) => c.domain === domain)

  return (
    <TooltipProvider delayDuration={300}>
      <div className="space-y-4">
        <Card>
          <CardHeader className="px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Database className="h-4 w-4 text-muted-foreground" />
                {poolLoading
                  ? t('cookies.pool_title', { defaultValue: 'Cookie Pool' })
                  : t('cookies.pool_count', { count: poolItems.length, defaultValue: `Cookie Pool (${poolItems.length})` })}
              </CardTitle>
              <Button size="sm" className="h-7 px-2.5 text-xs" onClick={() => setAddPoolOpen(true)}>
                <Upload className="mr-1.5 h-3 w-3" />
                {t('cookies.add', { defaultValue: 'Add' })}
              </Button>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            {poolLoading ? (
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
            ) : poolDomains.length === 0 ? (
              <div className="flex justify-center py-12 text-muted-foreground text-sm">
                {t('cookies.pool_empty', { defaultValue: 'No pool cookies' })}
              </div>
            ) : (
              <div
                className="divide-y divide-border px-3 py-1 transition-opacity duration-150"
                style={{ opacity: poolFetching ? 0.5 : 1 }}
              >
                {poolDomains.map((cookie) => {
                  const count = poolDomainCounts.get(cookie.domain) ?? 1
                  const rep = poolRepresentative(cookie.domain)

                  return (
                    <Item key={cookie.domain} size="sm" className="py-2.5 rounded-none border-0">
                      <ItemMedia variant="icon" className="size-8 rounded-md bg-muted text-muted-foreground">
                        <CookieFavicon domain={cookie.domain} />
                      </ItemMedia>
                      <ItemContent>
                        <ItemTitle>{cookie.domain}</ItemTitle>
                        <ItemDescription>
                          {t('cookies.accounts_count', { count, defaultValue: `${count} accounts` })}
                        </ItemDescription>
                      </ItemContent>
                      <ItemActions>
                        {rep && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span>
                                <CookieStatusBadge valid={rep.is_valid} />
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>
                              {rep.validated_at
                                ? `${t('cookies.validated_col', { defaultValue: 'Validated' })}: ${formatDate(rep.validated_at)}`
                                : t('cookies.never', { defaultValue: 'Never validated' })}
                            </TooltipContent>
                          </Tooltip>
                        )}
                        {rep && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                disabled={validating === rep.id}
                                onClick={() => validate(rep.id)}
                              >
                                {validating === rep.id
                                  ? <RefreshCw className="h-4 w-4 animate-spin" />
                                  : <CheckCircle className="h-4 w-4 text-muted-foreground" />}
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{t('cookies.revalidate')}</TooltipContent>
                          </Tooltip>
                        )}
                        {rep && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="text-destructive hover:text-destructive"
                                disabled={deleting === rep.id}
                                onClick={() => removePool(rep.id)}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{t('common.delete')}</TooltipContent>
                          </Tooltip>
                        )}
                      </ItemActions>
                    </Item>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <CookieIcon className="h-4 w-4 text-muted-foreground" />
                {personalLoading
                  ? t('cookies.title', { defaultValue: 'Cookies' })
                  : t('cookies.count_other', { count: personalItems.length })}
              </CardTitle>
              <Button size="sm" className="h-7 px-2.5 text-xs" onClick={() => setUploadOpen(true)}>
                <Upload className="mr-1.5 h-3 w-3" />
                {t('cookies.upload')}
              </Button>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            {personalLoading ? (
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
            ) : personalItems.length === 0 ? (
              <div className="flex justify-center py-12 text-muted-foreground text-sm">
                {t('cookies.empty')}
              </div>
            ) : (
              <div
                className="divide-y divide-border px-3 py-1 transition-opacity duration-150"
                style={{ opacity: personalFetching ? 0.5 : 1 }}
              >
                {personalItems.map((cookie) => {
                  const owner = userMap.get(cookie.user_id)
                  const ownerLabel = owner
                    ? (owner.username ? `@${owner.username}` : (owner.first_name ?? String(cookie.user_id)))
                    : String(cookie.user_id)

                  return (
                    <Item key={cookie.id} size="sm" className="py-2.5 rounded-none border-0">
                      <ItemMedia variant="icon" className="size-8 rounded-md bg-muted text-muted-foreground">
                        <CookieFavicon domain={cookie.domain} />
                      </ItemMedia>
                      <ItemContent>
                        <ItemTitle>{cookie.domain}</ItemTitle>
                        <ItemDescription>{ownerLabel}</ItemDescription>
                      </ItemContent>
                      <ItemActions>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span>
                              <CookieStatusBadge valid={cookie.is_valid} />
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            {cookie.validated_at
                              ? `${t('cookies.validated_col', { defaultValue: 'Validated' })}: ${formatDate(cookie.validated_at)}`
                              : t('cookies.never', { defaultValue: 'Never validated' })}
                          </TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              disabled={validating === cookie.id}
                              onClick={() => validate(cookie.id)}
                            >
                              {validating === cookie.id
                                ? <RefreshCw className="h-4 w-4 animate-spin" />
                                : <CheckCircle className="h-4 w-4 text-muted-foreground" />}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>{t('cookies.revalidate')}</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-destructive hover:text-destructive"
                              disabled={deleting === cookie.id}
                              onClick={() => removePersonal(cookie.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>{t('common.delete')}</TooltipContent>
                        </Tooltip>
                      </ItemActions>
                    </Item>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <AddPoolDialog
          open={addPoolOpen}
          onClose={() => setAddPoolOpen(false)}
          onDone={() => loadPool()}
        />

        <UploadDialog
          open={uploadOpen}
          onClose={() => setUploadOpen(false)}
          onDone={() => loadPersonal()}
          identity={identity}
          users={users}
        />
      </div>
    </TooltipProvider>
  )
}
