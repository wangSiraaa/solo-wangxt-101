const BASE = '/api'

async function req(path, options = {}) {
  const resp = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const data = await resp.json()
      detail = data.detail || JSON.stringify(data)
    } catch { /* keep statusText */ }
    throw new Error(detail)
  }
  return resp.status === 204 ? null : resp.json()
}

export const api = {
  get: (path) => req(path),
  post: (path, body) => req(path, { method: 'POST', body: JSON.stringify(body || {}) }),
}
