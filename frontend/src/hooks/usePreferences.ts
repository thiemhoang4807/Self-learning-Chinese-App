import { useCallback, useEffect, useRef, useState } from 'react'
import type { Preferences } from '../types'
import { errorMessage } from '../lib/api'
import { getPreferences, patchPreferences } from '../lib/backup'

const preferenceKey = 'mandarin-study.preferences'

function initialPreferences(): Preferences {
  try {
    const saved = JSON.parse(localStorage.getItem(preferenceKey) || '{}')
    return {
      theme: saved.theme === 'dark' ? 'dark' : 'light',
      pinyin: saved.pinyin === true,
    }
  } catch {
    return { theme: 'light', pinyin: false }
  }
}

export function usePreferences() {
  const [preferences, setPreferences] = useState(initialPreferences)
  const [preferenceError, setPreferenceError] = useState('')
  const current = useRef(preferences)
  const dirty = useRef<Partial<Preferences>>({})
  const hydrated = useRef(false)
  const queue = useRef<Promise<void>>(Promise.resolve())

  const apply = useCallback((next: Preferences) => {
    current.current = next
    setPreferences(next)
    document.documentElement.dataset.theme = next.theme
    try { localStorage.setItem(preferenceKey, JSON.stringify(next)) } catch { /* Storage may be disabled. */ }
  }, [])

  const flushPreferences = useCallback(() => {
    const operation = queue.current.then(async () => {
      if (!hydrated.current) {
        const remote = await getPreferences()
        if (remote) apply({ ...remote, ...dirty.current })
        else dirty.current = { ...current.current }
        hydrated.current = true
      }
      const pending = dirty.current
      if (Object.keys(pending).length) {
        const remote = await patchPreferences(pending)
        const remaining = { ...dirty.current }
        if (remaining.theme === pending.theme) delete remaining.theme
        if (remaining.pinyin === pending.pinyin) delete remaining.pinyin
        dirty.current = remaining
        apply({ ...remote, ...remaining })
      }
      setPreferenceError('')
    })
    queue.current = operation.catch(cause => {
      setPreferenceError(errorMessage(cause))
    })
    return operation
  }, [apply])

  useEffect(() => {
    apply(current.current)
    function sync() { void flushPreferences().catch(() => {}) }
    sync()
    window.addEventListener('online', sync)
    return () => window.removeEventListener('online', sync)
  }, [apply, flushPreferences])

  function update(patch: Partial<Preferences>) {
    dirty.current = { ...dirty.current, ...patch }
    apply({ ...current.current, ...patch })
    void flushPreferences().catch(() => {})
  }

  function applyRestoredPreferences(saved: Preferences) {
    hydrated.current = true
    dirty.current = {}
    setPreferenceError('')
    apply(saved)
  }

  return {
    preferences,
    preferenceError,
    flushPreferences,
    applyRestoredPreferences,
    toggleTheme: () => update({ theme: current.current.theme === 'dark' ? 'light' : 'dark' }),
    togglePinyin: () => update({ pinyin: !current.current.pinyin }),
  }
}
