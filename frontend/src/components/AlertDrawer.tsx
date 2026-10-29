import { Link } from 'react-router-dom'
import { edgarLink, formatLatency, formatPct, formatPrice, timeSince } from '../lib/format'
import type { Alert } from '../types'

type Props = {
  alert: Alert | null
  onClose: () => void
}

export function AlertDrawer({ alert, onClose }: Props) {
  if (!alert) return null

  const bull = alert.direction === 'bullish'
  const bear = alert.direction === 'bearish'

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button
        type="button"
        className="absolute inset-0 bg-ink/70 backdrop-blur-[2px]"
        aria-label="Close drawer"
        onClick={onClose}
      />
      <aside className="animate-drawer-in relative z-10 flex h-full w-full max-w-md flex-col border-l border-line bg-ink-2 shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <Link
              to={`/ticker/${alert.ticker}`}
              className="font-display text-3xl font-bold text-foam hover:text-accent"
              onClick={onClose}
            >
              {alert.ticker}
            </Link>
            <p className="text-sm text-mist">{alert.company_name}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-line px-2 py-1 text-xs text-mist hover:text-foam"
          >
            Close
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <div className="flex flex-wrap items-baseline gap-3">
            <span
              className={`font-display text-2xl font-bold ${
                bull ? 'text-bull' : bear ? 'text-bear' : 'text-mist'
              }`}
            >
              {alert.direction}
            </span>
            <span className="font-display text-2xl tabular-nums text-foam">
              {alert.confidence}
              <span className="text-sm text-mist"> conf</span>
            </span>
            <span className="text-sm text-mist">{alert.form_type}</span>
          </div>

          <section>
            <h3 className="mb-1 text-[11px] uppercase tracking-wide text-mist">Summary</h3>
            <p className="text-sm leading-relaxed text-foam">{alert.summary}</p>
          </section>

          <section>
            <h3 className="mb-1 text-[11px] uppercase tracking-wide text-mist">
              Key evidence
            </h3>
            <blockquote className="border-l-2 border-accent/50 bg-panel px-3 py-2 text-sm italic text-foam/90">
              “{alert.key_evidence}”
            </blockquote>
          </section>

          {alert.source === 'form4_rule' || alert.event_type === 'form4_open_market_buy' ? (
            <section className="rounded-lg border border-line bg-panel p-3">
              <h3 className="mb-1 text-[11px] uppercase tracking-wide text-accent">
                Form 4 open-market buy
              </h3>
              <p className="text-sm text-foam/90">
                Alerted by rule (officer/director code P) — Ollama score not required.
              </p>
            </section>
          ) : null}

          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Stat label="Since filing" value={timeSince(alert.created_at)} />
            <Stat label="Latency" value={formatLatency(alert.latency_seconds)} />
            <Stat label="Price at alert" value={formatPrice(alert.price_at_alert)} />
            <Stat
              label="% since accepted"
              value={formatPct(alert.pct_change_since_accepted)}
              tone={
                (alert.pct_change_since_accepted ?? 0) >= 0 ? 'bull' : 'bear'
              }
            />
            <Stat label="Market cap" value={alert.market_cap_bucket ?? '—'} />
            <Stat
              label="Press release"
              value={
                alert.no_press_release === null
                  ? '—'
                  : alert.no_press_release
                    ? 'None'
                    : 'Present'
              }
            />
          </dl>
        </div>

        <div className="border-t border-line px-5 py-4">
          <a
            href={edgarLink(alert.accession_number, alert.filing_url)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex w-full items-center justify-center rounded-md border border-accent/40 bg-accent-dim px-3 py-2.5 text-sm font-semibold text-accent transition hover:bg-accent/20"
          >
            Open SEC filing
          </a>
          <p className="mt-2 text-center text-[11px] text-mist">
            {alert.accession_number}
          </p>
        </div>
      </aside>
    </div>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'bull' | 'bear'
}) {
  return (
    <div className="rounded-md border border-line/80 bg-panel/60 px-3 py-2">
      <dt className="text-[10px] uppercase tracking-wide text-mist">{label}</dt>
      <dd
        className={`mt-0.5 font-display text-lg font-semibold tabular-nums ${
          tone === 'bull' ? 'text-bull' : tone === 'bear' ? 'text-bear' : 'text-foam'
        }`}
      >
        {value}
      </dd>
    </div>
  )
}
