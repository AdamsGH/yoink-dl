import { useEffect, useRef, useState } from 'react'
import { format } from 'date-fns'
import { CalendarIcon, ExternalLink, RotateCcw } from 'lucide-react'
import type { DateRange } from 'react-day-picker'

import { apiClient } from '@core/lib/api-client'
import { cn, formatBytes, formatDate } from '@core/lib/utils'
import type { PaginatedResponse } from '@core/types/api'
import type { DownloadLog, RetryResponse } from '@dl/types'
import { Badge } from '@core/components/ui/badge'
import { Button } from '@core/components/ui/button'
import { Calendar } from '@core/components/ui/calendar'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Input } from '@core/components/ui/input'
import { Label } from '@core/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@core/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@core/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@core/components/ui/table'
import { toast } from '@core/components/ui/toast'

type StatusFilter = 'all' | 'ok' | 'cached' | 'error'

interface Filters {
  search: string
  domain: string
  status: StatusFilter
  dateRange?: DateRange
}

const DEFAULT_FILTERS: Filters = { search: '', domain: '', status: 'all' }
const PAGE_SIZE = 20

function StatusBadge({ status }: { status: string }) {
  const variant =
    status === 'ok' ? 'success' :
    status === 'cached' ? 'secondary' :
    status === 'error' ? 'destructive' : 'outline'
  return <Badge variant={variant}>{status}</Badge>
}

function fmtSecs(secs: number): string {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = secs % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`
}

function tgMessageUrl(groupId: number, messageId: number, threadId?: number | null): string {
  // Supergroup IDs are negative with -100 prefix; strip to get channel ID
  const channelId = Math.abs(groupId) - 1_000_000_000_000
  // Format: t.me/c/{channel}/{thread}/{message} when in a topic,
  //         t.me/c/{channel}/{message} for main chat
  if (threadId) return `https://t.me/c/${channelId}/${threadId}/${messageId}`
  return `https://t.me/c/${channelId}/${messageId}`
}

function ExpandedRow({ item }: { item: DownloadLog }) {
  const [retrying, setRetrying] = useState(false)

  const retry = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setRetrying(true)
    try {
      await apiClient.post<RetryResponse>(`/dl/downloads/${item.id}/retry`)
      toast.success('URL sent to bot  - check your Telegram chat')
    } catch {
      toast.error('Failed to queue retry')
    } finally {
      setRetrying(false)
    }
  }

  const msgUrl = item.group_id && item.message_id
    ? tgMessageUrl(item.group_id, item.message_id, item.thread_id)
    : null

  return (
    <div className="space-y-3" onClick={(e) => e.stopPropagation()}>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
        <div className="col-span-full">
          <span className="text-muted-foreground">URL</span>
          <p className="font-mono break-all">{item.url}</p>
        </div>
        {item.clip_start != null && item.clip_end != null && (
          <div>
            <span className="text-muted-foreground">Clip</span>
            <p className="font-mono">{fmtSecs(item.clip_start)} → {fmtSecs(item.clip_end)}</p>
          </div>
        )}
        {item.duration != null && (
          <div>
            <span className="text-muted-foreground">Duration</span>
            <p>{fmtSecs(Math.round(item.duration))}</p>
          </div>
        )}
        {item.group_id != null && (
          <div>
            <span className="text-muted-foreground">Group</span>
            <p>{item.group_title ?? <span className="font-mono">{item.group_id}</span>}
              {item.thread_id != null && <span className="text-muted-foreground"> / thread {item.thread_id}</span>}
            </p>
          </div>
        )}
        {item.error_msg && (
          <div className="col-span-full">
            <span className="text-muted-foreground">Error</span>
            <p className="text-destructive break-all">{item.error_msg}</p>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs gap-1.5"
          disabled={retrying}
          onClick={retry}
        >
          <RotateCcw className={cn('h-3.5 w-3.5', retrying && 'animate-spin')} />
          {retrying ? 'Queuing…' : 'Re-download'}
        </Button>
        {msgUrl && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs gap-1.5"
            asChild
          >
            <a href={msgUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-3.5 w-3.5" />
              Open in Telegram
            </a>
          </Button>
        )}
      </div>
    </div>
  )
}

export default function HistoryPage() {
  const [items, setItems] = useState<DownloadLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [applied, setApplied] = useState<Filters>(DEFAULT_FILTERS)
  const [expanded, setExpanded] = useState<number | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setLoading(true)
    const params: Record<string, string | number> = {
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    }
    if (applied.search) params.search = applied.search
    if (applied.domain) params.domain = applied.domain
    if (applied.status !== 'all') params.status = applied.status
    if (applied.dateRange?.from) params.date_from = format(applied.dateRange.from, 'yyyy-MM-dd')
    if (applied.dateRange?.to) params.date_to = format(applied.dateRange.to, 'yyyy-MM-dd')

    apiClient
      .get<PaginatedResponse<DownloadLog>>('/dl/downloads', { params })
      .then((res) => { setItems(res.data.items); setTotal(res.data.total) })
      .catch(() => toast.error('Failed to load history'))
      .finally(() => setLoading(false))
  }, [page, applied])

  const apply = () => { setPage(1); setApplied(filters) }

  const resetFilters = () => {
    setFilters(DEFAULT_FILTERS)
    setPage(1)
    setApplied(DEFAULT_FILTERS)
  }

  const hasActive =
    !!applied.search || !!applied.domain ||
    applied.status !== 'all' || !!applied.dateRange?.from

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const dateLabel = filters.dateRange?.from
    ? filters.dateRange.to
      ? `${format(filters.dateRange.from, 'MMM d')}  - ${format(filters.dateRange.to, 'MMM d, yyyy')}`
      : format(filters.dateRange.from, 'MMM d, yyyy')
    : 'Date range'

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Download History</h1>

      <Card>
        <CardContent className="pt-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Search title / URL</Label>
              <Input
                ref={searchRef}
                placeholder="youtube.com, video title…"
                value={filters.search}
                onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && apply()}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Domain</Label>
              <Input
                placeholder="youtube.com"
                value={filters.domain}
                onChange={(e) => setFilters((f) => ({ ...f, domain: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && apply()}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Status</Label>
              <Select value={filters.status} onValueChange={(v: string) => setFilters((f) => ({ ...f, status: v as StatusFilter }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="ok">OK</SelectItem>
                  <SelectItem value="cached">Cached</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" className={cn('h-9 justify-start gap-2 font-normal', !filters.dateRange?.from && 'text-muted-foreground')}>
                  <CalendarIcon className="h-4 w-4 opacity-50" />
                  {dateLabel}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar mode="range" selected={filters.dateRange} onSelect={(r: DateRange | undefined) => setFilters((f) => ({ ...f, dateRange: r }))} initialFocus />
              </PopoverContent>
            </Popover>
            {filters.dateRange?.from && (
              <Button size="sm" variant="ghost" className="h-9 text-muted-foreground" onClick={() => setFilters((f) => ({ ...f, dateRange: undefined }))}>✕</Button>
            )}
            <Button size="sm" className="h-9" onClick={apply}>Apply</Button>
            {hasActive && <Button size="sm" variant="outline" className="h-9" onClick={resetFilters}>Clear all</Button>}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            {total.toLocaleString()} download{total !== 1 ? 's' : ''}
            {hasActive && <span className="ml-2 text-sm font-normal text-muted-foreground">(filtered)</span>}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex justify-center py-12 text-muted-foreground">Loading…</div>
          ) : items.length === 0 ? (
            <div className="flex justify-center py-12 text-muted-foreground">
              {hasActive ? 'No results match your filters' : 'No downloads yet'}
            </div>
          ) : (
            <>
              {/* Desktop table */}
              <div className="hidden md:block overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="whitespace-nowrap">Date</TableHead>
                      <TableHead>Domain</TableHead>
                      <TableHead>Title / URL</TableHead>
                      <TableHead>Quality</TableHead>
                      <TableHead>Size</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item) => (
                      <>
                        <TableRow
                          key={item.id}
                          className="cursor-pointer"
                          onClick={() => setExpanded((p) => p === item.id ? null : item.id)}
                        >
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDate(item.created_at)}</TableCell>
                          <TableCell className="text-sm">{item.domain ?? '-'}</TableCell>
                          <TableCell className="max-w-[220px]">
                            <p className="truncate text-sm">{item.title ?? item.url}</p>
                            {item.title && <p className="truncate text-xs text-muted-foreground">{item.url}</p>}
                          </TableCell>
                          <TableCell className="text-sm">{item.quality ?? '-'}</TableCell>
                          <TableCell className="text-sm">{formatBytes(item.file_size)}</TableCell>
                          <TableCell><StatusBadge status={item.status} /></TableCell>
                        </TableRow>
                        {expanded === item.id && (
                          <TableRow key={`exp-${item.id}`} className="bg-muted/30 hover:bg-muted/30">
                            <TableCell colSpan={6} className="px-4 py-3">
                              <ExpandedRow item={item} />
                            </TableCell>
                          </TableRow>
                        )}
                      </>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Mobile cards */}
              <div className="md:hidden divide-y divide-border">
                {items.map((item) => (
                  <div
                    key={item.id}
                    className="px-4 py-3 space-y-1.5 cursor-pointer"
                    onClick={() => setExpanded((p) => p === item.id ? null : item.id)}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium leading-snug line-clamp-2 flex-1">
                        {item.title ?? item.url}
                      </p>
                      <StatusBadge status={item.status} />
                    </div>
                    {item.title && (
                      <p className="text-xs text-muted-foreground truncate">{item.url}</p>
                    )}
                    <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
                      <span>{item.domain ?? '-'}</span>
                      {item.quality && <span>{item.quality}</span>}
                      {item.file_size != null && <span>{formatBytes(item.file_size)}</span>}
                      <span>{formatDate(item.created_at)}</span>
                    </div>
                    {expanded === item.id && (
                      <div className="pt-2 border-t border-border">
                        <ExpandedRow item={item} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <Button variant="outline" size="sm" disabled={page === totalPages} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}
    </div>
  )
}
