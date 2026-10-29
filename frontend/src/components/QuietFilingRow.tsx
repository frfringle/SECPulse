import { Link } from 'react-router-dom'
import { timeSince } from '../lib/format'
import type { QuietRow } from '../types'

type Props = {
  row: QuietRow
}

export function QuietFilingRow({ row }: Props) {
  if (row.kind === 'patent') {
    const when = row.event_at || row.created_at
    return (
      <article className="grid grid-cols-[1fr_auto] gap-2 border-b border-line/40 px-1 py-2.5 text-sm sm:grid-cols-[5.5rem_1fr_auto] sm:items-center sm:gap-3">
        <Link
          to={`/ticker/${row.ticker}`}
          className="font-display text-base font-semibold text-mist transition hover:text-foam"
        >
          {row.ticker || '—'}
        </Link>
        <div className="min-w-0 col-span-2 sm:col-span-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="rounded border border-accent/30 px-1 text-[10px] uppercase tracking-wide text-accent">
              Patent
            </span>
            <span className="text-xs uppercase tracking-wide text-mist/70">
              {row.event_type.replace(/_/g, ' ')}
            </span>
            <span className="truncate text-mist/90">{row.title || row.assignee}</span>
          </div>
          <p className="mt-0.5 truncate text-xs text-mist/60">{row.reason}</p>
        </div>
        <time className="text-xs text-mist/70 tabular-nums" dateTime={when ?? undefined}>
          {when ? timeSince(when) : '—'}
        </time>
      </article>
    )
  }

  const when = row.accepted_at || row.ingested_at
  return (
    <article className="grid grid-cols-[1fr_auto] gap-2 border-b border-line/40 px-1 py-2.5 text-sm sm:grid-cols-[5.5rem_1fr_auto] sm:items-center sm:gap-3">
      <Link
        to={`/ticker/${row.ticker}`}
        className="font-display text-base font-semibold text-mist transition hover:text-foam"
      >
        {row.ticker || '—'}
      </Link>
      <div className="min-w-0 col-span-2 sm:col-span-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-xs uppercase tracking-wide text-mist/70">{row.form_type}</span>
          <span className="truncate text-mist/90">{row.company_name || 'Unknown company'}</span>
        </div>
        <p className="mt-0.5 truncate text-xs text-mist/60">{row.reason}</p>
      </div>
      <time className="text-xs text-mist/70 tabular-nums" dateTime={when ?? undefined}>
        {when ? timeSince(when) : '—'}
      </time>
    </article>
  )
}
