import { Globe } from 'lucide-react'
import { useFavicon } from '@dl/hooks/useFavicon'

interface CookieFaviconProps {
  domain: string
  /** Icon shown when favicon fails to load. Defaults to Globe. */
  fallback?: React.ReactNode
}

export function CookieFavicon({ domain, fallback }: CookieFaviconProps) {
  const src = useFavicon(domain)
  if (src) return <img src={src} alt="" className="size-4 rounded-sm object-contain" />
  return <>{fallback ?? <Globe className="size-4" />}</>
}
