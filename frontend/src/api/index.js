// 极简 API 封装：基于 fetch，不引入额外依赖。BASE 留空，由 vite 代理 / 后端同源处理。
const BASE = ''

function buildQuery(params) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null || v === '') continue
    sp.append(k, v)
  }
  const s = sp.toString()
  return s ? '?' + s : ''
}

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  let data = null
  const text = await res.text()
  if (text) {
    try { data = JSON.parse(text) } catch (e) { data = text }
  }
  if (!res.ok) {
    const detail = (data && data.detail) || ''
    throw new Error(detail || ('HTTP ' + res.status))
  }
  return data || {}
}

export const api = {
  state: () => req('/api/state'),
  products: (params) => req('/api/products' + buildQuery(params)),
  facets: () => req('/api/products/facets'),
  specStats: () => req('/api/spec-stats'),
  changes: (params) => req('/api/changes' + buildQuery(params)),
  sync: () => req('/api/sync', { method: 'POST' }),
  kbDocs: () => req('/api/kb/docs'),
  kbChunks: (q, limit) => req('/api/kb/chunks' + buildQuery({ q: q || '', limit: limit || 80 })),
  kbIngest: () => req('/api/kb/ingest', { method: 'POST' }),
  kbRebuild: () => req('/api/kb/rebuild', { method: 'POST' }),
  ask: (q, audience, dry_run) =>
    req('/api/ask', { method: 'POST', body: JSON.stringify({ q, audience, dry_run }) }),
  kuanproList: (params) => req('/api/kuanpro/list' + buildQuery(params)),
  kuanproFacets: () => req('/api/kuanpro/facets'),
  kuanproToggle: (product_id, on_sale) =>
    req('/api/kuanpro/toggle', { method: 'POST', body: JSON.stringify({ product_id, on_sale }) }),
  askStream: async (q, audience, onEvent) => {
    const res = await fetch(BASE + '/api/ask/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q, audience }),
    })
    if (!res.ok || !res.body) throw new Error('HTTP ' + res.status)
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const line = chunk.split('\n').find((l) => l.startsWith('data:'))
        if (!line) continue
        const data = line.slice(5).trim()
        if (data === '[DONE]') return
        try { onEvent(JSON.parse(data)) } catch (e) { /* 忽略坏块 */ }
      }
    }
  },
  settings: () => req('/api/settings'),
  saveSettings: (body) => req('/api/settings', { method: 'POST', body: JSON.stringify(body) }),
  testLlm: (body) => req('/api/settings/test-llm', { method: 'POST', body: JSON.stringify(body) }),
  captcha: () => req('/api/captcha'),
  login: (code) => req('/api/login', { method: 'POST', body: JSON.stringify({ code }) }),
  // 同步（SSE 流式进度）
  syncStream: async (onEvent) => {
    const res = await fetch(BASE + '/api/sync/stream', { method: 'POST' })
    if (!res.ok || !res.body) throw new Error('HTTP ' + res.status)
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const line = chunk.split('\n').find((l) => l.startsWith('data:'))
        if (!line) continue
        const data = line.slice(5).trim()
        if (data === '[DONE]') return
        try { onEvent(JSON.parse(data)) } catch (e) {}
      }
    }
  },
  kuanproSyncStream: async (onEvent) => {
    const res = await fetch(BASE + '/api/kuanpro/sync', { method: 'POST' })
    if (!res.ok || !res.body) throw new Error('HTTP ' + res.status)
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const line = chunk.split('\n').find((l) => l.startsWith('data:'))
        if (!line) continue
        const data = line.slice(5).trim()
        if (data === '[DONE]') return
        try { onEvent(JSON.parse(data)) } catch (e) {}
      }
    }
  },
}
