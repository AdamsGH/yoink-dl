import { useEffect, useState } from 'react'

const faviconCache = new Map<string, string | null>()

/**
 * Resolves a Google favicon URL for the given domain.
 * Returns null while loading or if the favicon fails to load.
 * Caches results in module-level Map to avoid redundant requests.
 */
export function useFavicon(domain: string | null): string | null {
  const [src, setSrc] = useState<string | null>(() =>
    domain ? (faviconCache.get(domain) ?? null) : null
  )

  useEffect(() => {
    if (!domain) return
    if (faviconCache.has(domain)) {
      setSrc(faviconCache.get(domain)!)
      return
    }
    const url = `https://www.google.com/s2/favicons?sz=32&domain=${domain}`
    const img = new Image()
    img.onload = () => { faviconCache.set(domain, url); setSrc(url) }
    img.onerror = () => { faviconCache.set(domain, null); setSrc(null) }
    img.src = url
  }, [domain])

  return src
}
