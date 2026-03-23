import { useEffect, useState } from 'react'

import { apiClient } from '@core/lib/api-client'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@core/components/ui/card'
import { Input } from '@core/components/ui/input'
import { Label } from '@core/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@core/components/ui/select'
import { toast } from '@core/components/ui/toast'

const ROLES = [
  { value: 'owner',      label: 'Owner only' },
  { value: 'admin',      label: 'Admin and above' },
  { value: 'moderator',  label: 'Moderator and above' },
  { value: 'user',       label: 'All users' },
]

export default function AdminBotSettingsPage() {
  const [settings, setSettings] = useState<Record<string, string | null>>({})
  const [loading, setLoading] = useState(true)
  const [storageChat, setStorageChat] = useState('')
  const [storageThread, setStorageThread] = useState('')
  const [storageSaving, setStorageSaving] = useState(false)

  useEffect(() => {
    apiClient
      .get<Record<string, string | null>>('/bot-settings')
      .then((r) => {
        setSettings(r.data)
        setStorageChat(r.data['inline_storage_chat_id'] ?? '')
        setStorageThread(r.data['inline_storage_thread_id'] ?? '')
      })
      .catch(() => toast.error('Failed to load bot settings'))
      .finally(() => setLoading(false))
  }, [])

  const saveStorage = async () => {
    setStorageSaving(true)
    try {
      await apiClient.patch('/bot-settings', {
        inline_storage_chat_id: storageChat || null,
        inline_storage_thread_id: storageThread || null,
      })
      toast.success('Saved')
    } catch {
      toast.error('Failed to save')
    } finally {
      setStorageSaving(false)
    }
  }

  const update = async (key: string, value: string) => {
    try {
      await apiClient.patch('/bot-settings', { [key]: value })
      setSettings((prev) => ({ ...prev, [key]: value }))
      toast.success('Saved')
    } catch {
      toast.error('Failed to save')
    }
  }

  if (loading) return <div className="flex justify-center py-24 text-muted-foreground">Loading…</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Bot Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle>Access Mode</CardTitle>
          <CardDescription>
            Controls who can use the bot in private chats.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Label>Private chat access</Label>
            <Select
              value={settings['bot_access_mode'] ?? 'open'}
              onValueChange={(v) => update('bot_access_mode', v)}
            >
              <SelectTrigger className="w-64">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="open">Open  - anyone can use the bot</SelectItem>
                <SelectItem value="approved_only">Approved only  - new users get restricted role</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              In <strong>approved only</strong> mode, new users receive the <code>restricted</code> role
              (no access) until manually upgraded to <code>user</code> or above.
              Existing users are not affected.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Browser Cookies</CardTitle>
          <CardDescription>
            Who can use the shared browser profile (Chromium) for cookie-authenticated downloads.
            The owner always has access regardless of this setting.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Label>Minimum role required</Label>
            <Select
              value={settings['browser_cookies_min_role'] ?? 'owner'}
              onValueChange={(v) => update('browser_cookies_min_role', v)}
            >
              <SelectTrigger className="w-64">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r.value} value={r.value}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Users with this role or higher will automatically use the shared
              Chromium profile cookies when no personal cookie is uploaded.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Inline Storage</CardTitle>
          <CardDescription>
            Global fallback for the inline download pipeline. When a user picks an inline result,
            the bot stages the file here to get a Telegram file_id, then edits the message in the group.
            Per-group overrides can be set in Groups settings. If empty, files are staged in the user's DM.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="storage-chat">Storage chat ID</Label>
              <Input
                id="storage-chat"
                placeholder="-100123456789 or channel ID"
                value={storageChat}
                onChange={(e) => setStorageChat(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">Bot must be a member with send permission.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="storage-thread">Thread ID (optional)</Label>
              <Input
                id="storage-thread"
                placeholder="Forum topic ID"
                value={storageThread}
                onChange={(e) => setStorageThread(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">Leave empty for the main chat.</p>
            </div>
          </div>
          <Button onClick={saveStorage} disabled={storageSaving} size="sm">
            {storageSaving ? 'Saving…' : 'Save storage settings'}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
