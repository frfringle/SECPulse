export type Direction = 'bullish' | 'bearish' | 'neutral'

export interface Alert {
  id: number
  filing_id: number
  accession_number: string
  ticker: string
  form_type: string
  company_name: string
  direction: Direction
  confidence: number
  summary: string
  key_evidence: string
  event_type: string
  source: string
  created_at: string | null
  latency_seconds: number | null
  price_at_alert: number | null
  price_at_accepted: number | null
  pct_change_since_accepted: number | null
  market_cap: number | null
  market_cap_bucket: string | null
  no_press_release: boolean | null
  enrichment_error: string | null
  filing_url?: string | null
}

export interface Health {
  status: string
  stage: number
  last_poll_at: string | null
  last_poll_inserted: number
  last_poll_error: string | null
  queue_size: number
  ollama_reachable: boolean
  ollama_model: string | null
}

export interface PricePoint {
  t: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  volume: number | null
}

export interface TickerDetail {
  ticker: string
  price: number | null
  market_cap: number | null
  market_cap_bucket: string | null
  currency: string
  price_error: string | null
  alerts: Alert[]
  alert_count: number
  history: {
    intraday: PricePoint[]
    five_day: PricePoint[]
  }
}

export interface AlertFilters {
  direction: string
  form_type: string
  min_confidence: number
  market_cap_bucket: string
}
