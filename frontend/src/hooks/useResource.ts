import { useEffect, useState } from 'react'
import { api, errorMessage } from '../lib/api'

const loadResource = <T,>(path: string, signal: AbortSignal) => api<T>(path, { signal })

export function useResource<T>(path: string | null, load: (path: string, signal: AbortSignal) => Promise<T> = loadResource<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(Boolean(path))
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    setData(null)
    setError('')
    if (!path) {
      setLoading(false)
      return
    }
    const controller = new AbortController()
    setLoading(true)
    load(path, controller.signal)
      .then(result => {
        if (!controller.signal.aborted) setData(result)
      })
      .catch(cause => {
        if (!controller.signal.aborted) setError(errorMessage(cause))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [path, revision, load])

  return { data, setData, error, loading, reload: () => setRevision(value => value + 1) }
}
