import { Link } from 'react-router-dom'
import { timeSince } from '../lib/format'
import type { PatentEvent } from '../types'

type Props = {
  patent: PatentEvent
  fresh?: boolean
  watched?: boolean
  onOpen: (patent: PatentEvent) => void
  onToggleWatch: (ticker: string) => void
}

export function PatentRow({
  patent,
  fresh,
  watched,
  onOpen,
  onToggleWatch,
}: Props) {
  const label =
    patent.event_type === 'grant'
      ? 'Grant'
      : patent.event_type === 'status_change'
        ? 'Status'
        : 'Application'

  return (
    <article
      className={`group relative grid grid-cols-[1fr_auto] gap-3 border-b border-line/70 px-1 py-4 transition hover:bg-panel/50 sm:grid-cols-[7rem_1fr_auto] sm:items-center sm:gap-4 ${fresh ? 'animate-alert-in' : ''}`}
    >
      <button
        type="button"
        onClick={() => onOpen(patent)}
        className="col-span-2 grid grid-cols-subgrid text-left sm:col-span-2 sm:contents"
      >
        <div className="sm:pr-2">
          <Link
            to={`/ticker/${patent.ticker}`}
            onClick={(e) => e.stopPropagation()}
            className="font-display text-xl font-bold tracking-tight text-foam transition hover:text-accent"
          >
            {patent.ticker}
          </Link>
          <p className="truncate text-xs text-mist">{patent.assignee}</p>
        </div>

        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="rounded border border-accent/40 bg-accent-dim px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-accent">
              Patent
            </span>
            <span className="text-[11px] font-semibold uppercase tracking-wide text-bull">
              {label}
            </span>
            <span className="text-[11px] text-mist">
              {patent.patent_number
                ? `US${patent.patent_number}`
                : patent.application_number}
            </span>
          </div>
          <p className="line-clamp-2 text-sm text-foam/90">{patent.title || 'Untitled invention'}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-mist">
            <span>{timeSince(patent.event_at || patent.created_at)}</span>
            <span className="rounded border border-line/80 px-1.5 py-0.5">USPTO</span>
          </div>
        </div>
      </button>

      <div className="flex flex-col items-end gap-2">
        <button
          type="button"
          onClick={() => onToggleWatch(patent.ticker)}
          className={`text-[11px] ${watched ? 'text-accent' : 'text-mist hover:text-foam'}`}
          aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'}
        >
          {watched ? '★ Watch' : '☆ Watch'}
        </button>
      </div>
    </article>
  )
}
