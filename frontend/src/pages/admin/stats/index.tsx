import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

import { apiClient } from '@core/lib/api-client'
import { cn } from '@core/lib/utils'
import type { StatsOverview } from '@dl/types'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Skeleton } from '@core/components/ui/skeleton'

const CTP_FALLBACKS = [
  '#8aadf4', '#c6a0f6', '#ed8796', '#a6da95', '#f5a97f',
  '#91d7e3', '#eed49f', '#f5bde6', '#8bd5ca', '#b7bdf8',
]
const CTP_VARS = [
  '--ctp-blue', '--ctp-mauve', '--ctp-red', '--ctp-green', '--ctp-peach',
  '--ctp-sky', '--ctp-yellow', '--ctp-pink', '--ctp-teal', '--ctp-lavender',
]

let _chartColors: string[] | null = null
function chartColors(): string[] {
  if (_chartColors) return _chartColors
  const style = getComputedStyle(document.documentElement)
  _chartColors = CTP_VARS.map((name, i) => style.getPropertyValue(name).trim() || CTP_FALLBACKS[i])
  return _chartColors
}

const PERIOD_OPTIONS = [7, 30, 90] as const

type Period = (typeof PERIOD_OPTIONS)[number]

function PeriodToggle({ value, onChange }: { value: Period; onChange: (v: Period) => void }) {
  const { t } = useTranslation()
  return (
    <div className="flex rounded-md border overflow-hidden">
      {PERIOD_OPTIONS.map((opt) => (
        <Button
          key={opt}
          variant="ghost"
          size="sm"
          onClick={() => onChange(opt)}
          className={cn(
            'rounded-none border-0 px-3 h-8 text-xs',
            value === opt
              ? 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
              : 'text-muted-foreground',
          )}
        >
          {t(`admin_stats.period_${opt}` as Parameters<typeof t>[0])}
        </Button>
      ))}
    </div>
  )
}

function StatCard({ label, value, sub, variant = 'default' }: {
  label: string
  value: string | number
  sub?: string
  variant?: 'default' | 'danger' | 'success'
}) {
  return (
    <Card className="select-none">
      <CardContent className="pt-5">
        <div className={cn(
          'text-3xl font-bold tabular-nums',
          variant === 'danger'  ? 'text-destructive' :
          variant === 'success' ? 'text-green-500'   : 'text-primary',
        )}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </div>
        <div className="mt-1 text-sm text-muted-foreground">{label}</div>
        {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  )
}

function StatCardSkeleton() {
  return (
    <Card>
      <CardContent className="pt-5 space-y-2">
        <Skeleton className="h-9 w-20" />
        <Skeleton className="h-4 w-28" />
      </CardContent>
    </Card>
  )
}

export default function AdminStatsPage() {
  const { t } = useTranslation()
  const [stats, setStats] = useState<StatsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [period, setPeriod] = useState<Period>(30)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setLoading(true)
    setError(null)

    apiClient
      .get<StatsOverview>('/dl/stats/overview', {
        params: { days: period },
        signal: ctrl.signal,
      })
      .then((res) => { setStats(res.data) })
      .catch((err) => {
        if (err?.code === 'ERR_CANCELED') return
        const status = err?.response?.status
        setError(status === 401 ? t('admin_stats.err_unauthorized') : status === 403 ? t('admin_stats.err_forbidden') : t('admin_stats.err_load'))
      })
      .finally(() => { setLoading(false) })

    return () => ctrl.abort()
  }, [period])

  const cacheRate = stats && stats.downloads_today > 0
    ? Math.round((stats.cache_hits_today / stats.downloads_today) * 100)
    : 0

  const domainSlice = stats?.top_domains.slice(0, 6) ?? []
  const domainTotal = domainSlice.reduce((s, d) => s + d.count, 0)
  const domainsWithPercent = domainSlice.map((d) => ({
    ...d,
    percent: domainTotal > 0 ? Math.round((d.count / domainTotal) * 100) : 0,
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">{t('admin_stats.title')}</h1>
        <PeriodToggle value={period} onChange={setPeriod} />
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)
        ) : stats ? (
          <>
            <StatCard label={t('admin_stats.total')} value={stats.total_downloads} />
            <StatCard label={t('admin_stats.today')} value={stats.downloads_today} variant="success" />
            <StatCard
              label={t('admin_stats.cache_hits')}
              value={stats.cache_hits_today}
              sub={t('admin_stats.cache_rate', { rate: cacheRate })}
            />
            <StatCard
              label={t('admin_stats.errors')}
              value={stats.errors_today}
              variant={stats.errors_today > 0 ? 'danger' : 'default'}
            />
          </>
        ) : null}
      </div>

      {!error && (
        <>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{t('admin_stats.chart_title', { days: period })}</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <Skeleton className="h-48 w-full" />
              ) : !stats || stats.downloads_by_day.length === 0 ? (
                <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">{ t('admin_stats.no_data') }</div>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={stats.downloads_by_day} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 10 }}
                      tickFormatter={(v: string) => v.slice(5)}
                      interval="preserveStartEnd"
                    />
                    <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                    <Tooltip labelFormatter={(v) => `Date: ${v}`} formatter={(v) => [v, 'Downloads']} />
                    <Bar dataKey="count" fill={chartColors()[0]} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{t('admin_stats.top_domains')}</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <Skeleton className="h-44 w-full" />
                ) : !stats || stats.top_domains.length === 0 ? (
                  <div className="text-sm text-muted-foreground">{ t('admin_stats.no_data') }</div>
                ) : (
                  <ResponsiveContainer width="100%" height={stats.top_domains.slice(0, 8).length * 26 + 8}>
                    <BarChart
                      data={stats.top_domains.slice(0, 8)}
                      layout="vertical"
                      margin={{ top: 0, right: 12, left: 4, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-border" />
                      <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                      <YAxis type="category" dataKey="domain" width={88} tick={{ fontSize: 10 }} />
                      <Tooltip formatter={(v) => [v, 'Downloads']} />
                      <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                        {stats.top_domains.slice(0, 8).map((_, i) => (
                          <Cell key={i} fill={chartColors()[i % chartColors().length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{t('admin_stats.domain_share')}</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <Skeleton className="h-44 w-full" />
                ) : domainsWithPercent.length === 0 ? (
                  <div className="text-sm text-muted-foreground">{ t('admin_stats.no_data') }</div>
                ) : (
                  <div className="space-y-3">
                    <ResponsiveContainer width="100%" height={160}>
                      <PieChart>
                        <Pie
                          data={domainsWithPercent}
                          dataKey="count"
                          nameKey="domain"
                          cx="50%"
                          cy="50%"
                          innerRadius={40}
                          outerRadius={72}
                          paddingAngle={2}
                          label={false}
                        >
                          {domainsWithPercent.map((_, i) => (
                            <Cell key={i} fill={chartColors()[i % chartColors().length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v, name) => [Number(v).toLocaleString(), name]} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="space-y-1.5">
                      {domainsWithPercent.map((item, i) => (
                        <div key={item.domain} className="flex items-center gap-2 text-xs">
                          <span
                            className="h-2.5 w-2.5 shrink-0 rounded-sm"
                            style={{ backgroundColor: chartColors()[i % chartColors().length] }}
                          />
                          <span className="flex-1 truncate text-muted-foreground">{item.domain}</span>
                          <span className="tabular-nums font-medium">{Number(item.count).toLocaleString()}</span>
                          <span className="w-9 text-right tabular-nums text-muted-foreground">{item.percent}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
