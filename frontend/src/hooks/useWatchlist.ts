import { useCallback, useEffect, useState } from 'react'

const KEY = 'secpulse.watchlist'

function read(): string[] {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.map(String) : []
  } catch {
    return []
  }
}

export function useWatchlist() {
  const [watchlist, setWatchlist] = useState<string[]>(() => read())

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(watchlist))
  }, [watchlist])

  const toggle = useCallback((ticker: string) => {
    const t = ticker.toUpperCase()
    setWatchlist((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    )
  }, [])

  const has = useCallback(
    (ticker: string) => watchlist.includes(ticker.toUpperCase()),
    [watchlist],
  )

  return { watchlist, toggle, has }
}
