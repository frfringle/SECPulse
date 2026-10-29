import {
  AreaSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'
import type { Alert, PricePoint } from '../types'

type Props = {
  points: PricePoint[]
  alerts?: Alert[]
  height?: number
}

export function PriceChart({ points, alerts = [], height = 280 }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    const chart: IChartApi = createChart(ref.current, {
      height,
      layout: {
        background: { color: 'transparent' },
        textColor: '#8a9a8e',
        fontFamily: 'Manrope, sans-serif',
      },
      grid: {
        vertLines: { color: 'rgba(36,48,40,0.55)' },
        horzLines: { color: 'rgba(36,48,40,0.55)' },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      crosshair: {
        vertLine: { color: 'rgba(200,245,96,0.35)' },
        horzLine: { color: 'rgba(200,245,96,0.35)' },
      },
    })

    const series: ISeriesApi<'Area'> = chart.addSeries(AreaSeries, {
      lineColor: '#3dd68c',
      topColor: 'rgba(61, 214, 140, 0.28)',
      bottomColor: 'rgba(61, 214, 140, 0.02)',
      lineWidth: 2,
    })

    const data = points
      .filter((p) => p.close != null && p.t)
      .map((p) => {
        const d = new Date(p.t)
        const time = Math.floor(d.getTime() / 1000) as Time
        return { time, value: p.close as number }
      })
      .sort((a, b) => Number(a.time) - Number(b.time))

    const dedup: typeof data = []
    for (const pt of data) {
      if (dedup.length && dedup[dedup.length - 1].time === pt.time) {
        dedup[dedup.length - 1] = pt
      } else {
        dedup.push(pt)
      }
    }

    if (dedup.length) {
      series.setData(dedup)
      chart.timeScale().fitContent()
    }

    const markers = alerts
      .map((a) => {
        if (!a.created_at) return null
        const t = Math.floor(new Date(a.created_at).getTime() / 1000) as Time
        const bull = a.direction === 'bullish'
        return {
          time: t,
          position: 'aboveBar' as const,
          color: bull ? '#3dd68c' : '#ff6b4a',
          shape: (bull ? 'arrowUp' : 'arrowDown') as 'arrowUp' | 'arrowDown',
          text: a.direction.slice(0, 4),
        }
      })
      .filter(Boolean) as {
      time: Time
      position: 'aboveBar'
      color: string
      shape: 'arrowUp' | 'arrowDown'
      text: string
    }[]

    if (markers.length) {
      createSeriesMarkers(
        series,
        markers.sort((a, b) => Number(a.time) - Number(b.time)),
      )
    }

    const ro = new ResizeObserver(() => {
      if (ref.current) {
        chart.applyOptions({ width: ref.current.clientWidth })
      }
    })
    ro.observe(ref.current)
    chart.applyOptions({ width: ref.current.clientWidth })

    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [points, alerts, height])

  if (!points.length) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-line bg-panel/40 text-sm text-mist"
        style={{ height }}
      >
        No price history
      </div>
    )
  }

  return <div ref={ref} className="w-full overflow-hidden rounded-lg" />
}
