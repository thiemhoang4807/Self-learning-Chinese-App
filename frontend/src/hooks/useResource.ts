import { useEffect, useState } from 'react'
import { api, errorMessage } from '../lib/api'

export function useResource<T>(path: string | null) {
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
    api<T>(path, { signal: controller.signal })
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
  }, [path, revision])

  return { data, setData, error, loading, reload: () => setRevision(value => value + 1) }
}
