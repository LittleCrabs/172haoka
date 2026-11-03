<template>
  <el-row :gutter="12" class="fill">
    <!-- 左侧：文档列表（master） -->
    <el-col :span="6" class="left-pane">
      <el-card shadow="never" class="doc-card">
        <div class="pane-title">
          知识文档 <span class="muted">{{ docs.length }}</span>
        </div>
        <el-input v-model="filterText" placeholder="过滤文档名" clearable size="small" style="margin-bottom: 8px" />
        <div class="doc-list">
          <div
            v-for="d in filteredDocs"
            :key="d.doc_id"
            class="doc-item"
            :class="{ active: selectedDocId === d.doc_id }"
            @click="selectDoc(d.doc_id)"
          >
            <span class="doc-title" :title="d.title">{{ d.title }}</span>
            <el-tag size="small" effect="plain" :type="audienceTag(d.audience)" class="doc-cat">
              {{ audienceText(d.audience) }}
            </el-tag>
          </div>
          <EmptyState v-if="!filteredDocs.length" compact type="doc"
            :title="filterText ? '没有匹配的文档' : '还没有文档'"
            :desc="filterText ? '换个关键词再试' : '在设置页导入外挂文档后会自动分块'" />
        </div>
      </el-card>
    </el-col>

    <!-- 右侧：全文 / 分块 -->
    <el-col :span="18" class="right-pane">
      <el-card shadow="never" class="content-card">
        <!-- 编辑时搜索框和「全文/分块」都用不上，留着只会把按钮挤到第二排 -->
        <div class="toolbar" v-if="!editing">
          <el-input
            v-model="searchQ"
            placeholder="搜索全库内容（支持中文关键词）"
            clearable
            style="width: 280px"
            @input="onSearch"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>

          <template v-if="!searchQ">
            <el-radio-group v-model="viewMode" size="small">
              <el-radio-button value="full">全文</el-radio-button>
              <el-radio-button value="chunk">分块（{{ docChunks.length }}）</el-radio-button>
            </el-radio-group>
          </template>
          <span v-else class="muted">共 {{ searchResults.length }} 条匹配</span>

          <div class="spacer" />

          <el-button type="primary" plain :icon="EditPen" :disabled="!selectedDoc" @click="startEdit">
            修改正文
          </el-button>
          <!-- 维护动作低频且带破坏性，收进下拉，别和「修改正文」抢位置 -->
          <el-dropdown trigger="click" @command="onMaintain">
            <el-button :icon="Tools">维护<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="clean" :disabled="cleaning" :icon="Brush">
                  整理分块正文<span class="dd-hint">清洗已入库的脏字符</span>
                </el-dropdown-item>
                <el-dropdown-item command="rebuild_one" :disabled="!selectedDoc || rebuildingOne" :icon="Files">
                  重建本篇<span class="dd-hint">只重切当前文档</span>
                </el-dropdown-item>
                <el-dropdown-item command="rebuild" :disabled="rebuilding" :icon="Refresh">
                  重建全部分块<span class="dd-hint">全部重切 + 重算向量</span>
                </el-dropdown-item>
                <el-dropdown-item command="embed" :disabled="embedding" :icon="Coin">
                  补算向量<span class="dd-hint">只算缺的，已有跳过</span>
                </el-dropdown-item>
                <el-dropdown-item command="ingest" :disabled="ingesting" :icon="Upload" divided>
                  导入外挂文档<span class="dd-hint">读取 kb_extra 目录</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <!-- 编辑态：只留保存/取消，避免误点其他按钮把改动冲掉 -->
        <div class="toolbar" v-else>
          <el-tag type="warning" effect="light" size="small">编辑中</el-tag>
          <span class="muted">{{ editChars }} 字</span>
          <div class="spacer" />
          <el-button :icon="MagicStick" :loading="tidying" @click="tidy">整理格式</el-button>
          <el-button @click="cancelEdit">取消</el-button>
          <el-button type="primary" :icon="Check" :loading="saving" @click="save">保存并重建</el-button>
        </div>

        <!-- 文档身份条：改的时候随时能看到自己在改哪一篇 -->
        <div class="doc-head" v-if="selectedDoc && !searchQ">
          <b class="doc-head-title">{{ doc?.title || selectedDoc.title }}</b>
          <el-tag size="small" :type="audienceTag(doc?.audience || selectedDoc.audience)" effect="light">
            {{ audienceText(doc?.audience || selectedDoc.audience) }}
          </el-tag>
          <span class="muted">{{ docIdShort }}</span>
          <span class="muted" v-if="doc">{{ doc.chars }} 字 · {{ doc.chunk_count }} 段 · 更新 {{ doc.fetched_at }}</span>
          <el-tooltip v-if="isMdDoc && doc?.source_file" placement="bottom" raw-content
            :content="`这篇来自 <code>${doc.source_file}</code>，<b>保存会同时写回该文件</b>；文件被外部改动过时，导入以外挂为准。`">
            <el-tag size="small" type="success" effect="plain">源文件同步</el-tag>
          </el-tooltip>
          <el-tooltip v-else-if="isMdDoc" placement="bottom" raw-content
            content="找不到对应的 kb_extra 源文件：保存只改库，<b>下次「导入外挂」会把它覆盖</b>。">
            <el-tag size="small" type="warning" effect="plain">源文件缺失</el-tag>
          </el-tooltip>
        </div>

        <!-- 编辑器 -->
        <div class="editor-wrap" v-if="editing">
          <el-input
            v-model="editContent"
            type="textarea"
            class="doc-editor"
            resize="none"
            placeholder="正文内容，支持 Markdown 标题（# 开头的行会被当作段落标题）"
            @keydown.ctrl.s.prevent="save"
            @keydown.meta.s.prevent="save"
          />
          <div class="editor-foot muted">
            保存后只重切这一篇（{{ doc?.chunk_count ?? '—' }} 段）并补算向量，其他文档不受影响。
            <template v-if="isMdDoc && doc?.source_file">
              外挂文档，<b :title="doc.source_file">会同时写回 {{ sourceFileName }}</b>。
            </template>
            <template v-else-if="isMdDoc">找不到源文件，只改库（导入外挂会覆盖）。</template>
            Ctrl + S 保存。
          </div>
        </div>

        <!-- 阅读态 -->
        <div class="chunk-list" v-else v-loading="loading">
          <EmptyState v-if="!displayChunks.length" compact type="search"
            :title="searchQ ? '没有匹配的内容' : '请选择左侧文档'"
            :desc="searchQ ? '换一个关键词，或清空搜索看全文' : '点击左边任意文档，这里会显示正文'" />

          <!-- 全文：一篇一篇看，不再被切开的段落打断。
               按行渲染是为了把 markdown 的 # 标题变成真标题——原来整篇塞进 <pre>，
               正文里 `### 办卡与资料` 连井号一起显示，看着像排版坏了。 -->
          <div v-if="!searchQ && viewMode === 'full' && doc" class="doc-full">
            <template v-for="(line, i) in fullLines" :key="i">
              <div v-if="headingLevel(line)" class="md-h" :class="'md-h' + headingLevel(line)">
                {{ headingText(line) }}
              </div>
              <div v-else class="md-line">{{ line }}</div>
            </template>
          </div>

          <!-- 分块：看检索时实际用的是哪几段 -->
          <template v-if="(searchQ || viewMode === 'chunk')">
            <div v-for="(c, i) in displayChunks" :key="c.chunk_id || i" class="chunk">
              <div class="chunk-head">
                <el-tag size="small" type="info">{{ searchQ ? c.title : '第 ' + (i + 1) + ' 段' }}</el-tag>
                <span v-if="c.heading" class="chunk-heading">
                  <template v-for="(part, pi) in splitHeading(c.heading)" :key="pi">
                    <span v-if="pi" class="h-sep">/</span>
                    <span :class="pi === splitHeading(c.heading).length - 1 ? 'h-last' : 'h-up'">{{ part }}</span>
                  </template>
                </span>
                <span v-if="c.score != null" class="chunk-score">匹配度 {{ c.score }}</span>
                <span v-else class="muted chunk-len">{{ (c.text || '').length }} 字</span>
              </div>
              <pre class="chunk-text">{{ chunkText(c.text, c.heading) }}</pre>
            </div>
          </template>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { ref, computed, onMounted, onActivated } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Upload, Brush, EditPen, Check, MagicStick, Tools, ArrowDown, Coin, Files } from '@element-plus/icons-vue'
import EmptyState from '../components/EmptyState.vue'
import { api } from '../api'

const docs = ref([])
const allChunks = ref([])
const selectedDocId = ref('')
const filterText = ref('')
const searchQ = ref('')
const searchResults = ref([])
const loading = ref(false)
const rebuilding = ref(false)
const ingesting = ref(false)
const cleaning = ref(false)

// 单篇文档 + 编辑态
const doc = ref(null)
const viewMode = ref('full')
const editing = ref(false)
const editContent = ref('')
const saving = ref(false)
const tidying = ref(false)
const embedding = ref(false)
const rebuildingOne = ref(false)

// 兜底清洗：后端已经刷过一遍历史数据，但「导入外挂」随时会带进新的脏字符
// （H5 详情页的 \x03、导出工具的零宽字符），渲染前再过一道，页面上永远不会出现方块。
// heading 单独传进来是为了剥掉正文开头重复的标题：入库时正文前面拼了标题
// （让向量和关键词检索能匹配到章节），卡片上方已经显示过一遍了。
function chunkText(s, heading) {
  if (!s) return ''
  let t = String(s)
  if (heading && t.startsWith(heading)) {
    t = t.slice(heading.length).replace(/^[\s\n]+/, '')
  }
  return t
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '')
    .replace(/[\u200b-\u200f\ufeff]/g, '')
    .replace(/\n{3,}/g, '\n\n')
}

const AUD = { agent: '代理', customer: '客户', shared: '共用' }
const audienceText = (a) => AUD[a] || a || '代理'
const audienceTag = (a) => ({ agent: 'info', customer: 'success', shared: 'warning' })[a] || 'info'

const selectedDoc = computed(() => docs.value.find((d) => d.doc_id === selectedDocId.value) || null)
const filteredDocs = computed(() => {
  const t = filterText.value.trim()
  if (!t) return docs.value
  return docs.value.filter((d) => (d.title || '').includes(t))
})
const docChunks = computed(() =>
  allChunks.value.filter((c) => c.doc_id === selectedDocId.value))
const displayChunks = computed(() => {
  if (searchQ.value.trim()) return searchResults.value
  return docChunks.value
})
const editChars = computed(() => (editContent.value || '').length)
const docIdShort = computed(() => selectedDocId.value)
const isMdDoc = computed(() => selectedDocId.value.startsWith('md-'))
// 完整路径几十个字符，塞进脚注会把整行撑成两排，只留文件名，全路径走 title
const sourceFileName = computed(() => {
  const p = doc.value?.source_file || ''
  return p.split('/').pop() || p
})

// 空格可有可无：后端 _split_md 认的是 startswith("#")，手写正文常写成
// 「#第一节」「##第一种方法」，这里再要求 `# ` 就会出现「切分认了、显示不认」。
const MD_HEAD = /^(#{1,6})\s*(\S.*)$/
const fullLines = computed(() => (doc.value?.content || '').split('\n'))
function headingLevel(line) {
  const m = MD_HEAD.exec((line || '').trim())
  return m ? m[1].length : 0
}
function headingText(line) {
  const m = MD_HEAD.exec((line || '').trim())
  return m ? m[2] : line
}
// heading 现在是完整路径「一级 / 二级」：父级压灰、末级标蓝，一眼看出这篇属于哪一节
function splitHeading(h) {
  return String(h || '').split(' / ').filter(Boolean)
}

async function selectDoc(id) {
  if (id === selectedDocId.value) return
  // 有未保存改动时先问一句，别让人一句话白写
  if (editing.value && editContent.value !== (doc.value?.content || '')) {
    try {
      await ElMessageBox.confirm('当前文档有未保存的修改，切换会丢掉。要继续吗？', '放弃修改',
        { type: 'warning', confirmButtonText: '放弃并切换', cancelButtonText: '继续编辑' })
    } catch {
      return
    }
  }
  editing.value = false
  selectedDocId.value = id
  searchQ.value = ''
  searchResults.value = []
  viewMode.value = 'full'
  await loadDoc(id)
}

async function loadDoc(id) {
  if (!id) { doc.value = null; return }
  try {
    doc.value = await api.kbDoc(id)
  } catch (e) {
    doc.value = null
    ElMessage.error('文档读取失败：' + e.message)
  }
}

function startEdit() {
  if (!doc.value) return
  editContent.value = doc.value.content || ''
  editing.value = true
  viewMode.value = 'full'
}

async function cancelEdit() {
  if (editContent.value !== (doc.value?.content || '')) {
    try {
      await ElMessageBox.confirm('放弃这次修改？', '取消编辑',
        { type: 'warning', confirmButtonText: '放弃', cancelButtonText: '继续编辑' })
    } catch {
      return
    }
  }
  editing.value = false
  editContent.value = ''
}

// 先把正文交给后端同一套 clean_text 洗一遍，结果回填到编辑框里让人过目，
// 不自作主张直接落库——清洗会合并 OCR 碎片行，偶尔不是你想要的。
async function tidy() {
  if (!editContent.value.trim()) return
  tidying.value = true
  try {
    const res = await api.kbCleanText(editContent.value)
    if (!res.changed) {
      ElMessage.success('这段正文已经是干净的')
      return
    }
    editContent.value = res.text
    ElMessage.success(`已整理格式（${res.before} → ${res.after} 字），确认无误后保存`)
  } catch (e) {
    ElMessage.error('整理失败：' + e.message)
  } finally {
    tidying.value = false
  }
}

async function save() {
  if (saving.value) return
  const content = editContent.value
  if (!content.trim()) {
    ElMessage.warning('正文不能为空')
    return
  }
  saving.value = true
  try {
    const res = await api.kbDocSave(selectedDocId.value, { content })
    editing.value = false
    const f = res.file || {}
    let msg = `已保存，重新切分为 ${res.chunks} 段`
    if (res.dropped) msg += `（屏蔽 ${res.dropped} 句内部话术）`
    if (f.written) msg += '，已同步写回源文件'
    else if (f.reason) msg += `；源文件未更新（${f.reason}）`
    ElMessage.success(msg)
    await refresh()
  } catch (e) {
    ElMessage.error('保存失败：' + e.message)
  } finally {
    saving.value = false
  }
}

let searchTimer = null
function onSearch() {
  const q = searchQ.value.trim()
  if (!q) {
    searchResults.value = []
    return
  }
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    loading.value = true
    try {
      searchResults.value = (await api.kbChunks(q, 80)) || []
    } catch (e) {
      ElMessage.error('搜索失败：' + e.message)
    } finally {
      loading.value = false
    }
  }, 250)
}

function onMaintain(cmd) {
  if (cmd === 'clean') cleanText()
  else if (cmd === 'rebuild_one') rebuildOne()
  else if (cmd === 'rebuild') rebuild()
  else if (cmd === 'embed') embedAll()
  else if (cmd === 'ingest') ingest()
}

// 只重切当前这篇：内容不动，纯粹让新的分块/清洗规则对它生效。
// 不动正文，所以不用怕改坏东西；向量也只补这一篇缺的。
async function rebuildOne() {
  if (!selectedDocId.value) return
  rebuildingOne.value = true
  try {
    const res = await api.kbDocRebuild(selectedDocId.value)
    const e = res.embed || {}
    ElMessage.success(
      `《${doc.value?.title || selectedDocId.value}》重切完成：${res.before} → ${res.chunks} 段` +
      (e.error ? `；向量补齐失败：${e.error}` : `，向量补算 ${e.new ?? 0} 条`))
    await refresh()
  } catch (e) {
    ElMessage.error('重建本篇失败：' + e.message)
  } finally {
    rebuildingOne.value = false
  }
}

// 向量是语义检索的前提。分块重切之后 embedding 必须重算，否则「搜得到、答不上」
// 而且界面上看不出任何异常——所以单独给一个能点、能看结果的动作。
async function embedAll() {
  embedding.value = true
  try {
    const res = await api.kbEmbed()
    if (res.error) {
      ElMessage.error('补算向量失败：' + res.error)
      return
    }
    if (res.skipped) {
      ElMessage.warning('还没配向量模型，先到「设置 → 模型服务」填上 base_url / model / api_key')
      return
    }
    ElMessage.success(`向量已就绪：本次补算 ${res.new ?? 0} 条，表里已有 ${res.done ?? 0} 条`)
  } catch (e) {
    ElMessage.error('补算向量失败：' + e.message)
  } finally {
    embedding.value = false
  }
}

async function rebuild() {
  try {
    await ElMessageBox.confirm(
      '会重新切分全部分块，并重算全部向量（1292 条，可能要几分钟）。只改某一篇正文不需要走这里，用「修改正文」保存即可。',
      '重建分块', { type: 'warning', confirmButtonText: '开始重建', cancelButtonText: '取消' })
  } catch { return }
  rebuilding.value = true
  try {
    const res = await api.kbRebuild()
    const e = res.embed || {}
    if (e.error) {
      ElMessage.warning(`分块已重建，但向量重算失败：${e.error}。可稍后点「补算向量」重试`)
    } else {
      ElMessage.success(`重建完成：${res.kb_chunks} 段文档分块，向量补算 ${e.new ?? 0} 条`)
    }
    await init()
  } catch (e) {
    ElMessage.error('重建失败：' + e.message)
  } finally {
    rebuilding.value = false
  }
}

async function cleanText() {
  if (cleaning.value) return
  cleaning.value = true
  try {
    const preview = await api.kbClean(true)
    if (!preview.changed) {
      ElMessage.success('分块正文已经是干净的')
      return
    }
    const res = await api.kbClean(false)
    ElMessage.success(`已整理 ${res.changed} 段分块正文`)
    await init()
  } catch (e) {
    ElMessage.error('整理失败：' + e.message)
  } finally {
    cleaning.value = false
  }
}

async function ingest() {
  ingesting.value = true
  try {
    const res = await api.kbIngest()
    const skipped = (res.skipped || []).length
    let msg = `导入 ${res.imported || 0} 篇`
    if (skipped) msg += `，跳过 ${skipped} 篇（库里的版本更新，未覆盖）`
    if (skipped) ElMessage.warning(msg)
    else ElMessage.success(msg)
    await init()
  } catch (e) {
    ElMessage.error('导入失败：' + e.message)
  } finally {
    ingesting.value = false
  }
}

// 只刷当前这篇 + 分块，不动整个列表，保存后界面不闪
async function refresh() {
  await loadDoc(selectedDocId.value)
  const c = await api.kbChunks('', 2000)
  allChunks.value = c || []
  const d = await api.kbDocs()
  docs.value = d || []
}

async function init() {
  loading.value = true
  try {
    const [d, c] = await Promise.all([api.kbDocs(), api.kbChunks('', 2000)])
    docs.value = d || []
    allChunks.value = c || []
    if (docs.value.length) {
      if (!selectedDocId.value) selectedDocId.value = docs.value[0].doc_id
      await loadDoc(selectedDocId.value)
    }
  } catch (e) {
    ElMessage.error('加载失败：' + e.message)
  } finally {
    loading.value = false
  }
}

onMounted(init)
onActivated(() => { if (!doc.value && selectedDocId.value) loadDoc(selectedDocId.value) })
</script>

<style scoped>
.fill { height: 100%; }
.left-pane { height: 100%; }
.doc-card { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
.doc-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; padding-bottom: 8px; }
.pane-title { font-weight: 600; margin-bottom: 8px; display: flex; align-items: baseline; gap: 6px; }
.doc-list { flex: 1; overflow: auto; }
.doc-item { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 7px 8px; border-radius: 6px; cursor: pointer; }
.doc-item:hover { background: var(--line-soft, #f5f7fa); }
.doc-item.active { background: #ecf5ff; }
.doc-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.doc-cat { flex: 0 0 auto; }
.right-pane { height: 100%; }
.content-card { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
.content-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex: 0 0 auto; flex-wrap: wrap; }
.edit-hint { color: var(--warn, #e6a23c); }
.doc-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 10px; margin-bottom: 10px; background: var(--line-soft, #f7f9fc); border-radius: 6px; flex: 0 0 auto; }
.doc-head-title { font-size: 14px; }
.editor-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.doc-editor { flex: 1; display: flex; }
.doc-editor :deep(.el-textarea) { flex: 1; display: flex; }
.doc-editor :deep(.el-textarea__inner) {
  height: 100%; font-family: ui-monospace, Menlo, Consolas, 'Courier New', monospace;
  font-size: 13px; line-height: 1.75; color: var(--text-1, #303133); resize: none;
}
.editor-foot { margin-top: 6px; font-size: 12px; flex: 0 0 auto; }
.dd-hint { margin-left: 10px; color: var(--text-3, #909399); font-size: 12px; }
.chunk-list { flex: 1; overflow: auto; padding-right: 4px; }
.doc-full { line-height: 1.85; font-size: 13.5px; color: var(--text-1, #303133); }
/* 空行也要占一行，否则段间距会塌掉，整篇糊成一片 */
.md-line { white-space: pre-wrap; word-break: break-word; min-height: 1.85em; }
.md-h { font-weight: 600; margin: 14px 0 4px; line-height: 1.6; color: var(--text-1, #1f2733); }
.md-h1 { font-size: 16px; }
.md-h2 { font-size: 15px; }
.md-h3 { font-size: 14px; }
.md-h4, .md-h5, .md-h6 { font-size: 13.5px; color: var(--text-2, #4a5568); }
.chunk { border-bottom: 1px solid #f0f0f0; padding: 12px 4px; }
.chunk-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.chunk-heading { color: #409eff; font-size: 12px; display: inline-flex; align-items: baseline; gap: 4px; flex-wrap: wrap; }
.h-up { color: var(--text-3, #909399); }
.h-sep { color: var(--text-3, #c0c4cc); }
.h-last { color: #409eff; font-weight: 600; }
.chunk-score { margin-left: auto; color: var(--ok, #67c23a); font-size: 12px; }
.chunk-len { margin-left: auto; font-size: 12px; }
.chunk-text { white-space: pre-wrap; word-break: break-word; line-height: 1.7; font-family: inherit; margin: 0; font-size: 13px; color: var(--text-1, #303133); }
</style>
