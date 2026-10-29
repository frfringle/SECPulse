import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchAlerts, fetchHealth } from '../api'
import { AlertDrawer } from '../components/AlertDrawer'
import { AlertRow } from '../components/AlertRow'
import { Filters } from '../components/Filters'
import { Footer } from '../components/Footer'
import { Header } from '../components/Header'
import { useNotify } from '../hooks/useNotify'
import { useSSE } from '../hooks/useSSE'
import { useWatchlist } from '../hooks/useWatchlist'
import type { Alert, AlertFilters, Health } from '../types'

const DEFAULT_FILTERS: AlertFilters = {
  direction: 'all',
  form_type: 'all',
  min_confidence: 0,
  market_cap_bucket: 'small,mid',
}

export function Home() {
  const [filters, setFilters] = useState<AlertFilters>(DEFAULT_FILTERS)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [freshIds, setFreshIds] = useState<Set<number>>(new Set())
  const [selected, setSelected] = useState<Alert | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [watchlistOnly, setWatchlistOnly] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { watchlist, toggle, has } = useWatchlist()
  const { soundOn, setSoundOn, perm, requestPermission, notifyNew } = useNotify()

  const apiFilters = useMemo(() => {
    const bucket = filters.market_cap_bucket
    // API takes a single bucket; multi default filtered client-side
    if (bucket === 'small,mid' || bucket === 'all') {
      return {
        direction: filters.direction,
        form_type: filters.form_type,
        min_confidence: filters.min_confidence || undefined,
        market_cap_bucket: undefined as string | undefined,
      }
    }
    return {
      direction: filters.direction,
      form_type: filters.form_type,
      min_confidence: filters.min_confidence || undefined,
      market_cap_bucket: bucket,
    }
  }, [filters])

  const load = useCallback(async () => {
    try {
      const [a, h] = await Promise.all([fetchAlerts(apiFilters), fetchHealth()])
      setAlerts(a)
      setHealth(h)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [apiFilters])

  useEffect(() => {
    void load()
    const id = setInterval(() => {
      void fetchHealth().then(setHealth).catch(() => undefined)
    }, 15000)
    return () => clearInterval(id)
  }, [load])

  useSSE({
    onAlert: (alert) => {
      setAlerts((prev) => {
        if (prev.some((x) => x.id === alert.id)) return prev
        return [alert, ...prev]
      })
      setFreshIds((prev) => new Set(prev).add(alert.id))
      notifyNew(
        `${alert.ticker} ${alert.direction}`,
        alert.summary.slice(0, 120),
      )
      setTimeout(() => {
        setFreshIds((prev) => {
          const next = new Set(prev)
          next.delete(alert.id)
          return next
        })
      }, 1200)
    },
  })

  const visible = useMemo(() => {
    let rows = alerts
    if (filters.market_cap_bucket === 'small,mid') {
      rows = rows.filter(
        (a) =>
          !a.market_cap_bucket ||
          a.market_cap_bucket === 'small' ||
          a.market_cap_bucket === 'mid',
      )
    }
    if (watchlistOnly) {
      rows = rows.filter((a) => watchlist.includes(a.ticker))
    }
    return rows
  }, [alerts, filters.market_cap_bucket, watchlistOnly, watchlist])

  return (
    <div className="flex min-h-screen flex-col">
      <Header
        health={health}
        soundOn={soundOn}
        onToggleSound={() => setSoundOn((v) => !v)}
        onEnableNotify={() => void requestPermission()}
        notifyPerm={perm}
      />

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="animate-fade-up">
            <h1 className="font-display text-2xl font-bold text-foam sm:text-3xl">
              Live feed
            </h1>
            <p className="text-sm text-mist">
              New alerts slide in at the top as EDGAR filings clear the bar.
            </p>
          </div>
          <Filters
            filters={filters}
            onChange={setFilters}
            watchlistOnly={watchlistOnly}
            onWatchlistOnly={setWatchlistOnly}
          />
        </div>

        {error ? (
          <p className="rounded-md border border-bear/40 bg-bear-dim px-3 py-2 text-sm text-bear">
            {error}
          </p>
        ) : null}

        <section className="mt-2">
          {visible.length === 0 ? (
            <p className="animate-fade-up py-16 text-center text-mist">
              No alerts match these filters yet.
            </p>
          ) : (
            visible.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                fresh={freshIds.has(alert.id)}
                watched={has(alert.ticker)}
                onOpen={setSelected}
                onToggleWatch={toggle}
              />
            ))
          )}
        </section>
      </main>

      <Footer />
      <AlertDrawer alert={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
