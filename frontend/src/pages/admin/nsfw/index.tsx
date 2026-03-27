import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AxiosError } from 'axios'
import { Download, Pencil, Plus, ShieldAlert, Trash2, Upload } from 'lucide-react'


import { apiClient } from '@core/lib/api-client'
import { formatDate } from '@core/lib/utils'
import type { NsfwDomain, NsfwKeyword, NsfwCheckResponse } from '@dl/types'
import { Badge } from '@core/components/ui/badge'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@core/components/ui/dialog'
import { Input } from '@core/components/ui/input'
import { Label } from '@core/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@core/components/ui/table'
import { toast } from '@core/components/ui/toast'

interface AddDialogProps {
  open: boolean
  title: string
  fieldLabel: string
  fieldPlaceholder: string
  onClose: () => void
  onAdd: (value: string, note: string) => Promise<void>
}

function AddDialog({ open, title, fieldLabel, fieldPlaceholder, onClose, onAdd }: AddDialogProps) {
  const { t } = useTranslation()
  const [value, setValue] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  const handleAdd = async () => {
    if (!value.trim()) return
    setSaving(true)
    try {
      await onAdd(value.trim(), note.trim())
      setValue('')
      setNote('')
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => { if (!o) { setValue(''); setNote(''); onClose() } }}>
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
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t('nsfw.note_optional')}</Label>
            <Input
              {...{placeholder: t('nsfw.note_placeholder')}}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleAdd} disabled={saving || !value.trim()}>
            {saving ? t('nsfw.adding') : t('nsfw.add_btn')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface EditDialogProps {
  open: boolean
  title: string
  fieldLabel: string
  initial: { value: string; note: string }
  onClose: () => void
  onSave: (value: string, note: string) => Promise<void>
}

function EditDialog({ open, title, fieldLabel, initial, onClose, onSave }: EditDialogProps) {
  const { t } = useTranslation()
  const [value, setValue] = useState(initial.value)
  const [note, setNote] = useState(initial.note)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setValue(initial.value)
    setNote(initial.note)
  }, [initial.value, initial.note])

  const handleSave = async () => {
    if (!value.trim()) return
    setSaving(true)
    try {
      await onSave(value.trim(), note.trim())
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => { if (!o) onClose() }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>{fieldLabel}</Label>
            <Input value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
          </div>
          <div className="space-y-1.5">
            <Label>{t('nsfw.note_optional')}</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} disabled={saving || !value.trim()}>
            {saving ? t('common.loading') : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ImportDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [json, setJson] = useState('')
  const [importing, setImporting] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback((f: File | null | undefined) => {
    if (!f) return
    const reader = new FileReader()
    reader.onload = (e) => setJson(e.target?.result as string ?? '')
    reader.readAsText(f)
  }, [])

  const handleImport = async () => {
    let parsed: { domains?: { domain: string; note?: string }[]; keywords?: { keyword: string; note?: string }[] }
    try {
      parsed = JSON.parse(json)
    } catch {
      toast.error(t('common.error'))
      return
    }

    setImporting(true)
    try {
      await apiClient.post<{ domains_added: number; keywords_added: number }>('/dl/nsfw/import', {
        domains: parsed.domains ?? [],
        keywords: parsed.keywords ?? [],
      })
      toast.success(t('nsfw.added_ok'))
      setJson('')
      onClose()
      onDone()
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail
      toast.error(detail ?? t('nsfw.add_error'))
    } finally {
      setImporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => { if (!o) { setJson(''); onClose() } }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('nsfw.import')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Paste JSON or load a file. Expected format:
          </p>
          <pre className="rounded bg-muted p-2 text-xs overflow-x-auto">
{`{
  "domains": [{ "domain": "example.com", "note": "..." }],
  "keywords": [{ "keyword": "word", "note": "..." }]
}`}
          </pre>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}>
              <Upload className="mr-1.5 h-3.5 w-3.5" /> Load file
            </Button>
            <input ref={fileRef} type="file" accept=".json" className="hidden" onChange={(e) => handleFile(e.target.files?.[0])} />
          </div>
          <textarea
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
            rows={8}
            placeholder='{"domains": [...], "keywords": [...]}'
            value={json}
            onChange={(e) => setJson(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleImport} disabled={importing || !json.trim()}>
            {importing ? t('common.loading') : t('nsfw.import')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

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
        title: title.trim(),
        description: description.trim(),
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
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4" />
          {t('nsfw.check_title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="check-url">{t('nsfw.check_title')}</Label>
          <Input
            id="check-url"
            placeholder="https://example.com/video/..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && check()}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="check-title">Title (optional)</Label>
            <Input id="check-title" placeholder="Video title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="check-desc">{t('nsfw.check_desc_label')}</Label>
            <Input id="check-desc" placeholder="..." value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={check} disabled={checking || !url.trim()}>
            {checking ? t('nsfw.checking') : t('nsfw.check_btn')}
          </Button>
          {result && (
            <div className="flex items-center gap-2 text-sm">
              <Badge variant={result.is_nsfw ? 'destructive' : 'success'}>
                {result.is_nsfw ? 'NSFW' : 'clean'}
              </Badge>
              {result.matched_domain && (
                <span className="font-mono text-xs text-muted-foreground">domain: {result.matched_domain}</span>
              )}
              {result.matched_keywords.length > 0 && (
                <span className="font-mono text-xs text-muted-foreground">keywords: {result.matched_keywords.join(', ')}</span>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export default function AdminNsfwPage() {
  const { t } = useTranslation()
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

  const loadDomains = () => {
    setLoadingD(true)
    apiClient.get<NsfwDomain[]>('/dl/nsfw/domains')
      .then((r) => setDomains(r.data))
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => setLoadingD(false))
  }

  const loadKeywords = () => {
    setLoadingK(true)
    apiClient.get<NsfwKeyword[]>('/dl/nsfw/keywords')
      .then((r) => setKeywords(r.data))
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => setLoadingK(false))
  }

  const loadAll = () => { loadDomains(); loadKeywords() }
  useEffect(loadAll, [])

  const removeDomain = async (id: number) => {
    if (!confirm('Remove this domain?')) return
    setDeletingD(id)
    try {
      await apiClient.delete(`/dl/nsfw/domains/${id}`)
      toast.success(t('nsfw.removed'))
      loadDomains()
    } catch {
      toast.error(t('nsfw.remove_error'))
    } finally {
      setDeletingD(null)
    }
  }

  const removeKeyword = async (id: number) => {
    if (!confirm('Remove this keyword?')) return
    setDeletingK(id)
    try {
      await apiClient.delete(`/dl/nsfw/keywords/${id}`)
      toast.success(t('nsfw.removed'))
      loadKeywords()
    } catch {
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
      a.href = url
      a.download = 'nsfw-export.json'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error(t('common.load_error'))
    }
  }

  return (
    <div className="space-y-4">
      <CheckPanel />

      {/* Domains */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 gap-3 flex-wrap">
          <CardTitle className="text-sm font-medium">
            {loadingD ? '...' : t('nsfw.domains_count', { count: domains.length, defaultValue: '{{count}} domains' })}
          </CardTitle>
          <div className="flex gap-1.5">
            <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
              <Upload className="mr-1.5 h-3.5 w-3.5" /> {t('nsfw.import')}
            </Button>
            <Button variant="outline" size="sm" onClick={exportJson}>
              <Download className="mr-1.5 h-3.5 w-3.5" /> {t('nsfw.export', { defaultValue: 'Export' })}
            </Button>
            <Button size="sm" onClick={() => setAddDomainOpen(true)}>
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              {t('nsfw.add_domain')}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {loadingD ? (
            <div className="flex justify-center py-10 text-muted-foreground">{t('common.loading')}</div>
          ) : domains.length === 0 ? (
            <div className="flex justify-center py-10 text-muted-foreground">{t('nsfw.no_domains')}</div>
          ) : (
            <>
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t('nsfw.col_domain')}</TableHead>
                      <TableHead>{t('nsfw.col_note')}</TableHead>
                      <TableHead>{t('nsfw.col_added')}</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {domains.map((d) => (
                      <TableRow key={d.id}>
                        <TableCell className="font-mono text-sm">{d.domain}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{d.note ?? '-'}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{formatDate(d.created_at)}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Button variant="ghost" size="icon" onClick={() => setEditDomain(d)}>
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive"
                              disabled={deletingD === d.id} onClick={() => removeDomain(d.id)}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="md:hidden divide-y divide-border">
                {domains.map((d) => (
                  <div key={d.id} className="flex items-center justify-between px-4 py-3 gap-3">
                    <div className="min-w-0">
                      <p className="font-mono text-sm">{d.domain}</p>
                      {d.note && <p className="text-xs text-muted-foreground">{d.note}</p>}
                      <p className="text-xs text-muted-foreground">{formatDate(d.created_at)}</p>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <Button variant="ghost" size="icon" onClick={() => setEditDomain(d)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive"
                        disabled={deletingD === d.id} onClick={() => removeDomain(d.id)}>
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

      {/* Keywords */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-sm font-medium">
            {loadingK ? '...' : t('nsfw.keywords_count', { count: keywords.length, defaultValue: '{{count}} keywords' })}
          </CardTitle>
          <Button size="sm" onClick={() => setAddKeywordOpen(true)}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            {t('nsfw.add_keyword')}
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {loadingK ? (
            <div className="flex justify-center py-10 text-muted-foreground">{t('common.loading')}</div>
          ) : keywords.length === 0 ? (
            <div className="flex justify-center py-10 text-muted-foreground">{t('nsfw.no_keywords')}</div>
          ) : (
            <>
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t('nsfw.col_keyword')}</TableHead>
                      <TableHead>{t('nsfw.col_note')}</TableHead>
                      <TableHead>{t('nsfw.col_added')}</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {keywords.map((k) => (
                      <TableRow key={k.id}>
                        <TableCell className="font-mono text-sm">{k.keyword}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{k.note ?? '-'}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{formatDate(k.created_at)}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Button variant="ghost" size="icon" onClick={() => setEditKeyword(k)}>
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive"
                              disabled={deletingK === k.id} onClick={() => removeKeyword(k.id)}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="md:hidden divide-y divide-border">
                {keywords.map((k) => (
                  <div key={k.id} className="flex items-center justify-between px-4 py-3 gap-3">
                    <div className="min-w-0">
                      <p className="font-mono text-sm">{k.keyword}</p>
                      {k.note && <p className="text-xs text-muted-foreground">{k.note}</p>}
                      <p className="text-xs text-muted-foreground">{formatDate(k.created_at)}</p>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <Button variant="ghost" size="icon" onClick={() => setEditKeyword(k)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive"
                        disabled={deletingK === k.id} onClick={() => removeKeyword(k.id)}>
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

      <AddDialog
        open={addDomainOpen}
        {...{title: t('nsfw.add_domain_title')}}
        {...{fieldLabel: t('nsfw.domain_field')}}
        {...{fieldPlaceholder: t('nsfw.domain_placeholder')}}
        onClose={() => setAddDomainOpen(false)}
        onAdd={addDomain}
      />
      <AddDialog
        open={addKeywordOpen}
        {...{title: t('nsfw.add_keyword_title')}}
        {...{fieldLabel: t('nsfw.keyword_field')}}
        {...{fieldPlaceholder: t('nsfw.keyword_placeholder')}}
        onClose={() => setAddKeywordOpen(false)}
        onAdd={addKeyword}
      />
      <EditDialog
        open={!!editDomain}
        {...{title: t('nsfw.edit_domain_title')}}
        {...{fieldLabel: t('nsfw.domain_field')}}
        initial={{ value: editDomain?.domain ?? '', note: editDomain?.note ?? '' }}
        onClose={() => setEditDomain(null)}
        onSave={saveDomain}
      />
      <EditDialog
        open={!!editKeyword}
        {...{title: t('nsfw.edit_keyword_title')}}
        {...{fieldLabel: t('nsfw.keyword_field')}}
        initial={{ value: editKeyword?.keyword ?? '', note: editKeyword?.note ?? '' }}
        onClose={() => setEditKeyword(null)}
        onSave={saveKeyword}
      />
      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onDone={loadAll}
      />
    </div>
  )
}
