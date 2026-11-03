<template>
  <!-- 全局搜索：958 个商品原来只能进页面再筛，跨模块找东西全靠翻侧栏。
       这里一次检索 商品 / 知识库 / 页面，Ctrl+K 随时唤起。 -->
  <el-dialog
    v-model="visible"
    width="640px"
    top="12vh"
    :show-close="false"
    class="cmd-dialog"
    append-to-body
    @opened="onOpened"
    @closed="onClosed"
  >
    <div class="cmd">
      <div class="cmd-input">
        <el-icon class="cmd-ico"><Search /></el-icon>
        <input
          ref="inputRef"
          v-model="q"
          placeholder="搜索商品名 / 地区 / 知识库，回车打开"
          @input="onInput"
          @keydown.down.prevent="move(1)"
          @keydown.up.prevent="move(-1)"
          @keydown.enter.prevent="openActive"
          @keydown.esc.prevent="visible = false"
        />
        <span v-if="loading" class="cmd-status">检索中…</span>
        <kbd v-else class="cmd-kbd">ESC</kbd>
      </div>

      <div class="cmd-body">
        <!-- 无关键词：直接给页面跳转，键盘党不用摸鼠标 -->
        <template v-if="!q.trim()">
          <div class="cmd-group">跳转到</div>
          <button
            v-for="(p, i) in pages"
            :key="p.path"
            class="cmd-item"
            :class="{ active: i === active }"
            @mouseenter="active = i"
            @click="goPage(p)"
          >
            <el-icon class="item-ico"><component :is="p.icon" /></el-icon>
            <span class="item-main">{{ p.title }}</span>
            <span class="item-sub">{{ p.desc }}</span>
          </button>
        </template>

        <template v-else>
          <div v-if="!loading && isEmpty" class="cmd-empty">
            没有匹配「{{ q }}」的商品或文档
          </div>

          <template v-if="results.products.length">
            <div class="cmd-group">商品 <span class="grp-count">{{ results.total }} 条命中</span></div>
            <button
              v-for="p in results.products"
              :key="'p' + p.product_id"
              class="cmd-item"
              :class="{ active: isActive('p', p.product_id) }"
              @mouseenter="activeId = 'p' + p.product_id"
              @click="goProduct(p)"
            >
              <el-tag size="small" :type="p.on_sale ? 'info' : 'info'" effect="plain" class="item-tag">
                {{ p.category === '宽带' ? '宽' : '卡' }}
              </el-tag>
              <span class="item-main" v-html="highlight(p.product_name)"></span>
              <span class="item-sub">{{ [p.operator, p.area, p.on_sale ? '' : '已下架'].filter(Boolean).join(' · ') }}</span>
            </button>
          </template>

          <template v-if="results.kb.length">
            <div class="cmd-group">知识库</div>
            <button
              v-for="k in results.kb"
              :key="'k' + (k.doc_id || k.chunk_id)"
              class="cmd-item"
              :class="{ active: isActive('k', k.doc_id || k.chunk_id) }"
              @mouseenter="activeId = 'k' + (k.doc_id || k.chunk_id)"
              @click="goKb(k)"
            >
              <el-icon class="item-ico"><Document /></el-icon>
              <span class="item-main" v-html="highlight(k.title || '')"></span>
              <span class="item-sub">{{ k.kind === 'chunk' ? (k.snippet || '片段') : '文档' }}</span>
            </button>
          </template>
        </template>
      </div>

      <div class="cmd-foot">
        <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
        <span><kbd>Enter</kbd> 打开</span>
        <span><kbd>Esc</kbd> 关闭</span>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Document, ChatDotRound, Goods, Connection, Promotion, Notebook, Clock, Setting } from '@element-plus/icons-vue'
import { api } from '../api'

const props = defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const router = useRouter()
const inputRef = ref(null)
const q = ref('')
const loading = ref(false)
const results = ref({ products: [], kb: [], total: 0 })
const active = ref(0)
const activeId = ref('')

const pages = [
  { path: '/ask', title: '智能问答', desc: '问套餐、查规则', icon: ChatDotRound },
  { path: '/products', title: '商品库', desc: '手机卡全量筛选', icon: Goods },
  { path: '/kuanpro', title: '宽带选品', desc: '选品广场 / 上下架', icon: Connection },
  { path: '/xhs', title: '小红书', desc: '自动回帖运行控制', icon: Promotion },
  { path: '/kb', title: '知识库', desc: '文档与片段', icon: Notebook },
  { path: '/changes', title: '更新日志', desc: '字段级变更', icon: Clock },
  { path: '/settings', title: '设置', desc: '模型 / 账号 / 同步', icon: Setting },
]

const isEmpty = computed(() =>
  !results.value.products.length && !results.value.kb.length)

function isActive(kind, id) {
  return activeId.value === kind + id
}

// 命中词高亮：直接拼 HTML 有注入风险，先把文本转义再包 <mark>
function highlight(text) {
  const s = escapeHtml(text || '')
  const kw = q.value.trim()
  if (!kw) return s
  const re = new RegExp(escapeHtml(kw).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')
  return s.replace(re, (m) => `<mark>${m}</mark>`)
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ))
}

let timer = null
function onInput() {
  activeId.value = ''
  active.value = 0
  clearTimeout(timer)
  const kw = q.value.trim()
  if (!kw) { results.value = { products: [], kb: [], total: 0 }; return }
  timer = setTimeout(() => run(kw), 260)
}

async function run(kw) {
  loading.value = true
  try {
    const d = await api.search(kw)
    if (q.value.trim() === kw) results.value = d
  } catch (e) {
    results.value = { products: [], kb: [], total: 0 }
  } finally {
    loading.value = false
  }
}

function flatItems() {
  if (!q.value.trim()) return pages.map((p) => ({ kind: 'page', data: p }))
  return [
    ...results.value.products.map((p) => ({ kind: 'product', data: p })),
    ...results.value.kb.map((k) => ({ kind: 'kb', data: k })),
  ]
}

function move(step) {
  const items = flatItems()
  if (!items.length) return
  active.value = (active.value + step + items.length) % items.length
  const it = items[active.value]
  activeId.value = it.kind === 'page' ? '' : it.kind[0] + (it.data.product_id || it.data.doc_id || it.data.chunk_id)
}

function openActive() {
  const items = flatItems()
  const it = items[active.value]
  if (!it) return
  if (it.kind === 'page') goPage(it.data)
  else if (it.kind === 'product') goProduct(it.data)
  else goKb(it.data)
}

function goPage(p) {
  visible.value = false
  router.push(p.path)
}

function goProduct(p) {
  visible.value = false
  // 带着关键词进商品库，落地就是筛好的结果，不用再手打一遍
  router.push({ path: '/products', query: { q: p.product_name } })
}

function goKb(k) {
  visible.value = false
  router.push({ path: '/kb', query: k.doc_id ? { doc: k.doc_id } : {} })
}

function onOpened() {
  active.value = 0
  setTimeout(() => inputRef.value && inputRef.value.focus(), 30)
}

function onClosed() {
  q.value = ''
  results.value = { products: [], kb: [], total: 0 }
  activeId.value = ''
}

watch(() => props.modelValue, (v) => {
  if (!v) { clearTimeout(timer) }
})
</script>

<style scoped>
.cmd { display: flex; flex-direction: column; }
.cmd-input {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 4px 12px;
  border-bottom: 1px solid var(--line);
}
.cmd-ico { font-size: 18px; color: var(--text-3); }
.cmd-input input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  font-size: 15px;
  color: var(--text-1);
  background: transparent;
  padding: 6px 0;
}
.cmd-input input::placeholder { color: var(--text-3); }
.cmd-status { font-size: 12px; color: var(--text-3); }
.cmd-kbd,
.cmd-foot kbd {
  font-family: inherit;
  font-size: 11px;
  color: var(--text-3);
  background: #f4f6fa;
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 1px 5px;
}

.cmd-body { max-height: 52vh; overflow: auto; padding: 8px 0; }
.cmd-group {
  padding: 8px 8px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .4px;
  color: var(--text-3);
}
.grp-count { font-weight: normal; margin-left: 4px; }

.cmd-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font-size: 13.5px;
  color: var(--text-1);
}
.cmd-item.active { background: var(--brand-soft); }
.item-ico { font-size: 15px; color: var(--text-3); flex: 0 0 auto; }
.item-tag { flex: 0 0 auto; }
.item-main {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-main :deep(mark) { background: #fff2c2; color: inherit; padding: 0 1px; border-radius: 2px; }
.item-sub {
  flex: 0 1 44%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-3);
  text-align: right;
}
.cmd-empty { padding: 28px 10px; text-align: center; font-size: 13px; color: var(--text-3); }

.cmd-foot {
  display: flex;
  gap: 16px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
  font-size: 11.5px;
  color: var(--text-3);
}
.cmd-foot kbd { margin-right: 3px; }
</style>

<style>
/* 搜索框是主角：去掉 dialog 默认内边距，只留一层干净白底 */
.cmd-dialog .el-dialog__header { display: none; }
.cmd-dialog .el-dialog__body { padding: 14px 16px 12px; }
.cmd-dialog .el-dialog { border-radius: 12px; box-shadow: 0 18px 48px rgba(24, 32, 48, .18); }
</style>
