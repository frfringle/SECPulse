import type { ReactNode } from 'react'
import type { AlertFilters } from '../types'

type Props = {
  filters: AlertFilters
  onChange: (next: AlertFilters) => void
  watchlistOnly: boolean
  onWatchlistOnly: (v: boolean) => void
}

export function Filters({ filters, onChange, watchlistOnly, onWatchlistOnly }: Props) {
  return (
    <div className="animate-fade-up flex flex-wrap items-end gap-3" style={{ animationDelay: '80ms' }}>
      <Field label="Direction">
        <select
          value={filters.direction}
          onChange={(e) => onChange({ ...filters, direction: e.target.value })}
          className="field"
        >
          <option value="all">All</option>
          <option value="bullish">Bullish</option>
          <option value="bearish">Bearish</option>
        </select>
      </Field>
      <Field label="Form">
        <select
          value={filters.form_type}
          onChange={(e) => onChange({ ...filters, form_type: e.target.value })}
          className="field"
        >
          <option value="all">All</option>
          <option value="8-K">8-K</option>
          <option value="8-K/A">8-K/A</option>
          <option value="4">Form 4</option>
          <option value="SC 13D">SC 13D</option>
          <option value="SC 13D/A">SC 13D/A</option>
        </select>
      </Field>
      <Field label="Min confidence">
        <select
          value={filters.min_confidence}
          onChange={(e) =>
            onChange({ ...filters, min_confidence: Number(e.target.value) })
          }
          className="field"
        >
          <option value={0}>Any</option>
          <option value={65}>65+</option>
          <option value={75}>75+</option>
          <option value={85}>85+</option>
        </select>
      </Field>
      <Field label="Market cap">
        <select
          value={filters.market_cap_bucket}
          onChange={(e) =>
            onChange({ ...filters, market_cap_bucket: e.target.value })
          }
          className="field"
        >
          <option value="small,mid">Small + mid</option>
          <option value="small">Small</option>
          <option value="mid">Mid</option>
          <option value="large">Large</option>
          <option value="all">All</option>
        </select>
      </Field>
      <label className="mb-0.5 flex cursor-pointer items-center gap-2 text-xs text-mist">
        <input
          type="checkbox"
          checked={watchlistOnly}
          onChange={(e) => onWatchlistOnly(e.target.checked)}
          className="accent-accent"
        />
        Watchlist only
      </label>
    </div>
  )
}

function Field({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-mist">
      {label}
      {children}
    </label>
  )
}
