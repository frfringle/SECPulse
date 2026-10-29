import type { Health } from '../types'

export function StatusDot({ health }: { health: Health | null }) {
  const ok = health?.status === 'ok' && !health.last_poll_error
  const ollama = health?.ollama_reachable
  const uspto = health?.uspto_enabled
  const color = !health ? 'bg-mist' : ok ? 'bg-bull' : 'bg-bear'
  const label = !health
    ? 'Connecting…'
    : ok
      ? `Live · queue ${health.queue_size}${ollama ? '' : ' · Ollama off'}${
          uspto ? ' · USPTO on' : health?.uspto_configured ? ' · USPTO idle' : ''
        }`
      : health.last_poll_error || 'Degraded'

  return (
    <div
      className="flex items-center gap-2 text-xs text-mist"
      title={label}
      aria-label={label}
    >
      <span className="relative flex h-2.5 w-2.5">
        <span
          className={`absolute inline-flex h-full w-full rounded-full ${color} opacity-60 ${ok ? 'animate-pulse-dot' : ''}`}
        />
        <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${color}`} />
      </span>
      <span className="hidden sm:inline max-w-[14rem] truncate">{label}</span>
    </div>
  )
}
