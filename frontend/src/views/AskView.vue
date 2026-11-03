<template>
  <el-row :gutter="16" class="fill">
    <!-- 左侧：输入 -->
    <el-col :span="8" class="pane-col left-pane">
      <el-card class="compose" shadow="never">
        <div class="compose-head">
          <span class="pane-title">提问</span>
          <el-radio-group v-model="audience" size="small" class="audience-switch" @change="onAudienceChange">
            <el-radio-button label="agent">代理商视角</el-radio-button>
            <el-radio-button label="customer">对客话术</el-radio-button>
          </el-radio-group>
        </div>
        <!-- 提示放在输入框上方：只在底部出现的话，切换模式会把发送/清空按钮顶下去 -->
        <el-alert
          v-if="audience === 'customer'"
          type="warning"
          :closable="false"
          title="对客话术模式：答案会自动隐去佣金、返佣等内部信息"
          class="mode-tip"
        />
        <el-input
          v-model="question"
          type="textarea"
          :rows="4"
          resize="none"
          class="q-input"
          placeholder="直接粘客户聊天记录也行，例如：29元以内200G的卡有哪些？河南能办吗？"
          @keydown.ctrl.enter="send"
        />
        <div class="compose-actions">
          <el-button type="primary" :loading="loading" @click="send">发送 (Ctrl+Enter)</el-button>
          <el-button @click="question = ''">清空</el-button>
          <el-tooltip content="清掉上文记忆，从头开始" placement="top" :disabled="!turns.length">
            <el-button text class="new-chat" :disabled="!turns.length" @click="newChat">
              新对话<template v-if="turns.length">（{{ turns.length }}）</template>
            </el-button>
          </el-tooltip>
        </div>
        <div class="mem-hint">
          <template v-if="turns.length">
            已带上前 {{ Math.min(turns.length, SENT_TURNS) }} 轮上文，可直接追问
          </template>
          <template v-else>客户聊天记录可以整段粘进来，问完也能接着追问</template>
        </div>
      </el-card>
    </el-col>

    <!-- 右侧：对话 -->
    <el-col :span="16" class="pane-col right-pane">
      <el-card class="answer" shadow="never">
        <div class="pane-title answer-title">
          <span>
            回答
            <span v-if="turns.length" class="turn-count">本次对话 {{ turns.length }} 轮</span>
          </span>
          <el-button
            v-if="lastAnswer && !loading"
            size="small" text :icon="CopyDocument" @click="copyAnswer"
          >复制</el-button>
        </div>

        <div v-if="turns.length" ref="threadEl" class="thread" @scroll="onThreadScroll">
          <div v-for="(t, ti) in turns" :key="ti" class="turn">
            <div class="qa-q">
              <el-tag size="small" type="primary">问</el-tag>
              <span class="q-text">{{ t.q }}</span>
            </div>

            <div v-if="t.loading" class="typing-hint">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>检索资料中…</span>
            </div>
            <el-alert
              v-else-if="t.error"
              type="error"
              :closable="false"
              :title="t.error"
              class="block-gap"
            />
            <template v-else>
              <div v-if="t.typing" class="typing-hint">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>AI 正在回答…</span>
              </div>
              <div class="qa-a" v-if="t.answer">
                <el-tag size="small" type="success">答</el-tag>
                <pre class="answer-text" v-html="linkify(t.answer)"></pre>
              </div>
              <el-alert
                v-else-if="!t.typing"
                type="info"
                :closable="false"
                title="模型未返回内容"
                description="可能网络中断或模型服务异常，请重试。"
                class="block-gap"
              />
            </template>

            <div v-if="t.sources && t.sources.length" class="sources">
              <!-- 旧轮次默认收起：不收起的话，几轮下来全是来源列表，正文都得翻半天 -->
              <div class="sources-title src-toggle" @click="t.open = !t.open">
                <span class="caret">{{ t.open ? '▾' : '▸' }}</span>
                参考来源（{{ t.sources.length }}）
              </div>
              <div v-show="t.open">
                <div v-for="(s, i) in t.sources" :key="i" class="source-item">
                  <el-tag size="small" :type="s.type === 'product' ? 'primary' : 'info'">
                    {{ s.ref }}
                  </el-tag>
                  <span class="src-title">{{ s.title }}</span>
                  <span v-if="s.heading" class="src-heading">{{ s.heading }}</span>
                  <a v-if="s.detail_url" :href="s.detail_url" target="_blank" rel="noopener" class="src-link">详情页 ↗</a>
                </div>
              </div>
            </div>
          </div>
        </div>
        <el-empty v-else description="在左侧输入问题，开始提问" />
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument, Loading } from '@element-plus/icons-vue'
import { api } from '../api'

defineOptions({ name: 'AskView' })

// 前端保留整段对话用于展示，发给后端时只带最近 10 轮（后端同样按 10 轮截断）。
// 实际用法一次也就十几二十条客户消息，10 轮足够，不需要更复杂的压缩策略。
const SENT_TURNS = 10

const question = ref('')
const audience = ref('agent')
const loading = ref(false)
const turns = ref([])
const threadEl = ref(null)
const stick = ref(true)

const lastAnswer = computed(() => {
  for (let i = turns.value.length - 1; i >= 0; i--) {
    if (turns.value[i].answer) return turns.value[i].answer
  }
  return ''
})

// 只有成功回答过的轮次才进记忆，报错的那轮带进去只会污染上文
function historyPayload() {
  return turns.value
    .filter((t) => t.answer && !t.error)
    .slice(-SENT_TURNS)
    .map((t) => ({ q: t.q, a: t.answer }))
}

// 把回答里的 URL 变成可点击链接（先转义 HTML，再包 <a>，避免 XSS）
function linkify(text) {
  if (!text) return ''
  const esc = String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return esc.replace(/(https?:\/\/[^\s<>"'，。；、）】]+)/g,
    '<a href="$1" target="_blank" rel="noopener" class="inline-link">$1</a>')
}

function nowStr() {
  const d = new Date()
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}

function scrollToBottom() {
  const el = threadEl.value
  if (!el) return
  // 一定要在 DOM 更新之后量 scrollHeight，否则拿到的是上一帧的高度
  nextTick(() => { el.scrollTop = el.scrollHeight })
}

// 「是否贴着底部」用事件维护，不要每次流式增量现算：
// 新问题的参考来源是一次性渲染出来的，高度会突然跳一大截，
// 那一瞬间现算会判成「用户看的是上面」，之后就再也不跟随了。
function onThreadScroll() {
  const el = threadEl.value
  if (!el) return
  stick.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

async function send() {
  const q = question.value.trim()
  if (!q) {
    ElMessage.warning('请输入问题')
    return
  }
  if (loading.value) return
  const a = audience.value
  const history = historyPayload()

  loading.value = true
  question.value = ''
  // 新问题进来就把上一轮的来源收起，保持视线落在最新一轮
  turns.value.forEach((x) => { x.open = false })
  turns.value.push({
    q, audience: a, answer: '', sources: [], error: '',
    loading: true, typing: false, time: nowStr(), open: true,
  })
  // 取回响应式代理再改字段，否则改原始对象不会触发渲染
  const t = turns.value[turns.value.length - 1]
  stick.value = true
  scrollToBottom()

  try {
    await api.askStream(q, a, (ev) => {
      if (ev.type === 'sources') {
        t.loading = false
        t.typing = true
        t.sources = ev.sources || []
        if (stick.value) scrollToBottom()
      } else if (ev.type === 'delta') {
        t.loading = false
        t.typing = false
        t.answer = (t.answer || '') + ev.content
        if (stick.value) scrollToBottom()
      } else if (ev.type === 'error') {
        t.loading = false
        t.typing = false
        t.error = ev.error || '出错了'
        ElMessage.error(ev.error || '出错了')
      }
    }, history)
  } catch (e) {
    t.loading = false
    t.typing = false
    t.error = e.message
    ElMessage.error('请求失败：' + e.message)
  } finally {
    loading.value = false
    t.loading = false
    t.typing = false
    if (stick.value) scrollToBottom()
  }
}

function newChat() {
  if (loading.value) {
    ElMessage.warning('正在回答，稍等一下')
    return
  }
  turns.value = []
  ElMessage.success('已开始新对话')
}

// 换口径就清空上文：代理商视角的回答里有佣金、结算，
// 带进对客话术模式会被模型顺口说出来。
function onAudienceChange(v) {
  if (!turns.value.length) return
  turns.value = []
  ElMessage.info(v === 'customer' ? '已切到对客话术，上文已清空' : '已切到代理商视角，上文已清空')
}

async function copyAnswer() {
  const text = lastAnswer.value
  if (!text) return
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    ElMessage.success('已复制最新一条回答')
  } catch (e) {
    ElMessage.error('复制失败：' + e.message)
  }
}
</script>

<style scoped>
/* 左右两栏等高：卡片撑满视口，输入框吃掉剩余高度，按钮贴底 ——
   否则左栏只有一行内容高，和右边的大卡片上下沿都错开。 */
.pane-col { height: 100%; }
.left-pane,
.right-pane { height: 100%; }

.compose {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.compose :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.pane-title { font-weight: 600; margin-bottom: 10px; }

/* 标题与模式切换同一行：左标题、右分段按钮 */
.compose-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex: 0 0 auto;
}
.compose-head .pane-title { margin-bottom: 0; }
.audience-switch { flex: 0 0 auto; }
/* 提示紧贴输入框上方，切换模式只挤压输入框高度，按钮位置不动 */
.mode-tip { margin-bottom: 10px; flex: 0 0 auto; }

/* 输入框随卡片增高，和右侧对话区同高 */
.q-input {
  flex: 1;
  min-height: 110px;
  display: block;
}
.q-input :deep(.el-textarea__inner) {
  height: 100%;
  resize: none;
  line-height: 1.7;
  font-size: 14px;
  padding: 10px 12px;
}

.compose-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  flex: 0 0 auto;
}
.new-chat { margin-left: auto; padding: 0 4px; color: var(--text-2); font-size: 13px; }

.mem-hint {
  margin-top: 8px;
  flex: 0 0 auto;
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.5;
}

.answer-title { display: flex; align-items: center; justify-content: space-between; }
.turn-count {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--text-3);
}

/* 卡片本体不滚动，交给 .thread 滚，标题始终留在顶部 */
.answer { height: 100%; }
.answer :deep(.el-card__body) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.thread { flex: 1; min-height: 0; overflow: auto; padding-right: 4px; }
.thread::-webkit-scrollbar { width: 8px; }
.thread::-webkit-scrollbar-thumb { background: var(--line); border-radius: 4px; }

.turn + .turn {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.answer :deep(.el-empty) {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0;
}

.qa-q { display: flex; gap: 8px; align-items: flex-start; font-weight: 500; margin-bottom: 8px; }
.q-text { flex: 1; word-break: break-word; }
.qa-a { display: flex; gap: 8px; align-items: flex-start; }
.block-gap { margin: 10px 0; }
.answer-text { flex: 1; white-space: pre-wrap; word-break: break-word; line-height: 1.7; font-family: inherit; margin: 0; }
.answer-text :deep(.inline-link) { color: var(--brand); text-decoration: underline; word-break: break-all; cursor: pointer; }
.sources { margin-top: 14px; border-top: 1px dashed var(--line); padding-top: 10px; }
.sources-title { font-weight: 600; margin-bottom: 8px; }
.src-toggle { cursor: pointer; user-select: none; display: flex; align-items: center; gap: 4px; color: var(--text-2); }
.src-toggle:hover { color: var(--brand); }
.caret { font-size: 10px; width: 10px; }
.source-item { display: flex; gap: 8px; align-items: center; padding: 4px 0; }
.src-link { margin-left: auto; font-size: 12px; color: var(--brand); text-decoration: none; white-space: nowrap; }
.src-link:hover { text-decoration: underline; }
.src-heading { color: var(--text-3); font-size: 12px; }
.typing-hint { display: flex; align-items: center; gap: 8px; color: var(--text-3); font-size: 14px; margin: 10px 0; }
.typing-hint .el-icon { font-size: 16px; }
</style>
