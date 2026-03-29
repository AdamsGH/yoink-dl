/**
 * Parse the registrable domain from the first valid Netscape cookie file line.
 * Returns empty string if nothing is parseable (user-facing cookies page variant).
 * Returns null if nothing is parseable (admin cookies page variant — same logic).
 */
export function parseDomainFromNetscape(text: string): string {
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const parts = trimmed.split('\t')
    if (parts.length >= 7) {
      const host = parts[0].replace(/^\./, '')
      const dot = host.lastIndexOf('.')
      if (dot > 0) {
        const prev = host.lastIndexOf('.', dot - 1)
        return prev >= 0 ? host.slice(prev + 1) : host
      }
    }
  }
  return ''
}
