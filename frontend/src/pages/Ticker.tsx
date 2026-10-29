import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchTicker } from '../api'
import { AlertDrawer } from '../components/AlertDrawer'
import { AlertRow } from '../components/AlertRow'
import { Footer } from '../components/Footer'
import { PriceChart } from '../components/PriceChart'
import { useWatchlist } from '../hooks/useWatchlist'
import { formatPrice } from '../lib/format'
import type { Alert, TickerDetail } from '../types'

export function TickerPage() {
  const { symbol = '' } = useParams()
  const ticker = symbol.toUpperCase()
  const [data, setData] = useState<TickerDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Alert | null>(null)
  const [range, setRange] = useState<'intraday' | 'five_day'>('five_day')
  const { has, toggle } = useWatchlist()

  useEffect(() => {
    let cancelled = false
    setData(null)
    fetchTicker(ticker)
      .then((d) => {
        if (!cancelled) {
          setData(d)
          setError(null)
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed')
      })
    return () => {
      cancelled = true
    }
  }, [ticker])

  const points =
    range === 'intraday' ? data?.history.intraday ?? [] : data?.history.five_day ?? []

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-line/80">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-5 sm:px-6">
          <Link to="/" className="font-display text-xl font-bold text-foam">
            SEC<span className="text-accent">Pulse</span>
          </Link>
          <Link to="/" className="text-sm text-mist hover:text-foam">
            ← Feed
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
        <div className="animate-fade-up mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-display text-5xl font-extrabold tracking-tight text-foam sm:text-6xl">
              {ticker}
            </p>
            <p className="mt-1 text-sm text-mist">
              {data?.market_cap_bucket
                ? `${data.market_cap_bucket} cap`
                : 'Market data via yfinance'}
            </p>
          </div>
          <div className="text-right">
            <p className="font-display text-4xl font-bold tabular-nums text-bull sm:text-5xl">
              {formatPrice(data?.price ?? null)}
            </p>
            <button
              type="button"
              onClick={() => toggle(ticker)}
              className={`mt-2 text-sm ${has(ticker) ? 'text-accent' : 'text-mist hover:text-foam'}`}
            >
              {has(ticker) ? '★ On watchlist' : '☆ Add to watchlist'}
            </button>
          </div>
        </div>

        {error ? (
          <p className="mb-4 text-sm text-bear">{error}</p>
        ) : null}
        {data?.price_error && !error ? (
          <p className="mb-3 text-xs text-mist">
            Live quotes unavailable ({data.price_error}). Showing alert-derived levels when
            possible.
          </p>
        ) : null}

        <div className="mb-3 flex gap-2">
          <button
            type="button"
            onClick={() => setRange('five_day')}
            className={`rounded-md px-3 py-1 text-xs ${
              range === 'five_day'
                ? 'bg-accent-dim text-accent'
                : 'border border-line text-mist'
            }`}
          >
            5 day
          </button>
          <button
            type="button"
            onClick={() => setRange('intraday')}
            className={`rounded-md px-3 py-1 text-xs ${
              range === 'intraday'
                ? 'bg-accent-dim text-accent'
                : 'border border-line text-mist'
            }`}
          >
            Intraday
          </button>
        </div>

        <div className="animate-fade-up mb-10 rounded-xl border border-line bg-panel/30 p-3 sm:p-4">
          <PriceChart points={points} alerts={data?.alerts ?? []} />
        </div>

        <h2 className="mb-2 font-display text-xl font-bold text-foam">
          Alerts for {ticker}
        </h2>
        {(data?.alerts ?? []).length === 0 ? (
          <p className="py-8 text-mist">No stored alerts for this ticker.</p>
        ) : (
          (data?.alerts ?? []).map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              watched={has(alert.ticker)}
              onOpen={setSelected}
              onToggleWatch={toggle}
            />
          ))
        )}
      </main>

      <Footer />
      <AlertDrawer alert={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
