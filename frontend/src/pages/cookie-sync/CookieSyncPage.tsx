/**
 * Public page for mobile cookie upload via deep link.
 * Opened via https://yoink.example.com/cookie-sync?token=<tok>
 * No JWT required - the token is the credential.
 */
import { useEffect, useRef, useState } from 'react'
import { Upload, CheckCircle, AlertCircle } from 'lucide-react'

import { apiClient } from '@core/lib/api-client'
import { parseDomainFromNetscape } from '@dl/lib/cookie-utils'

type Phase = 'idle' | 'uploading' | 'done' | 'error'

function useTokenFromUrl(): string {
  const params = new URLSearchParams(window.location.search)
  return params.get('token') ?? ''
}

export default function CookieSyncPage() {
  const token = useTokenFromUrl()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [content, setContent] = useState('')
  const [domain, setDomain] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    document.title = 'Cookie Sync'
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
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

  const handleSubmit = async () => {
    if (!token) { setErrorMsg('No token in URL. Use the link from the bot.'); setPhase('error'); return }
    if (!content) { setErrorMsg('Select a cookies.txt file first.'); setPhase('error'); return }
    if (!domain) { setErrorMsg('Could not detect domain. Check the file format.'); setPhase('error'); return }

    setPhase('uploading')
    setErrorMsg('')
    try {
      await apiClient.post('/dl/cookies/upload', { domain, content }, {
        headers: { Authorization: `Bearer ${token}` },
      })
      setPhase('done')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Upload failed. Check that the token is valid and the file is correct.'
      setErrorMsg(msg)
      setPhase('error')
    }
  }

  if (phase === 'done') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="flex max-w-sm flex-col items-center gap-4 text-center">
          <CheckCircle className="h-12 w-12 text-green-500" />
          <h1 className="text-xl font-semibold">Cookies uploaded</h1>
          <p className="text-sm text-muted-foreground">
            Cookies for <strong>{domain}</strong> saved successfully. You can close this page.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm space-y-5">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold">Upload cookies</h1>
          <p className="text-sm text-muted-foreground">
            Export a <code className="rounded bg-muted px-1 text-xs">cookies.txt</code> file from your browser,
            then select it below.
          </p>
        </div>

        {!token && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            No token found in URL. Use the link sent by the bot.
          </div>
        )}

        <div className="space-y-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,text/plain"
            className="hidden"
            onChange={handleFileChange}
          />

          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-input bg-muted/30 px-4 py-6 text-sm text-muted-foreground transition-colors hover:bg-muted/50 active:bg-muted"
          >
            <Upload className="h-5 w-5" />
            {file ? file.name : 'Select cookies.txt'}
          </button>

          {file && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Domain</label>
              <input
                type="text"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="youtube.com"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
              <p className="text-xs text-muted-foreground">Auto-detected. Edit if incorrect.</p>
            </div>
          )}

          {phase === 'error' && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          <button
            type="button"
            onClick={handleSubmit}
            disabled={!file || !token || phase === 'uploading' || !domain}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {phase === 'uploading' ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground/30 border-t-primary-foreground" />
                Uploading…
              </>
            ) : 'Upload cookies'}
          </button>
        </div>

        <div className="space-y-2 rounded-md border bg-muted/30 p-3">
          <p className="text-xs font-medium">How to get cookies.txt</p>
          <ol className="space-y-1.5 text-xs text-muted-foreground">
            {[
              'Install "Get cookies.txt LOCALLY" (Chrome/Edge) or "Cookie-Editor" (iOS Safari via App Store).',
              'Open the site you want to add (YouTube, Instagram, etc.) and log in.',
              'Tap the extension icon and export cookies as a .txt file.',
              'Come back here and select that file.',
            ].map((step, i) => (
              <li key={i} className="flex gap-2">
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold">
                  {i + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  )
}
