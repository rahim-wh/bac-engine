import { useEffect, useState } from 'react'
import { api } from './api.js'

export function useDebounce(value, ms = 300) {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}

// Fetch with cancellation of stale requests + loading/error state.
export function useApi(path, params, enabled = true) {
  const [state, setState] = useState({ data: null, error: null, loading: false })
  const key = JSON.stringify([path, params, enabled])
  useEffect(() => {
    if (!enabled) return
    const ctl = new AbortController()
    setState((s) => ({ ...s, loading: true, error: null }))
    api(path, params, ctl.signal)
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((e) => { if (e.name !== 'AbortError') setState({ data: null, error: e.message, loading: false }) })
    return () => ctl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return state
}
