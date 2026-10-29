import { Link } from 'react-router-dom'
import type { Health } from '../types'
import { StatusDot } from './StatusDot'

type Props = {
  health: Health | null
  soundOn: boolean
  onToggleSound: () => void
  onEnableNotify: () => void
  notifyPerm: NotificationPermission
}

export function Header({
  health,
  soundOn,
  onToggleSound,
  onEnableNotify,
  notifyPerm,
}: Props) {
  return (
    <header className="animate-fade-up border-b border-line/80">
      <div className="mx-auto flex max-w-5xl items-end justify-between gap-4 px-4 pb-5 pt-8 sm:px-6">
        <div>
          <Link to="/" className="group block">
            <p className="font-display text-4xl font-extrabold tracking-tight text-foam sm:text-5xl">
              SEC<span className="text-accent">Pulse</span>
            </p>
            <p className="mt-1 max-w-md text-sm text-mist">
              Live EDGAR alerts — scored locally, never trading advice.
            </p>
          </Link>
        </div>
        <div className="flex flex-col items-end gap-3 pb-1">
          <StatusDot health={health} />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onToggleSound}
              className="rounded-md border border-line bg-panel px-2.5 py-1 text-xs text-mist transition hover:border-accent/40 hover:text-foam"
            >
              Sound {soundOn ? 'on' : 'off'}
            </button>
            {notifyPerm !== 'granted' && (
              <button
                type="button"
                onClick={onEnableNotify}
                className="rounded-md border border-line bg-panel px-2.5 py-1 text-xs text-mist transition hover:border-accent/40 hover:text-foam"
              >
                Notify
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}
