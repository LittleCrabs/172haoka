<template>
  <el-row :gutter="12" class="fill">
    <!-- 左侧：文档列表（master） -->
    <el-col :span="6" class="left-pane">
      <el-card shadow="never" class="doc-card">
        <div class="pane-title">知识文档（{{ docs.length }}）</div>
        <el-input v-model="filterText" placeholder="过滤文档名" clearable size="small" style="margin-bottom: 8px" />
        <div class="doc-list">
          <div
            v-for="d in filteredDocs"
            :key="d.doc_id"
            class="doc-item"
            :class="{ active: selectedDocId === d.doc_id }"
            @click="selectDoc(d.doc_id)"
          >
            <span class="doc-title">{{ d.title }}</span>
            <el-tag size="small" effect="plain" class="doc-cat">{{ d.category || d.audience }}</el-tag>
          </div>
          <el-empty v-if="!filteredDocs.length" description="暂无文档" :image-size="50" />
        </div>
      </el-card>
    </el-col>

    <!-- 右侧：内容阅读（detail，长文可滚动） -->
    <el-col :span="18" class="right-pane">
      <el-card shadow="never" class="content-card">
        <div class="toolbar">
          <el-input
            v-model="searchQ"
            placeholder="搜索知识库内容（支持中文关键词）"
            clearable
            style="width: 320px"
            @input="onSearch"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <span class="muted" v-if="searchQ">共 {{ displayChunks.length }} 条匹配</span>
          <span class="muted" v-else-if="selectedDoc">《{{ selectedDoc.title }}》共 {{ displayChunks.length }} 段</span>
          <div class="spacer" />
          <el-button :icon="Refresh" :loading="rebuilding" @click="rebuild">重建分块</el-button>
          <el-button :icon="Upload" :loading="ingesting" @click="ingest">导入外挂</el-button>
        </div>

        <div class="chunk-list" v-loading="loading">
          <el-empty v-if="!displayChunks.length" :description="searchQ ? '没有匹配的内容' : '请选择左侧文档'" />
          <div v-for="(c, i) in displayChunks" :key="c.chunk_id || i" class="chunk">
            <div class="chunk-head">
              <el-tag size="small" type="info">{{ c.doc_id }}</el-tag>
              <b class="chunk-title">{{ c.title }}</b>
              <span v-if="c.heading" class="chunk-heading">{{ c.heading }}</span>
              <span v-if="c.score != null" class="chunk-score">匹配度 {{ c.score }}</span>
            </div>
            <pre class="chunk-text">{{ c.text }}</pre>
          </div>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Upload } from '@element-plus/icons-vue'
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

const selectedDoc = computed(() => docs.value.find((d) => d.doc_id === selectedDocId.value) || null)
const filteredDocs = computed(() => {
  const t = filterText.value.trim()
  if (!t) return docs.value
  return docs.value.filter((d) => (d.title || '').includes(t))
})
const displayChunks = computed(() => {
  if (searchQ.value.trim()) return searchResults.value
  if (!selectedDocId.value) return []
  return allChunks.value.filter((c) => c.doc_id === selectedDocId.value)
})

function selectDoc(id) {
  selectedDocId.value = id
  searchQ.value = ''
  searchResults.value = []
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
      const res = await api.kbChunks(q, 80)
      searchResults.value = res || []
    } catch (e) {
      ElMessage.error('搜索失败：' + e.message)
    } finally {
      loading.value = false
    }
  }, 250)
}

async function rebuild() {
  rebuilding.value = true
  try {
    await api.kbRebuild()
    ElMessage.success('重建完成')
    await init()
  } catch (e) {
    ElMessage.error('重建失败：' + e.message)
  } finally {
    rebuilding.value = false
  }
}

async function ingest() {
  ingesting.value = true
  try {
    const res = await api.kbIngest()
    ElMessage.success(`导入 ${res.added || 0} 篇（更新 ${res.updated || 0}）`)
    await init()
  } catch (e) {
    ElMessage.error('导入失败：' + e.message)
  } finally {
    ingesting.value = false
  }
}

async function init() {
  loading.value = true
  try {
    const [d, c] = await Promise.all([api.kbDocs(), api.kbChunks('', 2000)])
    docs.value = d || []
    allChunks.value = c || []
    if (docs.value.length && !selectedDocId.value) selectedDocId.value = docs.value[0].doc_id
  } catch (e) {
    ElMessage.error('加载失败：' + e.message)
  } finally {
    loading.value = false
  }
}

onMounted(init)
</script>

<style scoped>
.fill { height: 100%; }
.left-pane { height: 100%; }
.doc-card { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
.doc-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; padding-bottom: 8px; }
.pane-title { font-weight: 600; margin-bottom: 8px; }
.doc-list { flex: 1; overflow: auto; }
.doc-item { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 8px; border-radius: 6px; cursor: pointer; }
.doc-item:hover { background: #f5f7fa; }
.doc-item.active { background: #ecf5ff; }
.doc-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.doc-cat { flex: 0 0 auto; }
.right-pane { height: 100%; }
.content-card { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
.content-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex: 0 0 auto; }
.chunk-list { flex: 1; overflow: auto; padding-right: 4px; }
.chunk { border-bottom: 1px solid #f0f0f0; padding: 12px 4px; }
.chunk-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.chunk-title { font-size: 14px; }
.chunk-heading { color: #409eff; font-size: 12px; }
.chunk-score { margin-left: auto; color: #67c23a; font-size: 12px; }
.chunk-text { white-space: pre-wrap; word-break: break-word; line-height: 1.7; font-family: inherit; margin: 0; font-size: 13px; color: #303133; }
</style>
