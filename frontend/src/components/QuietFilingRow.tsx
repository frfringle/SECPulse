import { Link } from 'react-router-dom'
import { timeSince } from '../lib/format'
import type { QuietFiling } from '../types'

type Props = {
  filing: QuietFiling
}

export function QuietFilingRow({ filing }: Props) {
  const when = filing.accepted_at || filing.ingested_at
  return (
    <article className="grid grid-cols-[1fr_auto] gap-2 border-b border-line/40 px-1 py-2.5 text-sm sm:grid-cols-[5.5rem_1fr_auto] sm:items-center sm:gap-3">
      <Link
        to={`/ticker/${filing.ticker}`}
        className="font-display text-base font-semibold text-mist transition hover:text-foam"
      >
        {filing.ticker || '—'}
      </Link>
      <div className="min-w-0 col-span-2 sm:col-span-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-xs uppercase tracking-wide text-mist/70">{filing.form_type}</span>
          <span className="truncate text-mist/90">{filing.company_name || 'Unknown company'}</span>
        </div>
        <p className="mt-0.5 truncate text-xs text-mist/60">{filing.reason}</p>
      </div>
      <time className="text-xs text-mist/70 tabular-nums" dateTime={when ?? undefined}>
        {when ? timeSince(when) : '—'}
      </time>
    </article>
  )
}
