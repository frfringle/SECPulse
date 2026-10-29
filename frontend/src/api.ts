import type { Alert, AlertFilters, Health, QuietFiling, TickerDetail } from './types'

/** Empty = same-origin (FastAPI SPA or Vite proxy). Set VITE_API_URL for Netlify → remote API. */
export const API_BASE = String(import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export function apiUrl(path: string): string {
  if (!path.startsWith('/')) return `${API_BASE}/${path}`
  return `${API_BASE}${path}`
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '' || v === 'all') continue
    sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export async function fetchHealth(): Promise<Health> {
  const r = await fetch(apiUrl('/api/health'))
  if (!r.ok) throw new Error('health failed')
  return r.json()
}

export async function fetchAlerts(
  filters: Partial<AlertFilters> & { limit?: number } = {},
): Promise<Alert[]> {
  const r = await fetch(
    apiUrl(
      `/api/alerts${qs({
        direction: filters.direction,
        form_type: filters.form_type,
        min_confidence: filters.min_confidence,
        market_cap_bucket: filters.market_cap_bucket,
        // Home seed: last N by created_at desc (API default order)
        limit: filters.limit ?? 5,
      })}`,
    ),
  )
  if (!r.ok) throw new Error('alerts failed')
  const data = await r.json()
  return data.alerts ?? []
}

export async function fetchAlert(id: number): Promise<Alert> {
  const r = await fetch(apiUrl(`/api/alerts/${id}`))
  if (!r.ok) throw new Error('alert not found')
  return r.json()
}

export async function fetchTicker(ticker: string): Promise<TickerDetail> {
  const r = await fetch(apiUrl(`/api/tickers/${encodeURIComponent(ticker)}`))
  if (!r.ok) throw new Error('ticker failed')
  return r.json()
}

export async function fetchNonAlertFilings(limit = 20): Promise<QuietFiling[]> {
  const r = await fetch(apiUrl(`/api/filings/non-alerts${qs({ limit })}`))
  if (!r.ok) throw new Error('non-alert filings failed')
  const data = await r.json()
  return data.filings ?? []
}

export function filingUrl(accession: string, filingUrlHint?: string): string {
  if (filingUrlHint) return filingUrlHint
  // Best-effort EDGAR index search link
  return `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum=&acc_no=${encodeURIComponent(accession)}&output=xml`
}
