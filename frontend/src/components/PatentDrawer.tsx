import { Link } from 'react-router-dom'
import { timeSince } from '../lib/format'
import type { PatentEvent } from '../types'

type Props = {
  patent: PatentEvent | null
  onClose: () => void
}

export function PatentDrawer({ patent, onClose }: Props) {
  if (!patent) return null

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
              to={`/ticker/${patent.ticker}`}
              className="font-display text-3xl font-bold text-foam hover:text-accent"
              onClick={onClose}
            >
              {patent.ticker}
            </Link>
            <p className="text-sm text-mist">{patent.assignee}</p>
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
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded border border-accent/40 bg-accent-dim px-2 py-0.5 text-xs font-semibold uppercase text-accent">
              Patent
            </span>
            <span className="text-sm text-mist">{patent.event_type.replace(/_/g, ' ')}</span>
          </div>
          <h2 className="font-display text-xl font-semibold text-foam">
            {patent.title || 'Untitled invention'}
          </h2>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-mist">Application</dt>
              <dd className="tabular-nums text-foam">{patent.application_number}</dd>
            </div>
            {patent.patent_number ? (
              <div className="flex justify-between gap-3">
                <dt className="text-mist">Patent</dt>
                <dd className="tabular-nums text-foam">US{patent.patent_number}</dd>
              </div>
            ) : null}
            {patent.status_label ? (
              <div className="flex justify-between gap-3">
                <dt className="text-mist">Status</dt>
                <dd className="text-right text-foam">{patent.status_label}</dd>
              </div>
            ) : null}
            <div className="flex justify-between gap-3">
              <dt className="text-mist">Event</dt>
              <dd className="text-foam">{timeSince(patent.event_at || patent.created_at)}</dd>
            </div>
          </dl>
          <p className="text-sm text-mist">{patent.reason}</p>
          <div className="flex flex-col gap-2 pt-2">
            <a
              href={patent.uspto_url}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-line px-3 py-2 text-center text-sm text-foam hover:border-accent hover:text-accent"
            >
              Open USPTO Patent Center
            </a>
            {patent.google_patents_url ? (
              <a
                href={patent.google_patents_url}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border border-line px-3 py-2 text-center text-sm text-foam hover:border-accent hover:text-accent"
              >
                Open Google Patents
              </a>
            ) : null}
          </div>
        </div>
      </aside>
    </div>
  )
}
