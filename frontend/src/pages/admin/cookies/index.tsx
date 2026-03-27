import { useEffect, useRef, useState } from 'react'
import { CheckCircle, CookieIcon, RefreshCw, Trash2, Upload } from 'lucide-react'
import { Check, ChevronsUpDown } from 'lucide-react'
import type { AxiosError } from 'axios'
import { useGetIdentity } from '@refinedev/core'
import { useTranslation } from 'react-i18next'

import { apiClient } from '@core/lib/api-client'
import { formatDate, cn } from '@core/lib/utils'
import type { Cookie } from '@dl/types'
import type { User, PaginatedResponse } from '@core/types/api'
import { Badge } from '@core/components/ui/badge'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@core/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@core/components/ui/dialog'
import { Input } from '@core/components/ui/input'
import { Label } from '@core/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@core/components/ui/popover'
import { Skeleton } from '@core/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@core/components/ui/table'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@core/components/ui/tooltip'
import { toast } from '@core/components/ui/toast'
import { useTelegramWebApp } from '@core/hooks/useTelegramWebApp'

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

// Combobox for user selection
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
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  const selected = users.find((u) => String(u.id) === value)
  const label = selected
    ? (selected.first_name ?? selected.username ?? String(selected.id))
    : value || t('cookies.select_user', { defaultValue: 'Select user…' })

  const filtered = users.filter((u) => {
    const q = search.toLowerCase()
    return (
      String(u.id).includes(q) ||
      (u.username ?? '').toLowerCase().includes(q) ||
      (u.first_name ?? '').toLowerCase().includes(q)
    )
  })

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal"
        >
          <span className="truncate">{label}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder={t('cookies.search_user', { defaultValue: 'Search by name or ID…' })}
            value={search}
            onValueChange={setSearch}
          />
          <CommandList>
            <CommandEmpty>{t('common.no_results', { defaultValue: 'No users found.' })}</CommandEmpty>
            <CommandGroup>
              {filtered.map((u) => (
                <CommandItem
                  key={u.id}
                  value={String(u.id)}
                  onSelect={(v) => { onChange(v); setOpen(false); setSearch('') }}
                >
                  <Check className={cn('mr-2 h-4 w-4', value === String(u.id) ? 'opacity-100' : 'opacity-0')} />
                  <span className="flex-1 truncate">
                    {u.first_name ?? u.username ?? String(u.id)}
                  </span>
                  <span className="ml-2 font-mono text-xs text-muted-foreground">{u.id}</span>
                  <Badge variant="outline" className="ml-2 text-xs capitalize">{u.role}</Badge>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

// Upload dialog
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
          {/* File picker */}
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

          {/* Domain */}
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

          {/* User combobox */}
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

// Main page
export default function AdminCookiesPage() {
  const { t } = useTranslation()
  const { data: identity } = useGetIdentity<Identity>()
  const { showConfirm } = useTelegramWebApp()

  const [items, setItems] = useState<Cookie[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [validating, setValidating] = useState<number | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [users, setUsers] = useState<User[]>([])

  const load = () => {
    setLoading(true)
    apiClient
      .get<Cookie[]>('/dl/cookies/all')
      .then((res) => setItems(res.data))
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    apiClient
      .get<PaginatedResponse<User>>('/users', { params: { limit: 200 } })
      .then((res) => setUsers(res.data.items))
      .catch(() => {})
  }, [])

  const validate = async (id: number) => {
    setValidating(id)
    try {
      const r = await apiClient.post<Cookie>(`/dl/cookies/${id}/validate`, {})
      setItems((prev) => prev.map((c) => c.id === id ? { ...c, is_valid: r.data.is_valid } : c))
      toast.success(r.data.is_valid ? t('cookies.valid_ok', { defaultValue: 'Cookie is valid' }) : t('cookies.invalid_msg', { defaultValue: 'Cookie appears invalid' }))
    } catch {
      toast.error(t('cookies.validate_error', { defaultValue: 'Validation failed' }))
    } finally {
      setValidating(null)
    }
  }

  const remove = async (id: number) => {
    const ok = await showConfirm(t('cookies.delete_confirm', { defaultValue: 'Delete this cookie?' }))
    if (!ok) return
    setDeleting(id)
    try {
      await apiClient.delete(`/dl/cookies/by-id/${id}`)
      toast.success(t('cookies.deleted', { defaultValue: 'Cookie deleted' }))
      load()
    } catch {
      toast.error(t('cookies.delete_error', { defaultValue: 'Failed to delete' }))
    } finally {
      setDeleting(null)
    }
  }

  return (
    <TooltipProvider delayDuration={300}>
      <div className="space-y-4">
        <Card>
          <CardHeader className="px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <CookieIcon className="h-4 w-4 text-muted-foreground" />
                {loading
                  ? t('cookies.title', { defaultValue: 'Cookies' })
                  : t('cookies.count_other', { count: items.length })}
              </CardTitle>
              <Button size="sm" onClick={() => setUploadOpen(true)}>
                <Upload className="mr-1.5 h-3.5 w-3.5" />
                {t('cookies.upload')}
              </Button>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            {loading ? (
              <div className="divide-y divide-border">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-3">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-4 w-16 ml-auto" />
                  </div>
                ))}
              </div>
            ) : items.length === 0 ? (
              <div className="flex justify-center py-12 text-muted-foreground text-sm">
                {t('cookies.empty')}
              </div>
            ) : (
              <>
                {/* Desktop */}
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
                            <div className="flex gap-1 justify-end">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button variant="ghost" size="icon" disabled={validating === cookie.id} onClick={() => validate(cookie.id)}>
                                    {validating === cookie.id
                                      ? <RefreshCw className="h-4 w-4 animate-spin" />
                                      : <CheckCircle className="h-4 w-4 text-muted-foreground" />}
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>{t('cookies.revalidate')}</TooltipContent>
                              </Tooltip>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" disabled={deleting === cookie.id} onClick={() => remove(cookie.id)}>
                                    <Trash2 className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>{t('common.delete')}</TooltipContent>
                              </Tooltip>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                {/* Mobile */}
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
                        <Button variant="ghost" size="icon" disabled={validating === cookie.id} onClick={() => validate(cookie.id)}>
                          {validating === cookie.id
                            ? <RefreshCw className="h-4 w-4 animate-spin" />
                            : <CheckCircle className="h-4 w-4 text-muted-foreground" />}
                        </Button>
                        <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" disabled={deleting === cookie.id} onClick={() => remove(cookie.id)}>
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

        <UploadDialog
          open={uploadOpen}
          onClose={() => setUploadOpen(false)}
          onDone={load}
          identity={identity}
          users={users}
        />
      </div>
    </TooltipProvider>
  )
}
