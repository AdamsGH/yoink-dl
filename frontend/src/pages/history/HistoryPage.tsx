import { useEffect, useState } from 'react'
import {
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Clapperboard,
  ExternalLink,
  Film,
  Images,
  Music,
  RotateCcw,
  Search,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { apiClient } from '@core/lib/api-client'
import { cn, formatBytes, formatDate } from '@core/lib/utils'
import type { PaginatedResponse } from '@core/types/api'
import type { DownloadLog, RetryResponse } from '@dl/types'
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Item, ItemActions, ItemContent, ItemDescription, ItemTitle, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Skeleton, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@ui'
import { SuccessBadge } from '@app'
import { toast } from '@core/components/ui/toast'

type StatusFilter = 'all' | 'ok' | 'cached' | 'error'
type PeriodFilter = '7' | '30' | '90' | 'all'

const PAGE_SIZE = 25

import { useFavicon } from '@dl/hooks/useFavicon'

function fmtSecs(secs: number): string {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = secs % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`
}

function tgMessageUrl(groupId: number, messageId: number, threadId?: number | null): string {
  // supergroup/channel: id starts with -100
  const idStr = String(Math.abs(groupId))
  if (idStr.startsWith('100')) {
    const channelId = idStr.slice(3) // strip the '100' prefix
    if (threadId) return `https://t.me/c/${channelId}/${threadId}/${messageId}`
    return `https://t.me/c/${channelId}/${messageId}`
  }
  // regular group - can't deep-link by message id
  return ''
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'ok') return <SuccessBadge>{status}</SuccessBadge>
  const variant = status === 'cached' ? 'secondary' : status === 'error' ? 'destructive' : 'outline'
  return <Badge variant={variant}>{status}</Badge>
}

function MediaIcon({ item }: { item: DownloadLog }) {
  const favicon = useFavicon(item.domain)
  const type = item.media_type

  const Icon =
    type === 'error'   ? AlertCircle :
    type === 'audio'   ? Music :
    type === 'gallery' ? Images :
    type === 'clip'    ? Clapperboard :
    Film

  const iconColor =
    type === 'error'   ? 'text-destructive' :
    type === 'audio'   ? 'text-violet-500' :
    type === 'gallery' ? 'text-blue-500' :
    type === 'clip'    ? 'text-amber-500' :
    'text-muted-foreground'

  return (
    <div className="relative size-8 shrink-0">
      <div className={cn('size-8 rounded-md bg-muted flex items-center justify-center', iconColor)}>
        <Icon className="size-4" />
      </div>
      {favicon && (
        <div className="absolute -bottom-0.5 -right-0.5 size-3.5 rounded-sm overflow-hidden">
          <img src={favicon} alt="" className="size-full object-cover" />
        </div>
      )}
    </div>
  )
}

function ExpandedDetails({ item }: { item: DownloadLog }) {
  const { t } = useTranslation()
  const [retrying, setRetrying] = useState(false)

  const retry = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setRetrying(true)
    try {
      await apiClient.post<RetryResponse>(`/dl/downloads/${item.id}/retry`)
      toast.success(t('history.retry_ok'))
    } catch {
      toast.error(t('history.retry_error'))
    } finally {
      setRetrying(false)
    }
  }

  const msgUrl = item.group_id && item.message_id
    ? tgMessageUrl(item.group_id, item.message_id, item.thread_id)
    : null

  const type = item.media_type

  // Meta chips: key-value pairs relevant to this type
  const chips: { label: string; value: string; highlight?: boolean }[] = []

  if (type === 'clip') {
    chips.push({ label: t('history.clip'), value: `${fmtSecs(item.clip_start!)} → ${fmtSecs(item.clip_end!)}`, highlight: true })
    if (item.quality) chips.push({ label: t('history.quality'), value: item.quality })
    if (item.duration != null && item.duration > 0) chips.push({ label: t('history.duration'), value: fmtSecs(Math.round(item.duration)) })
    if (item.file_size != null) chips.push({ label: t('history.size'), value: formatBytes(item.file_size) })
  } else if (type === 'video' || type === 'error') {
    if (item.quality) chips.push({ label: t('history.quality'), value: item.quality })
    if (item.duration != null && item.duration > 0) chips.push({ label: t('history.duration'), value: fmtSecs(Math.round(item.duration)) })
    if (item.file_size != null) chips.push({ label: t('history.size'), value: formatBytes(item.file_size) })
  } else if (type === 'audio') {
    if (item.duration != null && item.duration > 0) chips.push({ label: t('history.duration'), value: fmtSecs(Math.round(item.duration)) })
    if (item.file_size != null) chips.push({ label: t('history.size'), value: formatBytes(item.file_size) })
  } else if (type === 'gallery') {
    if (item.file_count != null) chips.push({ label: t('history.file_count'), value: String(item.file_count) })
    if (item.file_size != null) chips.push({ label: t('history.size'), value: formatBytes(item.file_size) })
  }

  if (item.group_title) chips.push({ label: t('history.group'), value: item.group_title })
  else if (item.group_id) chips.push({ label: t('history.group'), value: String(item.group_id) })

  return (
    <div className="pt-2 pb-1 space-y-2.5 text-xs" onClick={(e) => e.stopPropagation()}>
      {/* Error message */}
      {item.error_msg && (
        <p className="text-destructive break-all">{item.error_msg}</p>
      )}

      {/* Meta chips */}
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map(c => (
            <span
              key={c.label}
              className={cn(
                'inline-flex items-center gap-1 rounded px-1.5 py-0.5',
                c.highlight
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'bg-muted text-muted-foreground'
              )}
            >
              <span className="opacity-60">{c.label}</span>
              <span className="text-foreground">{c.value}</span>
            </span>
          ))}
        </div>
      )}

      {/* URL */}
      <div className="font-mono break-all text-muted-foreground bg-muted/50 rounded px-2 py-1.5 select-all">
        {item.url}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {item.status !== 'error' && (
          <Button
            size="sm" variant="outline"
            className="h-7 text-xs gap-1.5"
            disabled={retrying}
            onClick={retry}
          >
            <RotateCcw className={cn('h-3.5 w-3.5', retrying && 'animate-spin')} />
            {retrying ? t('history.queuing') : t('history.redownload')}
          </Button>
        )}
        {msgUrl && (
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1.5" asChild>
            <a href={msgUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-3.5 w-3.5" />
              {t('history.open_telegram')}
            </a>
          </Button>
        )}
      </div>
    </div>
  )
}

function HistoryItemSkeleton() {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5">
      <Skeleton className="size-8 rounded-md shrink-0" />
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-3.5 w-48" />
        <Skeleton className="h-3 w-28" />
      </div>
      <Skeleton className="h-5 w-12 shrink-0" />
    </div>
  )
}

function buildDescription(item: DownloadLog): string {
  const parts: string[] = []
  if (item.domain) parts.push(item.domain)
  parts.push(formatDate(item.created_at))
  return parts.join(' · ')
}

export default function HistoryPage() {
  const { t } = useTranslation()

  const [items, setItems] = useState<DownloadLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [initialLoading, setInitialLoading] = useState(true)
  const [fetching, setFetching] = useState(false)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [domains, setDomains] = useState<string[]>([])

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [domain, setDomain] = useState('_all')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [period, setPeriod] = useState<PeriodFilter>('all')

  const hasActive = debouncedSearch !== '' || domain !== '_all' || status !== 'all' || period !== 'all'
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // 300ms debounce on search
  useEffect(() => {
    const id = setTimeout(() => { setDebouncedSearch(search); setPage(1) }, 300)
    return () => clearTimeout(id)
  }, [search])

  // Reset page when filters change
  useEffect(() => { setPage(1) }, [domain, status, period])

  // Load domains once
  useEffect(() => {
    apiClient.get<{ domains: string[] }>('/dl/downloads/domains')
      .then(r => setDomains(r.data.domains))
      .catch(() => {})
  }, [])

  // Main load
  useEffect(() => {
    setFetching(true)
    const params: Record<string, string | number> = {
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    }
    if (debouncedSearch) params.search = debouncedSearch
    if (domain !== '_all') params.domain = domain
    if (status !== 'all') params.status = status
    if (period !== 'all') {
      const from = new Date()
      from.setDate(from.getDate() - Number(period))
      params.date_from = from.toISOString().slice(0, 10)
    }

    apiClient.get<PaginatedResponse<DownloadLog>>('/dl/downloads', { params })
      .then(res => { setItems(res.data.items); setTotal(res.data.total) })
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => { setFetching(false); setInitialLoading(false) })
  }, [page, debouncedSearch, domain, status, period, t])

  const resetFilters = () => {
    setSearch(''); setDebouncedSearch('')
    setDomain('_all'); setStatus('all'); setPeriod('all')
    setPage(1)
  }

  return (
    <TooltipProvider delayDuration={300}>
      <div className="space-y-3">
        {/* Search always on top */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            placeholder={t('history.search_placeholder')}
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9 h-9"
          />
        </div>

        {/* Filters row */}
        <div className="flex gap-2">
          <Select value={domain} onValueChange={v => { setDomain(v); setPage(1) }}>
            <SelectTrigger className="h-8 flex-1 text-xs">
              <SelectValue placeholder={t('history.domain_label')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_all">{t('history.domain_label', { defaultValue: 'All domains' })}</SelectItem>
              {domains.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}
            </SelectContent>
          </Select>

          <Select value={status} onValueChange={v => { setStatus(v as StatusFilter); setPage(1) }}>
            <SelectTrigger className="h-8 w-24 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('history.status_all')}</SelectItem>
              <SelectItem value="ok">ok</SelectItem>
              <SelectItem value="cached">cached</SelectItem>
              <SelectItem value="error">error</SelectItem>
            </SelectContent>
          </Select>

          <Select value={period} onValueChange={v => { setPeriod(v as PeriodFilter); setPage(1) }}>
            <SelectTrigger className="h-8 w-20 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('history.period_all')}</SelectItem>
              <SelectItem value="7">7d</SelectItem>
              <SelectItem value="30">30d</SelectItem>
              <SelectItem value="90">90d</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* List */}
        <Card>
          <CardHeader className="px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-sm font-medium tabular-nums">
                {initialLoading ? t('history.total_downloads') : (
                  <>
                    {total.toLocaleString()} {t('history.total_downloads').toLowerCase()}
                    {hasActive && <span className="ml-1.5 text-muted-foreground font-normal text-xs">{t('history.filtered')}</span>}
                  </>
                )}
              </CardTitle>
              {hasActive && (
                <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-muted-foreground" onClick={resetFilters}>
                  {t('history.clear_all')}
                </Button>
              )}
            </div>
          </CardHeader>

          <CardContent className={cn('p-0 transition-opacity duration-150', fetching && !initialLoading && 'opacity-60')}>
            {initialLoading ? (
              <div className="divide-y divide-border px-3 py-1">
                {Array.from({ length: 8 }).map((_, i) => <HistoryItemSkeleton key={i} />)}
              </div>
            ) : items.length === 0 ? (
              <div className="flex justify-center py-12 text-muted-foreground text-sm">
                {hasActive ? t('history.no_results') : t('history.empty')}
              </div>
            ) : (
              <div className="divide-y divide-border px-3 py-1">
                {items.map(item => {
                  const isOpen = expanded === item.id
                  const msgUrl = item.group_id && item.message_id
                    ? tgMessageUrl(item.group_id, item.message_id, item.thread_id)
                    : null

                  return (
                    <div key={item.id}>
                      <Item
                        size="sm"
                        className="py-2.5 rounded-none border-0 cursor-pointer"
                        onClick={() => setExpanded(p => p === item.id ? null : item.id)}
                      >
                        <MediaIcon item={item} />
                        <ItemContent>
                          <ItemTitle className="line-clamp-1">
                            {item.title ?? item.url}
                          </ItemTitle>
                          <ItemDescription>{buildDescription(item)}</ItemDescription>
                        </ItemContent>
                        <ItemActions>
                          <StatusBadge status={item.status} />
                          {msgUrl && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost" size="icon"
                                  className="h-7 w-7 shrink-0"
                                  onClick={e => e.stopPropagation()}
                                  asChild
                                >
                                  <a href={msgUrl} target="_blank" rel="noopener noreferrer">
                                    <ExternalLink className="h-3.5 w-3.5" />
                                  </a>
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>{t('history.open_telegram')}</TooltipContent>
                            </Tooltip>
                          )}
                          <button className="text-muted-foreground ml-0.5" onClick={e => { e.stopPropagation(); setExpanded(p => p === item.id ? null : item.id) }}>
                            {isOpen
                              ? <ChevronUp className="h-3.5 w-3.5" />
                              : <ChevronDown className="h-3.5 w-3.5" />}
                          </button>
                        </ItemActions>
                      </Item>
                      {isOpen && (
                        <div className="px-3 pb-1">
                          <ExpandedDetails item={item} />
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {t('history.page_of', { page, total: totalPages })}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                {t('history.prev')}
              </Button>
              <Button variant="outline" size="sm" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>
                {t('history.next')}
              </Button>
            </div>
          </div>
        )}
      </div>
    </TooltipProvider>
  )
}
