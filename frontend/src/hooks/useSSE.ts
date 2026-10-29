import { useEffect, useRef } from 'react'
import type { Alert } from '../types'

type Handlers = {
  onAlert: (alert: Alert) => void
}

export function useSSE({ onAlert }: Handlers) {
  const handler = useRef(onAlert)
  handler.current = onAlert

  useEffect(() => {
    const es = new EventSource('/api/stream')
    const onMessage = (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data) as Alert
        handler.current(data)
      } catch {
        /* ignore malformed */
      }
    }
    es.addEventListener('alert', onMessage as EventListener)
    return () => {
      es.removeEventListener('alert', onMessage as EventListener)
      es.close()
    }
  }, [])
}
