<template>
  <el-row :gutter="16" class="fill">
    <!-- 左侧：输入 -->
    <el-col :span="8" class="left-pane">
      <el-card class="compose" shadow="never">
        <div class="pane-title">提问</div>
        <el-radio-group v-model="audience" size="small" style="margin-bottom: 10px">
          <el-radio-button label="agent">代理商视角</el-radio-button>
          <el-radio-button label="customer">对客话术</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="question"
          type="textarea"
          :rows="5"
          placeholder="例如：29元以内200G以上的广电卡有哪些？办卡年龄有限制吗？"
          @keydown.ctrl.enter="send"
        />
        <div class="compose-actions">
          <el-button type="primary" :loading="loading" @click="send">发送 (Ctrl+Enter)</el-button>
          <el-button @click="question = ''">清空</el-button>
        </div>
        <el-alert
          v-if="audience === 'customer'"
          type="warning"
          :closable="false"
          title="对客话术模式：答案会自动隐去佣金、返佣等内部信息"
          style="margin-top: 10px"
        />
      </el-card>
    </el-col>

    <!-- 右侧：答案 -->
    <el-col :span="16" class="right-pane">
      <el-card class="answer" shadow="never">
        <div class="pane-title answer-title">
          <span>回答</span>
          <el-button
            v-if="current && current.answer && !loading"
            size="small" text :icon="CopyDocument" @click="copyAnswer"
          >复制</el-button>
        </div>
        <div v-if="loading" v-loading="true" element-loading-text="检索资料中…" style="min-height: 200px" />
        <template v-else-if="current">
          <div class="qa-q">
            <el-tag size="small" type="primary">问</el-tag>
            <span>{{ current.q }}</span>
          </div>
          <el-alert
            v-if="current.error"
            type="error"
            :closable="false"
            :title="current.error"
            style="margin: 12px 0"
          />
          <div v-if="typing" class="typing-hint">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>AI 正在回答…</span>
          </div>
          <div class="qa-a" v-if="current.answer">
            <el-tag size="small" type="success">答</el-tag>
            <pre class="answer-text" v-html="linkify(current.answer)"></pre>
          </div>
          <el-alert
            v-else-if="!loading && !typing && !current.error"
            type="info"
            :closable="false"
            title="模型未返回内容"
            description="可能网络中断或模型服务异常，请重试。"
            style="margin: 12px 0"
          />
          <div v-if="current.sources && current.sources.length" class="sources">
            <div class="sources-title">参考来源</div>
            <div v-for="(s, i) in current.sources" :key="i" class="source-item">
              <el-tag size="small" :type="s.type === 'product' ? 'primary' : 'info'">
                {{ s.ref }}
              </el-tag>
              <span class="src-title">{{ s.title }}</span>
              <span v-if="s.heading" class="src-heading">{{ s.heading }}</span>
              <a v-if="s.detail_url" :href="s.detail_url" target="_blank" rel="noopener" class="src-link">详情页 ↗</a>
            </div>
          </div>
        </template>
        <el-empty v-else description="在左侧输入问题，开始提问" />
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument, Loading } from '@element-plus/icons-vue'
import { api } from '../api'

defineOptions({ name: 'AskView' })

const question = ref('')
const audience = ref('agent')
const loading = ref(false)
const typing = ref(false)
const current = ref(null)

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

async function send() {
  const q = question.value.trim()
  if (!q) {
    ElMessage.warning('请输入问题')
    return
  }
  if (loading.value) return
  loading.value = true
  typing.value = false
  const a = audience.value
  current.value = { q, audience: a, answer: '', sources: [], error: '', time: nowStr() }
  question.value = ''
  try {
    await api.askStream(q, a, (ev) => {
      if (ev.type === 'sources') {
        loading.value = false
        typing.value = true
        current.value.sources = ev.sources || []
      } else if (ev.type === 'delta') {
        loading.value = false
        typing.value = false
        current.value.answer = (current.value.answer || '') + ev.content
      } else if (ev.type === 'error') {
        loading.value = false
        typing.value = false
        current.value.error = ev.error || '出错了'
        ElMessage.error(ev.error || '出错了')
      }
    })
  } catch (e) {
    loading.value = false
    typing.value = false
    if (current.value) current.value.error = e.message
    ElMessage.error('请求失败：' + e.message)
  } finally {
    loading.value = false
    typing.value = false
  }
}

async function copyAnswer() {
  const text = (current.value && current.value.answer) || ''
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
    ElMessage.success('已复制')
  } catch (e) {
    ElMessage.error('复制失败：' + e.message)
  }
}
</script>

<style scoped>
.left-pane { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.pane-title { font-weight: 600; margin-bottom: 10px; }
.answer-title { display: flex; align-items: center; justify-content: space-between; }
.compose-actions { margin-top: 10px; display: flex; gap: 8px; }
.right-pane { height: 100%; }
.answer { height: 100%; overflow: auto; }
.qa-q { display: flex; gap: 8px; align-items: flex-start; font-weight: 500; margin-bottom: 8px; }
.answer-text { white-space: pre-wrap; word-break: break-word; line-height: 1.7; font-family: inherit; margin: 0; }
.answer-text :deep(.inline-link) { color: #409eff; text-decoration: underline; word-break: break-all; cursor: pointer; }
.sources { margin-top: 16px; border-top: 1px dashed #ebeef5; padding-top: 10px; }
.sources-title { font-weight: 600; margin-bottom: 8px; }
.source-item { display: flex; gap: 8px; align-items: center; padding: 4px 0; }
.src-link { margin-left: auto; font-size: 12px; color: #409eff; text-decoration: none; white-space: nowrap; }
.src-link:hover { text-decoration: underline; }
.src-heading { color: #909399; font-size: 12px; }
.typing-hint { display: flex; align-items: center; gap: 8px; color: #909399; font-size: 14px; margin: 12px 0; }
.typing-hint .el-icon { font-size: 16px; }
</style>
