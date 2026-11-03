// 极简 API 封装：基于 fetch，不引入额外依赖。BASE 留空，由 vite 代理 / 后端同源处理。
import { reactive } from 'vue'

const BASE = ''

// 后端连接状态。以前只有 App.vue 在页面加载时查一次，后端中途挂了界面永远显示"服务正常"，
// 表现就是「页面卡住不动」——实际是每个请求都连不上。现在由所有请求共同维护。
//   ok         当前是否连得上（连续失败达到阈值才翻红，避免偶发抖动闪红）
//   lastError  最近一次错误文案
//   checkedAt  最近一次成功的时间戳
export const conn = reactive({ ok: true, lastError: '', checkedAt: 0, failures: 0 })

function markOk() {
  conn.ok = true
  conn.lastError = ''
  conn.failures = 0
  conn.checkedAt = Date.now()
}

function markFail(e, hard = false) {
  conn.failures += 1
  conn.lastError = (e && e.message) || String(e || '')
  // hard=true 用于纯探测请求（健康检查），一次失败即判定断开；
  // 普通业务请求容许一次抖动，连续两次才翻红。
  if (hard || conn.failures >= 2) conn.ok = false
}

// 默认超时：不做限制的话，后端进程活着但不响应时 fetch 会一直挂着（浏览器默认要几分钟），
// 页面就一直"转圈但不动"。慢接口在调用处单独放宽。
const DEFAULT_TIMEOUT = 60000

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
  const { timeout = DEFAULT_TIMEOUT, signal, hard = false, ...rest } = opts
  const ctrl = new AbortController()
  let timer = null
  if (timeout > 0) timer = setTimeout(() => ctrl.abort(), timeout)
  const abortByOuter = () => ctrl.abort()
  if (signal) {
    if (signal.aborted) ctrl.abort()
    else signal.addEventListener('abort', abortByOuter, { once: true })
  }

  let res
  try {
    res = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...rest,
      signal: ctrl.signal,
    })
  } catch (e) {
    const aborted = e && e.name === 'AbortError'
    const err = new Error(aborted ? '请求超时，后端没有响应' : '无法连接后端服务')
    markFail(err, hard)
    throw err
  } finally {
    if (timer) clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', abortByOuter)
  }

  let data = null
  const text = await res.text()
  if (text) {
    try { data = JSON.parse(text) } catch (e) { data = text }
  }
  if (!res.ok) {
    // 4xx/5xx 说明后端是通的，只是这次操作失败，不算连接断开
    markOk()
    const detail = (data && data.detail) || ''
    throw new Error(detail || ('HTTP ' + res.status))
  }
  markOk()
  return data || {}
}

// SSE / 长连接共用：把 fetch 失败归到连接状态里，避免流式接口挂了没人知道
async function openStream(path, opts = {}) {
  try {
    const res = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...opts,
    })
    if (!res.ok || !res.body) throw new Error('HTTP ' + res.status)
    markOk()
    return res
  } catch (e) {
    markFail(new Error(e && e.name === 'TypeError' ? '无法连接后端服务' : (e.message || '流式请求失败')))
    throw e
  }
}

// 逐块解析 SSE，三个流式接口共用（原来是三份几乎一模一样的循环）
async function readSSE(res, onEvent) {
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
}

export const api = {
  // 轻量健康检查：App.vue 定时调它，用来判断「后端还在不在」。
  // 注意失败只在 req 内部 markFail 一次——以前这里 .catch 里又补一次，
  // 一次超时就被记成两次失败，页面状态直接判定成断开，横幅一闪一闪。
  health: () => req('/api/health', { timeout: 8000, hard: true }).then((d) => {
    if (!d || d.ok !== true) {
      markFail(new Error('后端返回异常'), true)
      throw new Error('后端返回异常')
    }
    return d
  }),
  state: () => req('/api/state'),
  products: (params) => req('/api/products' + buildQuery(params)),
  facets: () => req('/api/products/facets'),
  specStats: () => req('/api/spec-stats'),
  changes: (params) => req('/api/changes' + buildQuery(params)),
  changesExpand: (params) => req('/api/changes/expand' + buildQuery(params)),
  // 同步 / 知识库重建 / 大模型生成都可能跑几十秒到十几分钟，单独放宽超时
  sync: () => req('/api/sync', { method: 'POST', timeout: 600000 }),
  kbDocs: () => req('/api/kb/docs'),
  kbDoc: (docId) => req('/api/kb/doc/' + encodeURIComponent(docId)),
  kbDocRebuild: (docId) => req('/api/kb/doc/' + encodeURIComponent(docId) + '/rebuild', {
    method: 'POST', timeout: 300000,
  }),
  kbDocSave: (docId, body) => req('/api/kb/doc/' + encodeURIComponent(docId), {
    method: 'PUT', timeout: 300000, body: JSON.stringify(body),
  }),
  kbCleanText: (text) => req('/api/kb/clean-text', {
    method: 'POST', body: JSON.stringify({ text }),
  }),
  kbChunks: (q, limit) => req('/api/kb/chunks' + buildQuery({ q: q || '', limit: limit || 80 })),
  kbIngest: () => req('/api/kb/ingest', { method: 'POST', timeout: 600000 }),
  kbRebuild: () => req('/api/kb/rebuild', { method: 'POST', timeout: 900000 }),
  kbEmbed: () => req('/api/kb/embed', { method: 'POST', timeout: 900000 }),
  kbClean: (dryRun) => req('/api/kb/clean' + buildQuery({ dry_run: dryRun ? 1 : 0 }),
    { method: 'POST', timeout: 300000 }),
  ask: (q, audience, dry_run, history) =>
    req('/api/ask', {
      method: 'POST',
      timeout: 180000,
      body: JSON.stringify({ q, audience, dry_run, history: history || [] }),
    }),
  kuanproList: (params) => req('/api/kuanpro/list' + buildQuery(params)),
  kuanproFacets: () => req('/api/kuanpro/facets'),
  kuanproToggle: (product_id, on_sale) =>
    req('/api/kuanpro/toggle', { method: 'POST', body: JSON.stringify({ product_id, on_sale }) }),
  // 批量上下架：800 多条未上架逐条点不现实；后端逐条转发、失败不中断，返回明细
  kuanproToggleBatch: (product_ids, on_sale) =>
    req('/api/kuanpro/toggle-batch', {
      method: 'POST', timeout: 300000,
      body: JSON.stringify({ product_ids, on_sale }),
    }),
  // 运行状态（设置页用）：登录有效期、上次同步结果、全局搜索
  loginStatus: () => req('/api/login-status'),
  syncStatus: (limit) => req('/api/sync-status' + buildQuery({ limit: limit || 6 })),
  search: (q) => req('/api/search' + buildQuery({ q }), { timeout: 20000 }),
  askStream: async (q, audience, onEvent, history) => {
    const res = await openStream('/api/ask/stream', {
      method: 'POST',
      body: JSON.stringify({ q, audience, history: history || [] }),
    })
    await readSSE(res, onEvent)
  },
  // 小红书
  xhsStats: (days) => req('/api/xhs/stats' + buildQuery({ days: days || 7 })),
  xhsHistory: (limit) => req('/api/xhs/history' + buildQuery({ limit: limit || 50 })),
  xhsAssess: (post_content, region) =>
    req('/api/xhs/assess', { method: 'POST', body: JSON.stringify({ post_content, region }) }),
  xhsReply: (body) => req('/api/xhs/reply', { method: 'POST', timeout: 180000, body: JSON.stringify(body) }),
  xhsRun: (body) => req('/api/xhs/run', { method: 'POST', body: JSON.stringify(body) }),
  xhsRunStatus: () => req('/api/xhs/run/status', { timeout: 12000 }),
  xhsConfig: () => req('/api/xhs/config'),
  settings: () => req('/api/settings'),
  saveSettings: (body) => req('/api/settings', { method: 'POST', body: JSON.stringify(body) }),
  testLlm: (body) => req('/api/settings/test-llm', { method: 'POST', timeout: 180000, body: JSON.stringify(body) }),
  captcha: () => req('/api/captcha'),
  login: (code) => req('/api/login', { method: 'POST', body: JSON.stringify({ code }) }),
  // 同步（SSE 流式进度）
  syncStream: async (onEvent) => {
    const res = await openStream('/api/sync/stream', { method: 'POST' })
    await readSSE(res, onEvent)
  },
  kuanproSyncStream: async (onEvent) => {
    const res = await openStream('/api/kuanpro/sync', { method: 'POST' })
    await readSSE(res, onEvent)
  },
}
