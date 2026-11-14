// Thin fetch wrapper: builds query strings (arrays repeat the key) and normalises errors.
export function qs(params) {
  const u = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return
    ;(Array.isArray(v) ? v : [v]).forEach((x) => u.append(k, x))
  })
  return u.toString()
}

export async function api(path, params = {}, signal) {
  const res = await fetch(`/api${path}?${qs(params)}`, { signal })
  if (!res.ok) {
    let msg = res.statusText
    try { msg = (await res.json()).detail || msg } catch { /* non-JSON error body */ }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return res.json()
}

export const exportUrl = (params) => `/api/records/export?${qs(params)}`
