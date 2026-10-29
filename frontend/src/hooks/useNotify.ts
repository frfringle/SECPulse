import { useCallback, useEffect, useState } from 'react'

const SOUND_KEY = 'secpulse.notify.sound'
const PERM_ASKED = 'secpulse.notify.asked'

function playBeep() {
  try {
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = 880
    gain.gain.value = 0.04
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start()
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25)
    osc.stop(ctx.currentTime + 0.26)
    setTimeout(() => ctx.close(), 400)
  } catch {
    /* ignore */
  }
}

export function useNotify() {
  const [soundOn, setSoundOn] = useState(() => localStorage.getItem(SOUND_KEY) !== '0')
  const [perm, setPerm] = useState<NotificationPermission>(
    typeof Notification !== 'undefined' ? Notification.permission : 'denied',
  )

  useEffect(() => {
    localStorage.setItem(SOUND_KEY, soundOn ? '1' : '0')
  }, [soundOn])

  const requestPermission = useCallback(async () => {
    if (typeof Notification === 'undefined') return
    const result = await Notification.requestPermission()
    setPerm(result)
    localStorage.setItem(PERM_ASKED, '1')
  }, [])

  const notifyNew = useCallback(
    (title: string, body: string) => {
      if (soundOn) playBeep()
      if (typeof Notification !== 'undefined' && perm === 'granted') {
        try {
          new Notification(title, { body, silent: true })
        } catch {
          /* ignore */
        }
      }
    },
    [perm, soundOn],
  )

  return {
    soundOn,
    setSoundOn,
    perm,
    requestPermission,
    notifyNew,
    askedBefore: localStorage.getItem(PERM_ASKED) === '1',
  }
}
