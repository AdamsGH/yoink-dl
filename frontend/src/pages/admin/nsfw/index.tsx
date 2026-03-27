import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AxiosError } from 'axios'
import { ChevronDown, Download, Pencil, Plus, ShieldAlert, Trash2, Upload } from 'lucide-react'

import { apiClient } from '@core/lib/api-client'
import { formatDate } from '@core/lib/utils'
import type { NsfwDomain, NsfwKeyword, NsfwCheckResponse } from '@dl/types'
import { Badge } from '@core/components/ui/badge'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@core/components/ui/collapsible'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@core/components/ui/dialog'
import { Input } from '@core/components/ui/input'
import { JsonEditor } from '@core/components/ui/json-editor'
import { Label } from '@core/components/ui/label'
import { Separator } from '@core/components/ui/separator'
import { Skeleton } from '@core/components/ui/skeleton'
import { toast } from '@core/components/ui/toast'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@core/components/ui/tooltip'
import { useTelegramWebApp } from '@core/hooks/useTelegramWebApp'

// ── Dialogs ───────────────────────────────────────────────────────────────────

function EntryDialog({
  open,
  title,
  fieldLabel,
  fieldPlaceholder,
  initialValue = '',
  initialNote = '',
  submitLabel,
  onClose,
  onSubmit,
}: {
  open: boolean
  title: string
  fieldLabel: string
  fieldPlaceholder?: string
  initialValue?: string
  initialNote?: string
  submitLabel: string
  onClose: () => void
  onSubmit: (value: string, note: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const [value, setValue] = useState(initialValue)
  const [note, setNote] = useState(initialNote)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) { setValue(initialValue); setNote(initialNote) }
  }, [open, initialValue, initialNote])

  const handleSubmit = async () => {
    if (!value.trim()) return
    setSaving(true)
    try {
      await onSubmit(value.trim(), note.trim())
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>{fieldLabel}</Label>
            <Input
              placeholder={fieldPlaceholder}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-muted-foreground">{t('nsfw.note_optional')}</Label>
            <Input
              placeholder={t('nsfw.note_placeholder')}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSubmit} disabled={saving || !value.trim()}>
            {saving ? t('common.loading') : submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const IMPORT_EXAMPLE = `{
  "domains":  [{ "domain": "example.com", "note": "optional" }],
  "keywords": [{ "keyword": "word",       "note": "optional" }]
}`

function ImportDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [value, setValue] = useState('')
  const [parseError, setParseError] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback((f: File | null | undefined) => {
    if (!f) return
    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target?.result as string ?? ''
      setValue(text)
      try { JSON.parse(text); setParseError(null) } catch (err) {
        setParseError((err as Error).message)
      }
    }
    reader.readAsText(f)
  }, [])

  const handleChange = (v: string) => {
    setValue(v)
    if (!v.trim()) { setParseError(null); return }
    try { JSON.parse(v); setParseError(null) } catch (err) {
      setParseError((err as Error).message)
    }
  }

  const handleImport = async () => {
    let parsed: { domains?: { domain: string; note?: string }[]; keywords?: { keyword: string; note?: string }[] }
    try { parsed = JSON.parse(value) } catch (err) {
      setParseError((err as Error).message)
      return
    }
    setImporting(true)
    try {
      await apiClient.post('/dl/nsfw/import', {
        domains: parsed.domains ?? [],
        keywords: parsed.keywords ?? [],
      })
      toast.success(t('nsfw.added_ok'))
      setValue('')
      setParseError(null)
      onClose()
      onDone()
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail
      toast.error(detail ?? t('nsfw.add_error'))
    } finally {
      setImporting(false)
    }
  }

  const canImport = value.trim().length > 0 && !parseError && !importing

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { setValue(''); setParseError(null); onClose() } }}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t('nsfw.import')}</DialogTitle>
          <DialogDescription>
            {t('nsfw.import_hint', { defaultValue: 'Paste JSON with domains and/or keywords arrays.' })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* Schema example — read-only highlighted block */}
          <JsonEditor
            value={IMPORT_EXAMPLE}
            readOnly
            minHeight="auto"
            maxHeight="120px"
            className="rounded-md border border-border"
          />

          {/* Editable area */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground font-medium">
                {t('nsfw.your_json', { defaultValue: 'Your JSON' })}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 text-xs"
                onClick={() => fileRef.current?.click()}
              >
                <Upload className="h-3 w-3" />
                {t('nsfw.load_file', { defaultValue: 'Load file' })}
              </Button>
              <input ref={fileRef} type="file" accept=".json" className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0])} />
            </div>
            <JsonEditor
              value={value}
              onChange={handleChange}
              minHeight="160px"
              maxHeight="40vh"
              className="rounded-md border border-border"
            />
            {parseError && (
              <p className="text-xs text-destructive font-mono">{parseError}</p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleImport} disabled={!canImport}>
            {importing ? t('common.loading') : t('nsfw.import')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Icon button with tooltip ──────────────────────────────────────────────────

function IconBtn({
  tooltip,
  onClick,
  disabled,
  destructive,
  children,
}: {
  tooltip: string
  onClick: () => void
  disabled?: boolean
  destructive?: boolean
  children: React.ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={`h-8 w-8 ${destructive ? 'text-muted-foreground hover:text-destructive' : ''}`}
          disabled={disabled}
          onClick={onClick}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">{tooltip}</TooltipContent>
    </Tooltip>
  )
}

// ── Item list ─────────────────────────────────────────────────────────────────

interface ListItem {
  id: number
  primary: string
  note?: string | null
  created_at: string
}

function ItemList<T extends ListItem>({
  items,
  loading,
  emptyKey,
  deletingId,
  onEdit,
  onDelete,
}: {
  items: T[]
  loading: boolean
  emptyKey: string
  deletingId: number | null
  onEdit: (item: T) => void
  onDelete: (item: T) => void
}) {
  const { t } = useTranslation()

  if (loading) {
    return (
      <div className="divide-y divide-border">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-3">
            <Skeleton className="h-4 flex-1" />
            <Skeleton className="h-4 w-20 hidden sm:block" />
            <Skeleton className="h-8 w-16 shrink-0" />
          </div>
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex justify-center py-6 text-sm text-muted-foreground">
        {t(emptyKey as Parameters<typeof t>[0])}
      </div>
    )
  }

  return (
    <div className="divide-y divide-border">
      {items.map((item) => (
        <div key={item.id} className="flex items-start gap-3 px-4 py-3">
          <div className="flex-1 min-w-0 space-y-0.5">
            <p className="font-mono text-sm leading-snug break-all">{item.primary}</p>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              {item.note && <span className="text-xs text-muted-foreground">{item.note}</span>}
              <span className="text-xs text-muted-foreground/60">{formatDate(item.created_at)}</span>
            </div>
          </div>
          <div className="flex gap-1 shrink-0 pt-0.5">
            <IconBtn tooltip={t('common.edit')} onClick={() => onEdit(item)}>
              <Pencil className="h-3.5 w-3.5" />
            </IconBtn>
            <IconBtn tooltip={t('common.delete')} destructive disabled={deletingId === item.id} onClick={() => onDelete(item)}>
              <Trash2 className="h-3.5 w-3.5" />
            </IconBtn>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Check panel ───────────────────────────────────────────────────────────────

function CheckPanel() {
  const { t } = useTranslation()
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [result, setResult] = useState<NsfwCheckResponse | null>(null)
  const [checking, setChecking] = useState(false)

  const check = async () => {
    if (!url.trim()) return
    setChecking(true)
    setResult(null)
    try {
      const res = await apiClient.post<NsfwCheckResponse>('/dl/nsfw/check', {
        url: url.trim(),
        title: title.trim() || null,
        description: description.trim() || null,
      })
      setResult(res.data)
    } catch {
      toast.error(t('common.load_error'))
    } finally {
      setChecking(false)
    }
  }

  return (
    <Card>
      <CardHeader className="px-4 py-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldAlert className="h-4 w-4 text-muted-foreground" />
          {t('nsfw.check_title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <div className="flex gap-2">
          <Input
            placeholder={t('nsfw.check_placeholder')}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && check()}
            className="flex-1"
          />
          <Button onClick={check} disabled={checking || !url.trim()} className="shrink-0">
            {checking ? t('nsfw.checking') : t('nsfw.check_btn')}
          </Button>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Input
            placeholder={t('nsfw.check_title_placeholder', { defaultValue: 'Title (optional)' })}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Input
            placeholder={t('nsfw.check_desc_placeholder', { defaultValue: 'Description (optional)' })}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        {result && (
          <div className="flex flex-wrap items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm">
            <Badge variant={result.is_nsfw ? 'destructive' : 'secondary'}>
              {result.is_nsfw ? t('nsfw.result_nsfw', { defaultValue: 'NSFW' }) : t('nsfw.result_clean', { defaultValue: 'Clean' })}
            </Badge>
            {result.matched_domain && (
              <span className="font-mono text-xs text-muted-foreground">
                {t('nsfw.matched_domain', { defaultValue: 'domain:' })} {result.matched_domain}
              </span>
            )}
            {result.matched_keywords.length > 0 && (
              <span className="font-mono text-xs text-muted-foreground">
                {t('nsfw.matched_keywords', { defaultValue: 'keywords:' })} {result.matched_keywords.join(', ')}
              </span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminNsfwPage() {
  const { t } = useTranslation()
  const { showConfirm, haptic } = useTelegramWebApp()

  const [domains, setDomains] = useState<NsfwDomain[]>([])
  const [keywords, setKeywords] = useState<NsfwKeyword[]>([])
  const [loadingD, setLoadingD] = useState(true)
  const [loadingK, setLoadingK] = useState(true)
  const [deletingD, setDeletingD] = useState<number | null>(null)
  const [deletingK, setDeletingK] = useState<number | null>(null)

  const [addDomainOpen, setAddDomainOpen] = useState(false)
  const [addKeywordOpen, setAddKeywordOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [editDomain, setEditDomain] = useState<NsfwDomain | null>(null)
  const [editKeyword, setEditKeyword] = useState<NsfwKeyword | null>(null)

  const loadDomains = useCallback(() => {
    setLoadingD(true)
    apiClient.get<NsfwDomain[]>('/dl/nsfw/domains')
      .then((r) => setDomains(r.data))
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => setLoadingD(false))
  }, [t])

  const loadKeywords = useCallback(() => {
    setLoadingK(true)
    apiClient.get<NsfwKeyword[]>('/dl/nsfw/keywords')
      .then((r) => setKeywords(r.data))
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => setLoadingK(false))
  }, [t])

  useEffect(() => { loadDomains(); loadKeywords() }, [loadDomains, loadKeywords])

  const removeDomain = async (d: NsfwDomain) => {
    const confirmed = await showConfirm(t('nsfw.confirm_remove_domain', { domain: d.domain, defaultValue: `Remove "${d.domain}"?` }))
    if (!confirmed) return
    setDeletingD(d.id)
    try {
      await apiClient.delete(`/dl/nsfw/domains/${d.id}`)
      haptic('success')
      toast.success(t('nsfw.removed'))
      loadDomains()
    } catch {
      haptic('error')
      toast.error(t('nsfw.remove_error'))
    } finally {
      setDeletingD(null)
    }
  }

  const removeKeyword = async (k: NsfwKeyword) => {
    const confirmed = await showConfirm(t('nsfw.confirm_remove_keyword', { keyword: k.keyword, defaultValue: `Remove "${k.keyword}"?` }))
    if (!confirmed) return
    setDeletingK(k.id)
    try {
      await apiClient.delete(`/dl/nsfw/keywords/${k.id}`)
      haptic('success')
      toast.success(t('nsfw.removed'))
      loadKeywords()
    } catch {
      haptic('error')
      toast.error(t('nsfw.remove_error'))
    } finally {
      setDeletingK(null)
    }
  }

  const addDomain = async (domain: string, note: string) => {
    try {
      await apiClient.post('/dl/nsfw/domains', { domain, note: note || null })
      toast.success(t('nsfw.added_ok'))
      loadDomains()
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail
      toast.error(detail ?? t('nsfw.add_error'))
      throw err
    }
  }

  const addKeyword = async (keyword: string, note: string) => {
    try {
      await apiClient.post('/dl/nsfw/keywords', { keyword, note: note || null })
      toast.success(t('nsfw.added_ok'))
      loadKeywords()
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail
      toast.error(detail ?? t('nsfw.add_error'))
      throw err
    }
  }

  const saveDomain = async (value: string, note: string) => {
    if (!editDomain) return
    try {
      await apiClient.patch(`/dl/nsfw/domains/${editDomain.id}`, { domain: value, note: note || null })
      toast.success(t('nsfw.saved'))
      loadDomains()
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail
      toast.error(detail ?? t('nsfw.save_error'))
      throw err
    }
  }

  const saveKeyword = async (value: string, note: string) => {
    if (!editKeyword) return
    try {
      await apiClient.patch(`/dl/nsfw/keywords/${editKeyword.id}`, { keyword: value, note: note || null })
      toast.success(t('nsfw.saved'))
      loadKeywords()
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail
      toast.error(detail ?? t('nsfw.save_error'))
      throw err
    }
  }

  const exportJson = async () => {
    try {
      const res = await apiClient.get('/dl/nsfw/export')
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'nsfw-export.json'; a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error(t('common.load_error'))
    }
  }

  const domainItems: ListItem[] = domains.map((d) => ({ id: d.id, primary: d.domain, note: d.note, created_at: d.created_at }))
  const keywordItems: ListItem[] = keywords.map((k) => ({ id: k.id, primary: k.keyword, note: k.note, created_at: k.created_at }))

  return (
    <TooltipProvider delayDuration={300}>
      <div className="space-y-4">
        <CheckPanel />

        {/* Domains + Keywords in one card */}
        <Card>
          {/* Card-level header: title + import/export */}
          <CardHeader className="px-4 py-3 border-b">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-base">
                {t('nsfw.rules_title', { defaultValue: 'Rules' })}
              </CardTitle>
              <div className="flex gap-1 shrink-0">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setImportOpen(true)}>
                      <Upload className="h-3.5 w-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top">{t('nsfw.import')}</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="outline" size="icon" className="h-8 w-8" onClick={exportJson}>
                      <Download className="h-3.5 w-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top">{t('nsfw.export', { defaultValue: 'Export' })}</TooltipContent>
                </Tooltip>
              </div>
            </div>
          </CardHeader>

          {/* Domains section */}
          <Collapsible defaultOpen={false}>
            <div className="px-4 py-3 flex items-center justify-between gap-2">
              <CollapsibleTrigger className="flex items-center gap-2 group flex-1 min-w-0">
                <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-data-[state=closed]:-rotate-90" />
                <span className="text-sm font-medium">
                  {loadingD
                    ? t('nsfw.domains', { defaultValue: 'Domains' })
                    : t('nsfw.domains_count', { count: domains.length, defaultValue: '{{count}} domains' })}
                </span>
              </CollapsibleTrigger>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button size="icon" className="h-7 w-7 shrink-0" onClick={() => setAddDomainOpen(true)}>
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="top">{t('nsfw.add_domain')}</TooltipContent>
              </Tooltip>
            </div>
            <CollapsibleContent>
              <ItemList
                items={domainItems}
                loading={loadingD}
                emptyKey="nsfw.no_domains"
                deletingId={deletingD}
                onEdit={(item) => setEditDomain(domains.find((d) => d.id === item.id) ?? null)}
                onDelete={(item) => removeDomain(domains.find((d) => d.id === item.id)!)}
              />
            </CollapsibleContent>
          </Collapsible>

          <Separator />

          {/* Keywords section */}
          <Collapsible defaultOpen={false}>
            <div className="px-4 py-3 flex items-center justify-between gap-2">
              <CollapsibleTrigger className="flex items-center gap-2 group flex-1 min-w-0">
                <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-data-[state=closed]:-rotate-90" />
                <span className="text-sm font-medium">
                  {loadingK
                    ? t('nsfw.keywords', { defaultValue: 'Keywords' })
                    : t('nsfw.keywords_count', { count: keywords.length, defaultValue: '{{count}} keywords' })}
                </span>
              </CollapsibleTrigger>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button size="icon" className="h-7 w-7 shrink-0" onClick={() => setAddKeywordOpen(true)}>
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="top">{t('nsfw.add_keyword')}</TooltipContent>
              </Tooltip>
            </div>
            <CollapsibleContent>
              <ItemList
                items={keywordItems}
                loading={loadingK}
                emptyKey="nsfw.no_keywords"
                deletingId={deletingK}
                onEdit={(item) => setEditKeyword(keywords.find((k) => k.id === item.id) ?? null)}
                onDelete={(item) => removeKeyword(keywords.find((k) => k.id === item.id)!)}
              />
            </CollapsibleContent>
          </Collapsible>
        </Card>

        {/* Dialogs */}
        <EntryDialog
          open={addDomainOpen}
          title={t('nsfw.add_domain_title')}
          fieldLabel={t('nsfw.domain_field')}
          fieldPlaceholder={t('nsfw.domain_placeholder')}
          submitLabel={t('nsfw.add_btn')}
          onClose={() => setAddDomainOpen(false)}
          onSubmit={addDomain}
        />
        <EntryDialog
          open={addKeywordOpen}
          title={t('nsfw.add_keyword_title')}
          fieldLabel={t('nsfw.keyword_field')}
          fieldPlaceholder={t('nsfw.keyword_placeholder')}
          submitLabel={t('nsfw.add_btn')}
          onClose={() => setAddKeywordOpen(false)}
          onSubmit={addKeyword}
        />
        <EntryDialog
          open={!!editDomain}
          title={t('nsfw.edit_domain_title')}
          fieldLabel={t('nsfw.domain_field')}
          initialValue={editDomain?.domain ?? ''}
          initialNote={editDomain?.note ?? ''}
          submitLabel={t('common.save')}
          onClose={() => setEditDomain(null)}
          onSubmit={saveDomain}
        />
        <EntryDialog
          open={!!editKeyword}
          title={t('nsfw.edit_keyword_title')}
          fieldLabel={t('nsfw.keyword_field')}
          initialValue={editKeyword?.keyword ?? ''}
          initialNote={editKeyword?.note ?? ''}
          submitLabel={t('common.save')}
          onClose={() => setEditKeyword(null)}
          onSubmit={saveKeyword}
        />
        <ImportDialog
          open={importOpen}
          onClose={() => setImportOpen(false)}
          onDone={() => { loadDomains(); loadKeywords() }}
        />
      </div>
    </TooltipProvider>
  )
}
