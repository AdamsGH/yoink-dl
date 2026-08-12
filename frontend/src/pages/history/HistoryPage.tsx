import { useEffect, useState } from 'react'
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Clapperboard,
  Download,
  ExternalLink,
  Film,
  Images,
  MoreVertical,
  Music,
  RotateCcw,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { downloadsApi } from '@dl/api/downloads'
import { cn, formatBytes, formatDateCompact } from '@core/lib/utils'
import type { DownloadLog } from '@dl/types'
import { Button, Card, CardContent, CardHeader, CardTitle, DividedList, Input, Item, ItemActions, ItemContent, ItemDescription, ItemTitle, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Skeleton, SkeletonList, TooltipProvider } from '@ui'
import { EmptyState, PageContainer } from '@app'
import { toast } from '@core/components/ui/toast'
import { useFavicon } from '@dl/hooks/useFavicon'

type StatusFilter = 'all' | 'ok' | 'cached' | 'error'
type PeriodFilter = '7' | '30' | '90' | 'all'

const PAGE_SIZE = 25

function fmtSecs(secs: number): string {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = secs % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`
}

function tgMessageUrl(groupId: number, messageId: number, threadId?: number | null): string {
  const idStr = String(Math.abs(groupId))
  if (idStr.startsWith('100')) {
    const channelId = idStr.slice(3)
    if (threadId) return `https://t.me/c/${channelId}/${threadId}/${messageId}`
    return `https://t.me/c/${channelId}/${messageId}`
  }
  return ''
}

function stripWww(domain: string): string {
  return domain.replace(/^www\./, '')
}

function youtubeVideoId(url: string): string | null {
  try {
    const parsed = new URL(url)
    if (!/(^|\.)youtube\.com$|(^|\.)youtu\.be$/.test(parsed.hostname)) return null
    if (parsed.hostname === 'youtu.be') return parsed.pathname.slice(1) || null
    if (parsed.pathname === '/watch') return parsed.searchParams.get('v')
    const match = parsed.pathname.match(/^\/(?:shorts|embed|live)\/([^/?]+)/)
    return match?.[1] ?? null
  } catch {
    return null
  }
}

function dateKey(iso: string): string {
  const date = new Date(iso)
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

function dateHeading(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'long',
    year: new Date(iso).getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
  })
}

function Thumbnail({ item }: { item: DownloadLog }) {
  const [failed, setFailed] = useState(false)
  const videoId = youtubeVideoId(item.url)
  const src = videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : null

  if (!src || failed) return <MediaIcon item={item} />
  return (
    <div className="relative h-16 w-28 shrink-0 overflow-hidden rounded-md bg-muted">
      <img
        src={src}
        alt=""
        className="h-full w-full object-cover"
        loading="lazy"
        onError={() => setFailed(true)}
      />
      {item.duration != null && item.duration > 0 && (
        <span className="absolute bottom-1 right-1 rounded bg-black/80 px-1 py-0.5 text-[10px] font-semibold leading-none text-white">
          {fmtSecs(Math.round(item.duration))}
        </span>
      )}
    </div>
  )
}

// Shorten a raw URL to hostname + path stub for display
function shortenUrl(url: string): string {
  try {
    const u = new URL(url)
    const path = u.pathname.length > 20 ? u.pathname.slice(0, 20) + '...' : u.pathname
    return u.hostname + path
  } catch {
    return url.length > 40 ? url.slice(0, 40) + '...' : url
  }
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
      await downloadsApi.retry(item.id)
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
  const chips: { label: string; value: string; highlight?: boolean }[] = []

  if (type === 'clip') {
    chips.push({ label: t('history.clip'), value: `${fmtSecs(item.clip_start!)} - ${fmtSecs(item.clip_end!)}`, highlight: true })
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

  return (
    <div className="pt-1.5 pb-2 space-y-2 text-xs" onClick={(e) => e.stopPropagation()}>
      {item.error_msg && (
        <p className="text-destructive break-words">{item.error_msg}</p>
      )}

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

      {/* URL - truncated, tap to select all */}
      <div className="font-mono text-[11px] break-all text-muted-foreground bg-muted/50 rounded px-2 py-1.5 select-all leading-relaxed">
        {item.url}
      </div>

      <div className="flex flex-wrap gap-2 pt-0.5">
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

export default function HistoryPage() {
  const { t } = useTranslation()

  const [items, setItems] = useState<DownloadLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [initialLoading, setInitialLoading] = useState(true)
  const [fetching, setFetching] = useState(false)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [domains, setDomains] = useState<string[]>([])
  const [filtersOpen, setFiltersOpen] = useState(false)

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [domain, setDomain] = useState('_all')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [period, setPeriod] = useState<PeriodFilter>('all')

  const hasActive = debouncedSearch !== '' || domain !== '_all' || status !== 'all' || period !== 'all'
  const hasFilterActive = domain !== '_all' || status !== 'all' || period !== 'all'
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  useEffect(() => {
    const id = setTimeout(() => { setDebouncedSearch(search); setPage(1) }, 300)
    return () => clearTimeout(id)
  }, [search])

  useEffect(() => { setPage(1) }, [domain, status, period])

  useEffect(() => {
    downloadsApi.getDomains()
      .then(r => setDomains(r.data.domains))
      .catch(() => {})
  }, [])

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

    downloadsApi.list(params)
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
    <PageContainer>
    <TooltipProvider delayDuration={300}>
      <div className="space-y-3">

        {/* Search + filter toggle */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              placeholder={t('history.search_placeholder')}
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-9 h-9"
            />
            {search && (
              <button
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => { setSearch(''); setDebouncedSearch('') }}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <Button
            variant={hasFilterActive ? 'default' : 'outline'}
            size="sm"
            className="h-9 w-9 p-0 shrink-0"
            onClick={() => setFiltersOpen(o => !o)}
          >
            <SlidersHorizontal className="h-4 w-4" />
          </Button>
        </div>

        {/* Filters panel - shown when toggled */}
        {filtersOpen && (
          <div className="grid grid-cols-3 gap-2">
            <Select value={domain} onValueChange={v => { setDomain(v); setPage(1) }}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Domain" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="_all">{t('history.domain_label', { defaultValue: 'All domains' })}</SelectItem>
                {domains.map(d => <SelectItem key={d} value={d}>{stripWww(d)}</SelectItem>)}
              </SelectContent>
            </Select>

            <Select value={status} onValueChange={v => { setStatus(v as StatusFilter); setPage(1) }}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('history.status_all', { defaultValue: 'All' })}</SelectItem>
                <SelectItem value="ok">ok</SelectItem>
                <SelectItem value="cached">cached</SelectItem>
                <SelectItem value="error">error</SelectItem>
              </SelectContent>
            </Select>

            <Select value={period} onValueChange={v => { setPeriod(v as PeriodFilter); setPage(1) }}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('history.period_all', { defaultValue: 'All time' })}</SelectItem>
                <SelectItem value="7">7d</SelectItem>
                <SelectItem value="30">30d</SelectItem>
                <SelectItem value="90">90d</SelectItem>
              </SelectContent>
            </Select>
          </div>
        )}

        {/* List */}
        <Card>
          <CardHeader className="px-4 py-2.5">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-sm font-medium tabular-nums text-muted-foreground">
                {initialLoading ? '...' : (
                  <>
                    {total.toLocaleString()} {t('history.total_downloads').toLowerCase()}
                    {hasActive && <span className="ml-1.5 font-normal text-xs">{t('history.filtered')}</span>}
                  </>
                )}
              </CardTitle>
              {hasActive && (
                <Button variant="ghost" size="sm" className="h-6 px-2 text-xs text-muted-foreground" onClick={resetFilters}>
                  <X className="h-3 w-3 mr-1" />
                  {t('history.clear_all')}
                </Button>
              )}
            </div>
          </CardHeader>

          <CardContent className={cn('p-0 transition-opacity duration-150', fetching && !initialLoading && 'opacity-60')}>
            {initialLoading ? (
              <DividedList>
                <SkeletonList count={8}>{(i) => <HistoryItemSkeleton key={i} />}</SkeletonList>
              </DividedList>
            ) : items.length === 0 ? (
              <EmptyState message={hasActive ? t('history.no_results') : t('history.empty')} />
            ) : (
              <DividedList className="px-3 py-0">
                {items.map((item, index) => {
                  const isOpen = expanded === item.id
                  const showDate = index === 0 || dateKey(items[index - 1].created_at) !== dateKey(item.created_at)
                  const msgUrl = item.group_id && item.message_id
                    ? tgMessageUrl(item.group_id, item.message_id, item.thread_id)
                    : null
                  const displayTitle = item.title
                    ? item.title
                    : shortenUrl(item.url)

                  return (
                    <div key={item.id}>
                      {showDate && (
                        <div className="border-b border-border/60 px-1 pb-1.5 pt-3 text-xs font-semibold text-foreground first:pt-2">
                          {dateHeading(item.created_at)}
                        </div>
                      )}
                      <Item
                        size="sm"
                        className="py-2 rounded-none border-0 cursor-pointer select-none"
                        onClick={() => setExpanded(p => p === item.id ? null : item.id)}
                      >
                        <Thumbnail item={item} />
                        <ItemContent className="gap-0.5 min-w-0 self-stretch justify-center">
                          <ItemTitle className="line-clamp-2 text-sm leading-tight">
                            {displayTitle}
                          </ItemTitle>
                          <ItemDescription className="flex items-center gap-1.5 text-xs">
                            {item.domain && <span className="truncate">{stripWww(item.domain)}</span>}
                            <span className="text-muted-foreground/50">·</span>
                            <span className="shrink-0">{formatDateCompact(item.created_at)}</span>
                          </ItemDescription>
                          {item.status !== 'error' ? (
                            <span className="flex items-center gap-1 text-[11px] text-emerald-500">
                              <CheckCircle2 className="size-3" />
                              {item.status === 'cached' ? t('history.status_cached') : t('history.downloaded')}
                              {item.quality && <span className="text-muted-foreground">{item.quality}</span>}
                            </span>
                          ) : (
                            <span className="text-[11px] text-destructive">{t('history.status_error')}</span>
                          )}
                        </ItemContent>
                        <ItemActions className="gap-0.5 self-stretch items-center">
                          {msgUrl && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-8 shrink-0"
                              asChild
                              onClick={(e) => e.stopPropagation()}
                            >
                              <a href={msgUrl} target="_blank" rel="noopener noreferrer" aria-label={t('history.open_telegram')}>
                                <Download className="size-4" />
                              </a>
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 shrink-0"
                            onClick={(e) => { e.stopPropagation(); setExpanded(p => p === item.id ? null : item.id) }}
                            aria-label={t('history.more')}
                          >
                            <MoreVertical className="size-4" />
                          </Button>
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
              </DividedList>
            )}
          </CardContent>
        </Card>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {t('history.page_of', { page, total: totalPages })}
            </span>
            <div className="flex gap-1">
              <Button variant="outline" size="sm" className="h-8 w-8 p-0" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" className="h-8 w-8 p-0" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

      </div>
    </TooltipProvider>
    </PageContainer>
  )
}
