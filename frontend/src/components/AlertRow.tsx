import { Link } from 'react-router-dom'
import { formatLatency, formatPct, timeSince } from '../lib/format'
import type { Alert } from '../types'

type Props = {
  alert: Alert
  fresh?: boolean
  watched?: boolean
  onOpen: (alert: Alert) => void
  onToggleWatch: (ticker: string) => void
}

export function AlertRow({
  alert,
  fresh,
  watched,
  onOpen,
  onToggleWatch,
}: Props) {
  const bull = alert.direction === 'bullish'
  const bear = alert.direction === 'bearish'
  const pct = alert.pct_change_since_accepted
  const pctBull = pct !== null && pct !== undefined && pct >= 0

  return (
    <article
      className={`group relative grid grid-cols-[1fr_auto] gap-3 border-b border-line/70 px-1 py-4 transition hover:bg-panel/50 sm:grid-cols-[7rem_1fr_auto] sm:items-center sm:gap-4 ${fresh ? 'animate-alert-in' : ''}`}
    >
      <button
        type="button"
        onClick={() => onOpen(alert)}
        className="col-span-2 grid grid-cols-subgrid text-left sm:col-span-2 sm:contents"
      >
        <div className="sm:pr-2">
          <Link
            to={`/ticker/${alert.ticker}`}
            onClick={(e) => e.stopPropagation()}
            className="font-display text-xl font-bold tracking-tight text-foam transition hover:text-accent"
          >
            {alert.ticker}
          </Link>
          <p className="truncate text-xs text-mist">{alert.company_name}</p>
        </div>

        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span
              className={`text-[11px] font-semibold uppercase tracking-wide ${
                bull ? 'text-bull' : bear ? 'text-bear' : 'text-mist'
              }`}
            >
              {alert.direction}
            </span>
            <span className="text-[11px] text-mist">
              {alert.form_type}
              {alert.event_type ? ` · ${alert.event_type.replace(/_/g, ' ')}` : ''}
            </span>
            <span className="font-display text-sm font-semibold tabular-nums text-foam">
              {alert.confidence}
              <span className="text-xs font-normal text-mist"> conf</span>
            </span>
          </div>
          <p className="line-clamp-2 text-sm text-foam/90">{alert.summary}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-mist">
            <span>{timeSince(alert.created_at)}</span>
            <span>latency {formatLatency(alert.latency_seconds)}</span>
            {alert.no_press_release ? (
              <span className="rounded border border-bear/30 bg-bear-dim px-1.5 py-0.5 text-bear">
                No press release
              </span>
            ) : null}
            {alert.source === 'form4_rule' ? (
              <span className="rounded border border-accent/30 bg-accent-dim px-1.5 py-0.5 text-accent">
                Form 4 rule
              </span>
            ) : null}
          </div>
        </div>
      </button>

      <div className="flex flex-col items-end gap-2">
        <p
          className={`font-display text-2xl font-bold tabular-nums ${
            pct === null || pct === undefined
              ? 'text-mist'
              : pctBull
                ? 'text-bull'
                : 'text-bear'
          }`}
        >
          {formatPct(pct)}
        </p>
        <button
          type="button"
          onClick={() => onToggleWatch(alert.ticker)}
          className={`text-[11px] ${watched ? 'text-accent' : 'text-mist hover:text-foam'}`}
          aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'}
        >
          {watched ? '★ Watch' : '☆ Watch'}
        </button>
      </div>
    </article>
  )
}
