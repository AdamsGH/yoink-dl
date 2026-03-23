import { useEffect, useState } from 'react'

import { Trash2 } from 'lucide-react'

import { apiClient } from '@core/lib/api-client'
import { formatDate } from '@core/lib/utils'
import { Badge } from '@core/components/ui/badge'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { toast } from '@core/components/ui/toast'

interface CookieEntry {
  id: number
  domain: string
  is_valid: boolean
  updated_at: string
}

export default function CookiesPage() {
  const [cookies, setCookies] = useState<CookieEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<number | null>(null)

  const load = () => {
    setLoading(true)
    apiClient.get<CookieEntry[]>('/dl/cookies')
      .then(r => setCookies(r.data))
      .catch(() => toast.error('Failed to load cookies'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const remove = async (id: number, domain: string) => {
    setDeleting(id)
    try {
      await apiClient.delete(`/dl/cookies/by-id/${id}`)
      toast.success(`Removed cookies for ${domain}`)
      load()
    } catch {
      toast.error('Failed to delete')
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">My Cookies</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Stored cookies</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex justify-center py-10 text-muted-foreground text-sm">Loading…</div>
          ) : cookies.length === 0 ? (
            <div className="flex justify-center py-10 text-muted-foreground text-sm">
              No cookies stored yet
            </div>
          ) : (
            <div className="divide-y divide-border">
              {cookies.map(c => (
                <div key={c.id} className="flex items-center justify-between px-4 py-3 gap-3">
                  <div className="min-w-0 space-y-0.5">
                    <p className="text-sm font-medium">{c.domain}</p>
                    <div className="flex items-center gap-2 pt-0.5">
                      <Badge variant={c.is_valid ? 'success' : 'destructive'} className="text-xs">
                        {c.is_valid ? 'valid' : 'invalid'}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        Updated {formatDate(c.updated_at)}
                      </span>
                    </div>
                  </div>
                  <Button
                    variant="ghost" size="icon"
                    className="text-destructive hover:text-destructive shrink-0"
                    disabled={deleting === c.id}
                    onClick={() => remove(c.id, c.domain)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">How to add cookies</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            Cookies let the bot download content that requires login - private Instagram posts,
            age-restricted YouTube videos, etc.
          </p>

          <div className="space-y-3">
            <div className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">1</span>
              <div>
                <p className="font-medium">Install the Yoink Cookie Sync extension</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Available for Chrome, Chromium, Edge. Load from the bot admin or ask your admin for the .zip file.
                </p>
              </div>
            </div>

            <div className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">2</span>
              <div>
                <p className="font-medium">Log in to the sites you want to use</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Instagram, YouTube, X, TikTok - in the same browser where the extension is installed.
                </p>
              </div>
            </div>

            <div className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">3</span>
              <div>
                <p className="font-medium">Get a token from the bot</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Send <code className="bg-muted px-1 rounded">/cookie token</code> to the bot in Telegram.
                </p>
              </div>
            </div>

            <div className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">4</span>
              <div>
                <p className="font-medium">Paste the token in the extension and click Send</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Token is valid for 10 minutes and single-use. Repeat when cookies expire.
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
