import { useCallback, useEffect, useRef, useState } from 'react'

export interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  retry: () => void
}

/**
 * Small data-fetching hook: tracks loading/error state, ignores stale
 * responses and exposes a retry callback.
 */
export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: readonly unknown[],
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const requestId = useRef(0)

  // The caller controls the dependency list; the fetcher itself is expected
  // to be re-created or stable per deps.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableFetcher = useCallback(fetcher, deps)

  useEffect(() => {
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    stableFetcher()
      .then((result) => {
        if (requestId.current !== id) return
        setData(result)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (requestId.current !== id) return
        setError(err instanceof Error ? err.message : 'Request failed')
        setLoading(false)
      })
  }, [stableFetcher, attempt])

  const retry = useCallback(() => setAttempt((a) => a + 1), [])

  return { data, loading, error, retry }
}

/** Debounce a changing value by `delay` ms. */
export function useDebouncedValue<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
