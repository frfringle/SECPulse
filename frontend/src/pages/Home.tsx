import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchAlerts,
  fetchHealth,
  fetchNonAlertFilings,
  fetchPatents,
} from '../api'
import { AlertDrawer } from '../components/AlertDrawer'
import { AlertRow } from '../components/AlertRow'
import { Filters } from '../components/Filters'
import { Footer } from '../components/Footer'
import { Header } from '../components/Header'
import { PatentDrawer } from '../components/PatentDrawer'
import { PatentRow } from '../components/PatentRow'
import { QuietFilingRow } from '../components/QuietFilingRow'
import { useNotify } from '../hooks/useNotify'
import { useSSE } from '../hooks/useSSE'
import { useWatchlist } from '../hooks/useWatchlist'
import type {
  Alert,
  AlertFilters,
  Health,
  PatentEvent,
  QuietRow,
} from '../types'

const DEFAULT_FILTERS: AlertFilters = {
  direction: 'all',
  form_type: 'all',
  min_confidence: 0,
  market_cap_bucket: 'small,mid',
}

type FeedItem =
  | { kind: 'alert'; sortAt: number; alert: Alert }
  | { kind: 'patent'; sortAt: number; patent: PatentEvent }

function ts(iso: string | null | undefined): number {
  if (!iso) return 0
  const n = new Date(iso).getTime()
  return Number.isNaN(n) ? 0 : n
}

export function Home() {
  const [filters, setFilters] = useState<AlertFilters>(DEFAULT_FILTERS)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [patents, setPatents] = useState<PatentEvent[]>([])
  const [quietRows, setQuietRows] = useState<QuietRow[]>([])
  const [freshIds, setFreshIds] = useState<Set<number>>(new Set())
  const [freshPatentIds, setFreshPatentIds] = useState<Set<number>>(new Set())
  const [selected, setSelected] = useState<Alert | null>(null)
  const [selectedPatent, setSelectedPatent] = useState<PatentEvent | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [watchlistOnly, setWatchlistOnly] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { watchlist, toggle, has } = useWatchlist()
  const { soundOn, setSoundOn, perm, requestPermission, notifyNew } = useNotify()

  const apiFilters = useMemo(() => {
    const bucket = filters.market_cap_bucket
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
      const overFetch = filters.market_cap_bucket === 'small,mid'
      const [raw, h, quiet, actionablePatents, quietPatents] = await Promise.all([
        fetchAlerts({ ...apiFilters, limit: overFetch ? 40 : 5 }),
        fetchHealth(),
        fetchNonAlertFilings(20),
        fetchPatents({ actionable: true, limit: 20 }),
        fetchPatents({ actionable: false, limit: 20 }),
      ])
      let a = raw
      if (overFetch) {
        a = raw
          .filter(
            (x) =>
              !x.market_cap_bucket ||
              x.market_cap_bucket === 'small' ||
              x.market_cap_bucket === 'mid',
          )
          .slice(0, 5)
      }
      setAlerts(a)
      setPatents(actionablePatents)
      const edgarQuiet: QuietRow[] = quiet.map((f) => ({ ...f, kind: 'edgar' as const }))
      const patentQuiet: QuietRow[] = quietPatents.map((p) => ({
        ...p,
        kind: 'patent' as const,
      }))
      const mergedQuiet = [...patentQuiet, ...edgarQuiet].sort(
        (x, y) =>
          ts(
            x.kind === 'patent'
              ? x.event_at || x.created_at
              : x.accepted_at || x.ingested_at,
          ) <
          ts(
            y.kind === 'patent'
              ? y.event_at || y.created_at
              : y.accepted_at || y.ingested_at,
          )
            ? 1
            : -1,
      )
      setQuietRows(mergedQuiet)
      setHealth(h)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [apiFilters, filters.market_cap_bucket])

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

  // Periodically refresh patents (no SSE for USPTO in v1)
  useEffect(() => {
    const id = setInterval(() => {
      void fetchPatents({ actionable: true, limit: 20 })
        .then((rows) => {
          setPatents((prev) => {
            const known = new Set(prev.map((p) => p.id))
            const fresh = rows.filter((r) => !known.has(r.id))
            if (fresh.length) {
              setFreshPatentIds((s) => {
                const n = new Set(s)
                fresh.forEach((f) => n.add(f.id))
                return n
              })
              setTimeout(() => {
                setFreshPatentIds((s) => {
                  const n = new Set(s)
                  fresh.forEach((f) => n.delete(f.id))
                  return n
                })
              }, 1200)
            }
            const byId = new Map<number, PatentEvent>()
            ;[...fresh, ...prev, ...rows].forEach((p) => byId.set(p.id, p))
            return [...byId.values()].sort(
              (a, b) => ts(b.event_at || b.created_at) - ts(a.event_at || a.created_at),
            )
          })
        })
        .catch(() => undefined)
    }, 60000)
    return () => clearInterval(id)
  }, [])

  const feed = useMemo(() => {
    let alertRows = alerts
    if (filters.market_cap_bucket === 'small,mid') {
      alertRows = alertRows.filter(
        (a) =>
          !a.market_cap_bucket ||
          a.market_cap_bucket === 'small' ||
          a.market_cap_bucket === 'mid',
      )
    }
    if (watchlistOnly) {
      alertRows = alertRows.filter((a) => watchlist.includes(a.ticker))
    }
    let patentRows = patents
    if (watchlistOnly) {
      patentRows = patentRows.filter((p) => watchlist.includes(p.ticker))
    }
    const items: FeedItem[] = [
      ...alertRows.map((alert) => ({
        kind: 'alert' as const,
        sortAt: ts(alert.created_at),
        alert,
      })),
      ...patentRows.map((patent) => ({
        kind: 'patent' as const,
        sortAt: ts(patent.event_at || patent.created_at),
        patent,
      })),
    ]
    return items.sort((a, b) => b.sortAt - a.sortAt)
  }, [alerts, patents, filters.market_cap_bucket, watchlistOnly, watchlist])

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
              Recent EDGAR alerts plus USPTO patent grants; new SEC alerts slide
              in via SSE.
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
          {feed.length === 0 ? (
            <p className="animate-fade-up py-12 text-center text-mist">
              No alerts match these filters yet.
            </p>
          ) : (
            feed.map((item) =>
              item.kind === 'alert' ? (
                <AlertRow
                  key={`a-${item.alert.id}`}
                  alert={item.alert}
                  fresh={freshIds.has(item.alert.id)}
                  watched={has(item.alert.ticker)}
                  onOpen={setSelected}
                  onToggleWatch={toggle}
                />
              ) : (
                <PatentRow
                  key={`p-${item.patent.id}`}
                  patent={item.patent}
                  fresh={freshPatentIds.has(item.patent.id)}
                  watched={has(item.patent.ticker)}
                  onOpen={setSelectedPatent}
                  onToggleWatch={toggle}
                />
              ),
            )
          )}
        </section>

        <section className="mt-10 animate-fade-up">
          <div className="mb-3">
            <h2 className="font-display text-lg font-semibold text-foam">
              Seen, not alerted
            </h2>
            <p className="text-xs text-mist">
              EDGAR filings and USPTO applications that were ingested but did not
              clear the alert bar.
            </p>
          </div>
          {quietRows.length === 0 ? (
            <p className="py-6 text-center text-sm text-mist/70">
              No quiet filings yet — poller may still be warming up.
            </p>
          ) : (
            <div className="rounded-md border border-line/50 bg-panel/30 px-2">
              {quietRows.map((row) => (
                <QuietFilingRow
                  key={row.kind === 'patent' ? `qp-${row.id}` : `qe-${row.id}`}
                  row={row}
                />
              ))}
            </div>
          )}
        </section>
      </main>

      <Footer />
      <AlertDrawer alert={selected} onClose={() => setSelected(null)} />
      <PatentDrawer patent={selectedPatent} onClose={() => setSelectedPatent(null)} />
    </div>
  )
}
