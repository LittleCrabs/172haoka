<template>
  <div class="xhs-page">
    <!-- 运行控制：严格分行的固定布局。
         以前参数、开关、按钮全挤在一个 flex 行里，按钮会被参数挤到下一行；
         开关一拨，按钮文案从「试跑一轮（不发送）」变成「启动一轮（会发评论）」，
         宽度一变整块就重排，下面所有卡片跟着上下跳。现在标题/参数/说明/日志各占一行，
         宽度变化只会在行内消化，不再互相挤压。 -->
    <el-card shadow="never" class="card ctrl-card">
      <div class="ctrl-head">
        <span class="ctrl-title">运行控制</span>
        <span class="run-state" :class="{ live: run.running }">
          <span class="dot"></span>
          <span>{{ run.running ? '运行中' : '空闲' }}</span>
          <span v-if="run.running && run.pid" class="run-pid">PID {{ run.pid }}</span>
        </span>
        <div class="ctrl-actions">
          <el-button
            :type="form.dry ? 'warning' : 'primary'"
            :icon="VideoPlay"
            :loading="starting"
            :disabled="run.running"
            class="run-btn"
            @click="startRun"
          >
            {{ form.dry ? '试跑一轮（不发送）' : '启动一轮（会发评论）' }}
          </el-button>
          <el-button :icon="Refresh" :loading="loading" @click="loadAll()">刷新数据</el-button>
          <el-tooltip content="恢复默认参数" placement="top">
            <el-button :icon="RefreshLeft" text circle class="reset-btn" @click="resetForm" />
          </el-tooltip>
        </div>
      </div>

      <!-- 参数行：成组排列，标签和输入框不拆开，换行只发生在整组之间 -->
      <div class="ctrl-params">
        <label class="p-item">
          <span class="lbl">命中上限</span>
          <el-input-number v-model="form.limit" :min="1" :max="50" size="small" controls-position="right" class="num" />
        </label>
        <label class="p-item">
          <span class="lbl">浏览</span>
          <el-input-number v-model="form.max_scan" :min="1" :max="300" size="small" controls-position="right" class="num" />
          <span class="lbl">帖</span>
        </label>
        <label class="p-item">
          <span class="lbl">每</span>
          <el-input-number v-model="form.refresh_every" :min="3" :max="60" size="small" controls-position="right" class="num" />
          <span class="lbl">帖刷新首页</span>
        </label>
        <label class="p-item">
          <span class="lbl">限时</span>
          <el-input-number v-model="form.max_minutes" :min="1" :max="60" size="small" controls-position="right" class="num" />
          <span class="lbl">分钟</span>
        </label>
        <div class="p-item p-switch">
          <el-switch v-model="form.dry" active-text="只判定不发" size="small" />
        </div>
        <div class="p-item p-switch">
          <el-switch
            v-model="form.hide_browser"
            active-text="隐藏浏览器"
            size="small"
            title="隐藏后窗口不进任务栏；若需要手动过验证码，关掉它再启动"
          />
        </div>
      </div>

      <!-- 说明文字默认收起：它是静态内容，展开会推高页面，默认摆出来只会显得拥挤 -->
      <div class="ctrl-note">
        <button class="note-toggle" @click="toggleNote">
          <el-icon><InfoFilled /></el-icon>
          {{ noteOpen ? '收起说明' : '参数说明' }}
        </button>
        <div v-show="noteOpen" class="note-body">
          点击「启动一轮」会弹出一个专用的 Chrome 窗口自动下滑浏览首页信息流，命中目标人群就发评论。
          每日发送上限 20 条、每帖随机间隔 90–240 秒、命中分数低于 2 不发。建议先用「只判定不发」跑一轮看效果。
          <br />
          首页顶部（刚刷新出来的那屏）命中率最高，越往下滑越偏——所以默认<b>每浏览 10 帖就重开首页换一批</b>，
          「浏览 40 帖」是本轮总预算，40 帖 ≈ 4 批。连续滑动加载不出新内容时最多救 3 次；
          单轮超过设定分钟数强制结束。
          <br />
          这些参数会自动记在本机浏览器里，刷新页面或切走再回来都还是这套；想还原点右侧的 ↺。
        </div>
      </div>

      <!-- 日志区常驻固定高度：以前只在运行时渲染，一启动就把下面整页推下去一跳。
           折叠状态记在本机，展开/收起只由你手动触发。 -->
      <div class="run-log">
        <div class="log-head">
          <span class="log-title">实时输出</span>
          <span class="log-sub">
            <template v-if="run.running">
              命中上限 {{ run.params.limit || form.limit }} 条 / 浏览 {{ run.params.max_scan || form.max_scan }} 帖 / 每 {{ run.params.refresh_every || form.refresh_every }} 帖换一批
            </template>
            <template v-else-if="run.finished_at">
              {{ run.state === 'failed' ? '上次异常退出于' : '上次结束于' }}
              {{ (run.finished_at || '').replace('T', ' ') }}
            </template>
            <template v-else>本轮未启动</template>
          </span>
          <button class="log-toggle" @click="toggleLog">{{ logOpen ? '收起' : '展开' }}</button>
        </div>
        <pre v-show="logOpen" ref="logBox" :class="{ idle: !run.running }">{{ logText }}</pre>
      </div>
    </el-card>

    <!-- 数据概览 -->
    <div class="stat-row">
      <el-card shadow="never" class="stat" v-for="s in statCards" :key="s.label">
        <div class="stat-val" :style="{ color: s.color }">{{ s.value }}</div>
        <div class="stat-label">{{ s.label }}</div>
        <div class="stat-sub">{{ s.sub }}</div>
      </el-card>
    </div>

    <!-- 分布 -->
    <div class="two-col">
      <el-card shadow="never" class="card">
        <template #header><span class="card-title">目标人群得分分布</span></template>
        <div v-if="!stats.score_dist.length" class="empty">暂无命中记录</div>
        <div v-else class="bars">
          <div v-for="d in stats.score_dist" :key="d.score" class="bar-row">
            <span class="bar-key">{{ d.score }} 分</span>
            <div class="bar-track">
              <div class="bar-fill" :style="{ width: barWidth(d.count, maxScoreCount), background: scoreColor(d.score) }"></div>
            </div>
            <span class="bar-val">{{ d.count }} 条</span>
          </div>
        </div>
        <div class="rule-line">
          <el-tooltip :content="'得分规则（设置页可调）：' + weightText" placement="top" :show-after="300">
            <span class="rule-text">得分规则（设置页可调）：{{ weightText }}</span>
          </el-tooltip>
          <button class="note-toggle" @click="toggleRule">{{ ruleOpen ? '收起' : '判定门槛' }}</button>
        </div>
        <div v-show="ruleOpen" class="hint">
          判定门槛：必须命中「办卡意图」或「流量需求」之一，或「资费敏感 + 学生校园」同时出现；
          只命中泛词（套餐、便宜、学生）不足以回复。正文若在聊医疗、金融、餐饮、招聘等无关场景且
          没有手机卡语境，直接跳过。
        </div>
      </el-card>

      <el-card shadow="never" class="card">
        <template #header><span class="card-title">跳过原因 / 人格分布</span></template>
        <div class="mini-grid">
          <div>
            <div class="sub-title">未发送原因</div>
            <div v-if="!stats.skip_dist.length" class="empty">暂无</div>
            <div v-for="s in stats.skip_dist" :key="s.reason" class="mini-row">
              <span>{{ s.reason }}</span><b>{{ s.count }}</b>
            </div>
          </div>
          <div>
            <div class="sub-title">命中人格</div>
            <div v-if="!stats.tone_dist.length" class="empty">暂无</div>
            <div v-for="t in stats.tone_dist" :key="t.tone" class="mini-row">
              <span>{{ t.tone }}</span><b>{{ t.count }}</b>
            </div>
          </div>
        </div>
        <div class="sub-title mt10">命中地区</div>
        <div class="tags">
          <el-tag v-for="r in stats.region_dist" :key="r.region" size="small" effect="plain" class="tag">
            {{ r.region }} · {{ r.count }}
          </el-tag>
          <span v-if="!stats.region_dist.length" class="empty">暂无</span>
        </div>
      </el-card>
    </div>

    <!-- 试算器 -->
    <el-card shadow="never" class="card">
      <template #header>
        <span class="card-title">判定试算</span>
        <span class="header-hint">粘贴一段笔记正文，看它会得多少分、命中哪些信号（不调用大模型）</span>
      </template>
      <el-input
        v-model="probe.text"
        type="textarea"
        :rows="4"
        placeholder="例：最近流量老是不够用，月租还贵，想换个便宜点的套餐，有没有推荐？IP属地：河南"
      />
      <div class="probe-actions">
        <el-input v-model="probe.region" placeholder="地区（可空，留空自动抽取）" class="region-input" clearable />
        <el-button :icon="Search" :loading="probing" @click="doAssess">判分</el-button>
        <el-button type="primary" plain :icon="ChatDotRound" :loading="replying" :disabled="!probe.text" @click="doReply">
          生成回复预览
        </el-button>
      </div>

      <div v-if="assess" class="assess-box">
        <div class="assess-head">
          <el-tag :type="assess.should_reply ? 'success' : 'info'" effect="dark" size="small">
            {{ assess.should_reply ? '命中目标人群' : '非目标人群' }}
          </el-tag>
          <span class="score-big" :style="{ color: scoreTextColor(assess.score) }">{{ assess.score }} 分</span>
          <span class="assess-region">地区：{{ assess.region || '未识别' }}</span>
          <span class="assess-region">该地区可办卡：{{ assess.region_available ?? '—' }}</span>
        </div>
        <div class="assess-reason">{{ assess.reason }}</div>
        <div class="tags mt6">
          <el-tag
            v-for="s in assess.signals" :key="s.category"
            size="small" class="tag"
            :type="s.level === 'soft' ? 'info' : 'primary'"
            :effect="s.level === 'strong' ? 'dark' : 'plain'"
          >
            {{ s.category }}<span v-if="s.level === 'strong'" class="lv">强</span>（{{ s.hits.join('、') }}）
          </el-tag>
        </div>
        <div v-if="replyText" class="reply-box">
          <div class="sub-title">生成的回复</div>
          <div class="reply-text">{{ replyText }}</div>
        </div>
        <el-alert v-if="replyError" :title="replyError" type="error" :closable="false" show-icon class="mt10" />
      </div>
    </el-card>

    <!-- 已回复记录 -->
    <el-card shadow="never" class="card">
      <template #header>
        <span class="card-title">回复记录（{{ history.length }}）</span>
        <span class="header-hint">
          「仅生成」= 只产出了话术、没有发到小红书（试跑模式，或因去重跳过）
        </span>
      </template>
      <!-- 固定高度而不是 max-height：行数从 0 涨到十几条时，表格高度变化会把
           下面的卡片推来推去；固定后新增记录只在表格内部滚动区里出现。 -->
      <el-table :data="history" size="small" stripe height="320">
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ row.replied_at || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag v-if="row.delivered_at" type="success" size="small" effect="light">已发送</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">仅生成</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="得分" width="80">
          <template #default="{ row }">
            <b :style="{ color: scoreTextColor(row.score) }">{{ row.score }}</b>
          </template>
        </el-table-column>
        <el-table-column prop="region" label="地区" width="90">
          <template #default="{ row }">{{ row.region || '—' }}</template>
        </el-table-column>
        <el-table-column prop="tone" label="人格" width="110" />
        <!-- 回复正文按合规要求不点名、不带链接；这张卡是后台替他选的，供跟进时直接发 -->
        <el-table-column label="推荐卡 / 客户下单链接" width="240">
          <template #default="{ row }">
            <template v-if="row.order_url">
              <div class="rec-name" :title="row.product_name">{{ row.product_name }}</div>
              <div class="rec-meta">
                <span>{{ recMeta(row) }}</span>
                <el-link type="primary" :href="row.order_url" target="_blank"
                  rel="noopener" class="rec-link">下单链接 ↗</el-link>
              </div>
            </template>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="回复内容" min-width="300">
          <template #default="{ row }">
            <el-tooltip :content="row.reply_text" placement="top" :show-after="400">
              <span class="reply-cell">{{ row.reply_text }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="帖子" width="110">
          <template #default="{ row }">
            <span class="mono">{{ (row.post_id || '').slice(0, 10) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 最近事件 -->
    <el-card shadow="never" class="card">
      <template #header>
        <span class="card-title">最近运行事件</span>
        <span class="header-hint">最近一轮：{{ stats.last_run.started_at || '—' }} · {{ stats.last_run.mode || '—' }}</span>
      </template>
      <el-table :data="stats.recent" size="small" height="360" stripe>
        <el-table-column label="时间" width="150">
          <template #default="{ row }">{{ (row.ts || '').replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="事件" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="eventType(row.event)" effect="plain">{{ eventLabel(row.event) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="帖子 / 地区" width="220">
          <template #default="{ row }">
            <span class="mono">{{ (row.post_id || '').slice(0, 10) }}</span>
            <span v-if="row.region" class="ml6">{{ row.region }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="380">
          <template #default="{ row }">
            <span v-if="row.score !== undefined" class="ml0">得分 {{ row.score }} · </span>
            {{ row.reply || row.reason || row.err || row.title || '' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { Refresh, RefreshLeft, VideoPlay, Search, ChatDotRound, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

defineOptions({ name: 'XhsView' })

const loading = ref(false)
const starting = ref(false)
const probing = ref(false)
const replying = ref(false)

// 折叠状态记在本机。日志默认收起：常驻一个黑框太占地方，
// 想看实时输出时点「展开」，或者启动时自动帮你展开。
const UI_KEY = 'xhs.ui'
const UI_DEFAULTS = { note: false, log: false, rule: false }
function loadUi() {
  try {
    const saved = JSON.parse(localStorage.getItem(UI_KEY) || '{}')
    const out = { ...UI_DEFAULTS }
    for (const k of Object.keys(UI_DEFAULTS)) {
      if (typeof saved[k] === 'boolean') out[k] = saved[k]
    }
    return out
  } catch {
    return { ...UI_DEFAULTS }
  }
}
const ui = loadUi()
const noteOpen = ref(ui.note)
const logOpen = ref(ui.log)
const ruleOpen = ref(ui.rule)
// 用户自己点过展开/收起之后，就不再自动帮他切换，免得抢控制权
let uiTouched = localStorage.getItem(UI_KEY) !== null

function saveUi() {
  try {
    localStorage.setItem(UI_KEY, JSON.stringify({ note: noteOpen.value, log: logOpen.value, rule: ruleOpen.value }))
  } catch { /* 隐私模式忽略 */ }
}
function toggleNote() { noteOpen.value = !noteOpen.value; uiTouched = true; saveUi() }
function toggleLog() { logOpen.value = !logOpen.value; uiTouched = true; saveUi() }
function toggleRule() { ruleOpen.value = !ruleOpen.value; uiTouched = true; saveUi() }

// 运行参数：改一次就记住，刷新 / 切换菜单都不回默认
const FORM_DEFAULTS = { limit: 5, max_scan: 40, refresh_every: 10, max_minutes: 10, dry: true, hide_browser: true }
const FORM_KEY = 'xhs.runParams'

function loadForm() {
  try {
    const saved = JSON.parse(localStorage.getItem(FORM_KEY) || '{}')
    const out = { ...FORM_DEFAULTS }
    for (const k of Object.keys(FORM_DEFAULTS)) {
      // 只认类型一致的字段，防止旧版本残留或手改坏了表单
      if (typeof saved[k] === typeof FORM_DEFAULTS[k]) out[k] = saved[k]
    }
    return out
  } catch {
    return { ...FORM_DEFAULTS }
  }
}

const form = reactive(loadForm())

watch(form, (v) => {
  try {
    localStorage.setItem(FORM_KEY, JSON.stringify(v))
  } catch { /* 隐私模式下写不进去，忽略 */ }
}, { deep: true })

function resetForm() {
  Object.assign(form, FORM_DEFAULTS)
  ElMessage.success('已恢复默认参数')
}

const probe = reactive({ text: '', region: '' })
const run = ref({ running: false, tail: '', params: {} })

// 日志区常驻（高度固定），没内容时给一行占位，避免黑框空着像坏了
const logText = computed(() => {
  if (run.value.tail) return run.value.tail
  return run.value.running ? '启动中…' : '暂无输出'
})

// 日志自动跟到最新一行；但你要是往上翻着看，就别把你拽回去
const logBox = ref(null)
watch(logText, async () => {
  const el = logBox.value
  const stick = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 60
  await nextTick()
  if (stick && logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
}, { immediate: true })

const stats = ref({
  total: { scanned: 0, hit: 0, sent: 0, runs: 0, hit_rate: 0, send_rate: 0 },
  today: { scanned: 0, sent: 0 },
  score_dist: [], region_dist: [], tone_dist: [], skip_dist: [], trend: [],
  last_run: {}, recent: [],
})
const history = ref([])
const assess = ref(null)
const replyText = ref('')
const replyError = ref('')

const DAILY_LIMIT = 20

const statCards = computed(() => {
  const t = stats.value.total
  const d = stats.value.today
  return [
    { label: '累计扫描帖子', value: t.scanned, sub: `共 ${t.runs} 轮运行`, color: '#1f2733' },
    { label: '命中目标人群', value: t.hit, sub: `命中率 ${t.hit_rate}%`, color: '#e8912d' },
    { label: '成功发送评论', value: t.sent, sub: `发送率 ${t.send_rate}%`, color: '#2fb344' },
    { label: '今日已发', value: `${d.sent} / ${DAILY_LIMIT}`, sub: '达到上限自动收工', color: '#2f6bff' },
  ]
})

const cfgInfo = ref({})

// 得分规则文案跟着配置走，免得设置页改了权重、这边还印着旧数字
const weightText = computed(() => {
  const w = cfgInfo.value.weights || {}
  const parts = Object.entries(w)
    .filter(([, v]) => Number(v) > 0)
    .map(([k, v]) => `${k} ${v} 分`)
  const base = parts.length ? parts.join(' · ') : '未配置'
  const min = cfgInfo.value.min_score
  return min == null ? base : `${base}（阈值 ${min} 分）`
})

const maxScoreCount = computed(() => Math.max(1, ...stats.value.score_dist.map((d) => d.count)))

function barWidth(n, max) {
  return Math.round((n / max) * 100) + '%'
}

// 分数越高颜色越深，同一蓝色系 —— 之前的红/黄/蓝混排像彩虹条，和品牌蓝也冲突
function scoreColor(score) {
  if (score >= 7) return '#2453d8'
  if (score >= 5) return '#2f6bff'
  if (score >= 4) return '#6d97ff'
  return '#a9c1ff'
}

// 文字场景用这档：浅蓝当正文会看不清
function scoreTextColor(score) {
  return score >= 4 ? '#2f6bff' : '#8a94a6'
}

// 推荐卡的一行摘要：运营商 · 月租 · 流量（缺哪个就不显示哪个）
function recMeta(row) {
  const bits = []
  if (row.product_operator) bits.push(row.product_operator)
  if (row.product_fee) bits.push(row.product_fee + '元/月')
  if (row.product_data) bits.push(row.product_data + 'G')
  return bits.join(' · ') || '资费未标注'
}

const EVENT_LABELS = {
  start: '开始', done: '结束', scanned: '扫描', hit: '命中', sent: '已发送',
  not_target: '非目标', skip_blacklist: '黑名单', skip_no_content: '正文为空',
  skip_replied: '已回复过', skip_low_or_cached: '分数不足（旧）', skip_cached: '已回复过',
  open_failed: '打开失败',
  send_failed: '发送失败', send_unverified: '未复核到', interrupted: '中断', fatal: '异常',
  feed_refresh: '刷新首页', scroll_stall: '滑不动', stop_timeout: '超时收工',
  stop_no_more_content: '无更多内容', stop_daily_limit: '达每日上限', api_error: '接口异常',
}
function eventLabel(e) {
  return EVENT_LABELS[e] || e
}
function eventType(e) {
  if (e === 'sent' || e === 'hit') return 'success'
  if (e === 'send_failed' || e === 'fatal') return 'danger'
  if (e === 'skip_blacklist' || e === 'send_unverified') return 'warning'
  if (e === 'done' || e === 'start') return 'primary'
  return 'info'
}

// 轮询去抖：内容没变化就不重新赋值。
// 每 5 秒一次全量替换会让整块 DOM 重建，用户正盯着看的表格、分布条就会"抖"一下——
// 这正是「页面一直在跳」的主要来源之一。
let statsSig = ''
let historySig = ''

async function loadAll() {
  loading.value = true
  try {
    const [s, h, cfg] = await Promise.all([api.xhsStats(7), api.xhsHistory(100), api.xhsConfig()])
    cfgInfo.value = cfg || {}
    const nextStats = {
      total: { scanned: 0, hit: 0, sent: 0, runs: 0, hit_rate: 0, send_rate: 0, ...(s.total || {}) },
      today: { scanned: 0, sent: 0, ...(s.today || {}) },
      score_dist: s.score_dist || [], region_dist: s.region_dist || [],
      tone_dist: s.tone_dist || [], skip_dist: s.skip_dist || [],
      trend: s.trend || [], last_run: s.last_run || {}, recent: s.recent || [],
    }
    const nextHistory = h.items || []

    const ss = JSON.stringify(nextStats)
    if (ss !== statsSig) {
      statsSig = ss
      stats.value = nextStats
    }
    const hs = JSON.stringify(nextHistory)
    if (hs !== historySig) {
      historySig = hs
      history.value = nextHistory
    }
  } catch (e) {
    ElMessage.error('加载失败：' + e.message)
  } finally {
    loading.value = false
  }
}

let runSig = ''
async function pollRun() {
  try {
    const r = await api.xhsRunStatus()
    const sig = [r.running, r.pid, r.state, r.finished_at, r.tail].join('|')
    if (sig !== runSig) {
      runSig = sig
      run.value = r
    }
    if (!r.running && starting.value) {
      starting.value = false
      loadAll()
    }
    // 打开页面时正好有一轮在跑，且你没动过这个折叠开关 → 自动展开日志
    if (r.running && !uiTouched && !logOpen.value) logOpen.value = true
  } catch (e) { /* 忽略 */ }
}

async function startRun() {
  starting.value = true
  try {
    await api.xhsRun({
      limit: form.limit, max_scan: form.max_scan,
      refresh_every: form.refresh_every,
      max_minutes: form.max_minutes, dry: form.dry, hide: form.hide_browser,
    })
    ElMessage.success('已启动，浏览器窗口会自动弹出')
    run.value = { ...(run.value || {}), running: true }
    // 启动后自动把日志展开：这时候你最想看的就是它在干什么
    if (!logOpen.value) {
      logOpen.value = true
      saveUi()
    }
    setTimeout(pollRun, 1200)
  } catch (e) {
    starting.value = false
    ElMessage.error(e.message || '启动失败')
  }
}

async function doAssess() {
  if (!probe.text.trim()) return
  probing.value = true
  replyText.value = ''
  replyError.value = ''
  try {
    assess.value = await api.xhsAssess(probe.text, probe.region || undefined)
  } catch (e) {
    ElMessage.error('判分失败：' + e.message)
  } finally {
    probing.value = false
  }
}

async function doReply() {
  if (!probe.text.trim()) return
  replying.value = true
  replyError.value = ''
  replyText.value = ''
  try {
    if (!assess.value) assess.value = await api.xhsAssess(probe.text, probe.region || undefined)
    const r = await api.xhsReply({
      post_content: probe.text,
      region: probe.region || undefined,
      force: true,   // 试算不走去重缓存，保证每次都能看到新生成
    })
    replyText.value = r.reply || ''
    replyError.value = r.error || ''
    if (!r.reply && !r.error) replyError.value = '规则判定为非目标人群，未生成回复'
    // 生成后刷新一次记录表，刚推的那张卡（客户下单链接）立刻能看到
    if (r.reply) await loadAll()
  } catch (e) {
    replyError.value = e.message
  } finally {
    replying.value = false
  }
}

let timer = null
function startPolling() {
  stopPolling()
  timer = setInterval(() => {
    pollRun()
    if (run.value.running) loadAll()
  }, 5000)
}
function stopPolling() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(() => {
  pollRun()
  startPolling()
})
// 本页在 keep-alive 白名单里：切回来补一次数据并恢复轮询，切走就停掉，避免后台空转请求
onActivated(() => {
  loadAll()
  pollRun()
  startPolling()
})
onDeactivated(stopPolling)
onUnmounted(stopPolling)
</script>

<style scoped>
.xhs-page { display: flex; flex-direction: column; gap: 12px; }
.card { flex-shrink: 0; }
.card-title { font-weight: 600; color: var(--text-1); }
.header-hint { margin-left: 10px; color: var(--text-3); font-size: 12px; font-weight: normal; }
.ml6 { margin-left: 6px; }
.ml0 { margin-left: 0; }
.mt6 { margin-top: 6px; }
.mt10 { margin-top: 10px; }
.hint { margin-top: 8px; color: var(--text-3); font-size: 12px; line-height: 1.6; }
/* 得分规则一行：规则摘要 + 可展开的门槛说明 */
.rule-line { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.rule-text {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-3);
  /* 允许折行：规则项多的时候截断成一行很难看，反正卡片高度是固定的，换行不会推动别的东西 */
  word-break: break-word;
}
/* ---------- 运行控制 ---------- */
/* 三行结构，行与行之间互不影响：标题行不会被按钮挤散，参数行换行只发生在整组之间 */
.ctrl-head { display: flex; align-items: center; gap: 10px; min-height: 32px; }
.ctrl-title { flex: 0 0 auto; font-size: 15px; font-weight: 600; color: var(--text-1); }

.run-state {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 9px;
  border-radius: 11px;
  background: #f4f5f7;
  color: var(--text-3);
  font-size: 12px;
  white-space: nowrap;
}
.run-state .dot { width: 6px; height: 6px; border-radius: 50%; background: #b9c0cc; }
.run-state.live { background: #eaf7ee; color: #1f8f3c; }
.run-state.live .dot { background: #2fb344; box-shadow: 0 0 0 3px rgba(47, 179, 68, .15); }
.run-pid { font-family: ui-monospace, Menlo, Consolas, monospace; opacity: .7; }

.ctrl-actions { display: flex; align-items: center; gap: 8px; margin-left: auto; flex: 0 0 auto; }
/* 两种模式的文案长度不同（试跑一轮 / 启动一轮），定宽后按钮宽度不再随开关变化 */
.run-btn { min-width: 172px; }

.ctrl-params { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 18px; margin-top: 14px; }
.p-item { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.p-switch { gap: 0; }
.lbl { color: var(--text-3); font-size: 12px; }
.num { width: 78px; }
.reset-btn { color: var(--text-3); }

.ctrl-note { margin-top: 10px; }
.note-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  background: none;
  padding: 0;
  color: var(--brand);
  font-size: 12px;
  cursor: pointer;
}
.note-toggle:hover { text-decoration: underline; }
.note-body {
  margin-top: 8px;
  padding: 10px 12px;
  background: #fafbfc;
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.7;
}

.run-log { margin-top: 12px; }
.log-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.log-title { flex: 0 0 auto; font-size: 12px; font-weight: 600; color: var(--text-2); }
.log-sub {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.log-toggle { flex: 0 0 auto; border: 0; background: none; padding: 0 2px; color: var(--brand); font-size: 12px; cursor: pointer; }
/* 固定高度：日志出现/消失都不会推动下方卡片 */
.run-log pre {
  margin: 0;
  padding: 10px;
  height: 108px;
  overflow: auto;
  font-size: 12px;
  background: #1e1e1e;
  color: #d5d9e0;
  border-radius: 4px;
  line-height: 1.6;
}
.run-log pre.idle { color: #7b8290; }

.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.stat :deep(.el-card__body) { padding: 14px 16px; }
.stat-val { font-size: 26px; font-weight: 700; line-height: 1.2; }
.stat-label { margin-top: 4px; font-size: 13px; color: var(--text-2); }
.stat-sub { margin-top: 2px; font-size: 12px; color: var(--text-3); }
/* 两列卡片定高：分数档位、跳过原因条数都会随数据增减，高度一变，
   下面所有卡片就跟着上下挪一大截。固定后内容超了在卡片内部滚动。 */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.two-col > .card :deep(.el-card__body) { height: 226px; overflow-y: auto; }
.bars { display: flex; flex-direction: column; gap: 10px; }
.bar-row { display: flex; align-items: center; gap: 10px; }
.bar-key { width: 52px; color: var(--text-2); font-size: 13px; }
.bar-track { flex: 1; height: 16px; background: var(--line); border-radius: 8px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 8px; transition: width 0.3s; }
.bar-val { width: 48px; text-align: right; font-size: 12px; color: var(--text-3); }
.mini-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.sub-title { font-size: 12px; color: var(--text-3); margin-bottom: 6px; }
.mini-row { display: flex; justify-content: space-between; font-size: 13px; color: var(--text-2); padding: 3px 0; }
.mini-row b { color: var(--text-1); }
.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { margin: 0; }
/* 「强」角标：标出能单独成立的硬信号 */
.lv { margin-left: 4px; font-size: 10px; opacity: .75; }
.empty { color: var(--text-3); font-size: 12px; padding: 6px 0; }
.probe-actions { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.region-input { width: 220px; }
.assess-box { margin-top: 12px; padding: 12px; background: #fafafa; border-radius: 6px; border: 1px solid var(--line); }
.assess-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.score-big { font-size: 20px; font-weight: 700; }
.assess-region { font-size: 12px; color: var(--text-3); }
.assess-reason { margin-top: 6px; font-size: 13px; color: var(--text-2); }
.reply-box { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--line); }
.reply-text { font-size: 13px; color: var(--text-1); line-height: 1.8; white-space: pre-wrap; }
.reply-cell { font-size: 12px; color: var(--text-2); line-height: 1.6; }
.rec-name {
  font-size: 12px; color: var(--text-1); line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; word-break: break-all;
}
.rec-meta { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: var(--text-3); margin-top: 2px; }
.rec-link { font-size: 11.5px; }
.mono { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; color: var(--text-3); }

@media (max-width: 1200px) {
  /* 窄屏下参数改成等宽网格：比自由换行整齐，也不会出现第二行只剩一个开关的怪样子 */
  .ctrl-params { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 16px; }
}

@media (max-width: 1100px) {
  .stat-row { grid-template-columns: repeat(2, 1fr); }
  .two-col { grid-template-columns: 1fr; }
}
</style>
