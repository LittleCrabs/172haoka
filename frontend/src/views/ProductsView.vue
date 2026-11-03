<template>
  <div class="fill">
    <el-card shadow="never" class="filter-card toolbar-card">
      <div class="filter-bar">
        <div class="filters">
          <el-input
            v-model="filters.q"
            class="kw"
            placeholder="搜索商品名 / 关键词 / 备注 / 地区"
            :prefix-icon="Search"
            clearable
            @input="debouncedSearch"
            @keyup.enter="search"
          />
          <el-select v-model="filters.operator" placeholder="运营商" clearable class="sel" @change="search">
            <el-option v-for="o in facets.operators" :key="o" :label="o" :value="o" />
          </el-select>
          <el-select v-model="filters.category" placeholder="分类" clearable class="sel" @change="search">
            <el-option v-for="c in facets.categories" :key="c" :label="c" :value="c" />
          </el-select>
          <el-select v-model="filters.region" placeholder="地区" clearable filterable class="sel-wide" @change="search">
            <el-option v-for="a in facets.areas" :key="a" :label="a" :value="a" />
          </el-select>
          <el-input-number
            v-model="filters.max_fee" :min="0" :controls="false" placeholder="月租≤"
            class="num" @change="search"
          />
          <el-input-number
            v-model="filters.min_data" :min="0" :controls="false" placeholder="流量≥"
            class="num" @change="search"
          />
          <el-checkbox v-model="filters.zhutui" @change="search">只看主推</el-checkbox>
        </div>
        <div class="actions">
          <el-button type="primary" :icon="Search" :loading="loading" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
          <el-button :icon="Refresh" :loading="syncing" @click="sync">同步</el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table
        ref="tableRef"
        :data="rows" v-loading="loading" stripe height="100%" row-key="product_id"
        @sort-change="onSortChange" @selection-change="onSelect"
      >
        <el-table-column type="selection" width="42" fixed="left" />
        <el-table-column type="expand" width="34">
          <template #default="{ row }">
            <div v-if="row.specs" class="specs">
              <div><b>流量结构：</b>
                总量 {{ row.specs.total_gb ?? '—' }}G /
                通用 {{ row.specs.general_gb ?? '—' }}G /
                定向 {{ row.specs.directional_gb ?? 0 }}G /
                夜间 {{ row.specs.night_gb ?? 0 }}G
                <span v-if="row.specs.night_window">（{{ row.specs.night_window }}）</span>
              </div>
              <div class="muted" v-if="row.specs.evidence">解析依据：{{ row.specs.evidence }}</div>
            </div>
            <div v-else class="muted">该商品暂无流量结构解析</div>
            <!-- 年龄、添加时间这类低频信息从列里挪进来：表宽不够时它们最先被裁成「18…」 -->
            <div class="specs meta-line">
              <span>适用年龄：<b>{{ row.age_range }}</b></span>
              <span>添加时间：<b>{{ row.create_time ? row.create_time.slice(0, 10) : '—' }}</b></span>
              <span>商品 ID：<b>{{ row.product_id }}</b></span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="product_name" label="商品名" min-width="300" sortable="custom">
          <template #default="{ row }">
            <div class="name-cell" :title="row.product_name">
              <el-tag v-if="row.is_zhutui" size="small" effect="plain" class="zt-tag">主推</el-tag>
              <span>{{ row.product_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="operator" label="运营商" width="76" />
        <el-table-column prop="category" label="分类" width="70">
          <template #default="{ row }">
            <span class="cat">{{ row.category || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="monthly_fee" label="月租" width="86" align="right" sortable="custom">
          <template #default="{ row }">
            <span v-if="row.monthly_fee != null" class="num-cell">{{ row.monthly_fee }}</span>
            <span v-else class="nil">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="data_gb" label="流量" width="84" align="right" sortable="custom">
          <template #default="{ row }">
            <span v-if="row.data_gb != null" class="num-cell">{{ row.data_gb }}<i class="unit">G</i></span>
            <span v-else class="nil">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="voice_min" label="语音" width="76" align="right" sortable="custom">
          <template #default="{ row }">
            <span v-if="row.voice_min != null" class="num-cell">{{ row.voice_min }}</span>
            <span v-else class="nil">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="commission" label="佣金" width="132" align="right" sortable="custom">
          <template #default="{ row }">
            <div v-if="row.commission_read" class="comm">
              <span class="num-cell">{{ splitCommission(row.commission_read).amount }}</span>
              <span v-if="splitCommission(row.commission_read).note" class="comm-note">
                {{ splitCommission(row.commission_read).note }}
              </span>
            </div>
            <span v-else class="nil">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="area" label="归属地" width="82" sortable="custom">
          <template #default="{ row }">{{ row.area || '—' }}</template>
        </el-table-column>
        <el-table-column prop="disable_area" label="禁发地区" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ nil: !row.disable_area }">{{ row.disable_area || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            type="search"
            :title="hasFilter ? '没有符合条件的商品' : '商品库还是空的'"
            :desc="hasFilter ? '放宽一下筛选条件，或者清空关键词再试' : '点右上角「同步」从后台拉一次商品数据'"
          >
            <template #action>
              <el-button v-if="hasFilter" size="small" @click="reset">清空筛选</el-button>
              <el-button v-else size="small" type="primary" :loading="syncing" @click="sync">立即同步</el-button>
            </template>
          </EmptyState>
        </template>
      </el-table>

      <!-- 批量操作条：选中才出现，固定在表格底部，不挤压表格高度 -->
      <div v-if="selected.length" class="batch-bar">
        <span class="batch-count">已选 <b>{{ selected.length }}</b> 项</span>
        <div class="batch-actions">
          <el-button size="small" :icon="Download" @click="exportCsv(selected, '选中商品')">
            导出 CSV
          </el-button>
          <el-button size="small" @click="exportCsv(rows, '当前页商品')">导出本页</el-button>
          <el-button size="small" text @click="clearSelection">取消选择</el-button>
        </div>
      </div>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[50, 100, 200]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="load"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>

    <el-drawer
      v-model="drawerVisible"
      :title="currentName || '商品详情'"
      size="560px"
      :destroy-on-close="true"
      class="detail-drawer"
    >
      <iframe v-if="detailUrl" :src="detailUrl" class="detail-frame" referrerpolicy="no-referrer" />
      <div v-else class="muted empty-detail">该商品暂无详情页链接，请先同步一次（需有效的 H5 域名）</div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Search, Download } from '@element-plus/icons-vue'
import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'

defineOptions({ name: 'ProductsView' })

const route = useRoute()

const facets = reactive({ operators: [], categories: [], areas: [] })
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const loading = ref(false)
const syncing = ref(false)
const selected = ref([])
const tableRef = ref(null)
const filters = reactive({ q: '', operator: '', category: '', max_fee: null, min_data: null, region: '', zhutui: false })
const sortBy = ref('')
const sortOrder = ref('')
const drawerVisible = ref(false)
const detailUrl = ref('')
const currentName = ref('')

const hasFilter = computed(() =>
  !!(filters.q || filters.operator || filters.category || filters.region ||
     filters.max_fee != null || filters.min_data != null || filters.zhutui))

// ---------------- 筛选条件持久化 ----------------
// 之前切到别的页面再回来，筛选全丢、页码回到第一页，802 个商品要重新点一遍。
const FILTER_KEY = 'products.filters'
function saveFilters() {
  try {
    localStorage.setItem(FILTER_KEY, JSON.stringify({
      filters: { ...filters }, sortBy: sortBy.value, sortOrder: sortOrder.value, pageSize: pageSize.value,
    }))
  } catch { /* 隐私模式忽略 */ }
}
function restoreFilters() {
  try {
    const v = JSON.parse(localStorage.getItem(FILTER_KEY) || '{}')
    if (v.filters) Object.assign(filters, v.filters)
    if (v.sortBy) { sortBy.value = v.sortBy; sortOrder.value = v.sortOrder || '' }
    if (v.pageSize) pageSize.value = v.pageSize
  } catch { /* 坏数据忽略 */ }
}

let timer = null

async function load() {
  loading.value = true
  try {
    const res = await api.products({
      q: filters.q,
      operator: filters.operator,
      category: filters.category,
      max_fee: filters.max_fee,
      min_data: filters.min_data,
      region: filters.region,
      zhutui: filters.zhutui ? 1 : undefined,
      sort: sortBy.value,
      order: sortOrder.value,
      page: page.value,
      page_size: pageSize.value,
    })
    rows.value = (res.items || []).map((r) => ({
      ...r,
      age_range: r.age_min && r.age_max ? `${r.age_min}-${r.age_max} 岁` : '不限',
    }))
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载失败：' + e.message)
  } finally {
    loading.value = false
  }
}

function search() {
  if (timer) clearTimeout(timer)
  page.value = 1
  saveFilters()
  load()
}

function debouncedSearch() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { page.value = 1; saveFilters(); load() }, 350)
}

function reset() {
  Object.assign(filters, { q: '', operator: '', category: '', max_fee: null, min_data: null, region: '', zhutui: false })
  sortBy.value = ''
  sortOrder.value = ''
  page.value = 1
  saveFilters()
  load()
}

function onSortChange({ prop, order }) {
  if (!order) {
    sortBy.value = ''
    sortOrder.value = ''
  } else {
    sortBy.value = prop
    sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  }
  search()
}

function onSizeChange() {
  page.value = 1
  saveFilters()
  load()
}

function onSelect(list) {
  selected.value = list
}

function clearSelection() {
  tableRef.value && tableRef.value.clearSelection()
  selected.value = []
}

async function loadFacets() {
  try {
    const f = await api.facets()
    facets.operators = f.operators || []
    facets.categories = f.categories || []
    facets.areas = f.areas || []
  } catch (e) { /* 忽略：候选值拿不到不影响主流程 */ }
}

// 详情 = 抽屉内嵌加载外部商品详情页（H5 iframe），不新开标签页
function openDetail(row) {
  currentName.value = row.product_name
  detailUrl.value = row.detail_url || ''
  drawerVisible.value = true
}

// 「¥120.00(次月返)」拆成金额 + 说明：金额等宽右对齐，说明独立小标签，
// 免得一个括号把整列数字挤得参差不齐
function splitCommission(text) {
  const s = String(text || '')
  const m = s.match(/^(.*?)\s*[（(](.+?)[)）]\s*$/)
  if (m) return { amount: m[1].trim(), note: m[2].trim() }
  return { amount: s, note: '' }
}

function exportCsv(list, label) {
  if (!list || !list.length) { ElMessage.warning('没有可导出的数据'); return }
  const head = ['商品名', '运营商', '分类', '月租', '流量(GB)', '语音(分钟)', '佣金', '佣金类型',
    '归属地', '禁发地区', '年龄', '添加时间', '商品ID']
  const lines = [head.join(',')]
  for (const r of list) {
    const comm = splitCommission(r.commission_read)
    lines.push([
      r.product_name, r.operator, r.category, r.monthly_fee ?? '', r.data_gb ?? '',
      r.voice_min ?? '', comm.amount, comm.note, r.area, r.disable_area,
      r.age_range, r.create_time ? r.create_time.slice(0, 10) : '', r.product_id,
    ].map(csvCell).join(','))
  }
  // BOM 必须加：不加 Excel 打开中文全是乱码
  const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${label}_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(`已导出 ${list.length} 条`)
}

function csvCell(v) {
  const s = String(v ?? '')
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}

async function sync() {
  syncing.value = true
  try {
    const res = await api.sync()
    ElMessage.success(
      `同步完成：共 ${res.total ?? 0}，新增 ${res.inserted ?? 0}，更新 ${res.updated ?? 0}，下架 ${res.offsale ?? 0}`
    )
    await loadFacets()
    load()
  } catch (e) {
    ElMessage.error('同步失败：' + e.message)
  } finally {
    syncing.value = false
  }
}

// 从全局搜索跳过来会带 ?q=，直接当关键词用（关键词优先于本地记住的筛选）
function applyRouteQuery() {
  const q = route.query.q
  if (typeof q === 'string' && q) {
    filters.q = q
    page.value = 1
    load()
    return true
  }
  return false
}

watch(() => route.query.q, () => { applyRouteQuery() })

onMounted(() => {
  restoreFilters()
  loadFacets()
  if (!applyRouteQuery()) load()
})
</script>

<style scoped>
.fill { height: 100%; display: flex; flex-direction: column; gap: 12px; }
.filter-card { flex: 0 0 auto; }
.filter-bar { display: flex; align-items: center; gap: 12px; }
.filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex: 1; min-width: 0; }
.actions { display: flex; gap: 8px; flex: 0 0 auto; }
.filter-bar .kw { width: 226px; }
.filter-bar .sel { width: 104px; }
.filter-bar .sel-wide { width: 122px; }
.filter-bar .num { width: 88px; }
.table-card { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.table-card :deep(.el-card__body) {
  flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; padding: 8px 14px 6px;
}
.name-cell { white-space: normal; line-height: 1.45; word-break: break-word; }
/* 主推用蓝色描边：橙在这套界面里留给「需注意」，营销标记不该抢这个语义 */
.zt-tag { margin-right: 6px; vertical-align: middle; }
.cat { color: var(--text-2); }
.nil { color: #c3c9d4; }
.unit { font-style: normal; font-size: 11px; color: var(--text-3); margin-left: 1px; }
.comm { display: inline-flex; align-items: center; gap: 5px; justify-content: flex-end; }
.comm-note {
  font-size: 11px;
  color: var(--text-3);
  background: #f4f6fa;
  border-radius: 3px;
  padding: 0 4px;
  line-height: 16px;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
  padding: 7px 12px;
  border-radius: 8px;
  background: var(--brand-soft);
  border: 1px solid #dbe6ff;
}
.batch-count { font-size: 12.5px; color: var(--text-2); }
.batch-actions { margin-left: auto; display: flex; gap: 8px; }

.pager { margin-top: 6px; text-align: right; }
.specs { padding: 8px 16px; line-height: 1.8; }
.meta-line { display: flex; gap: 24px; color: var(--text-3); font-size: 12.5px; }
.meta-line b { color: var(--text-2); font-weight: 500; }
</style>

<style>
/* 抽屉被 teleport 到 body，用非 scoped 样式才能命中 */
.detail-drawer .el-drawer__body { padding: 0; overflow: hidden; }
.detail-frame { display: block; width: 100%; height: 100%; border: 0; background: #fff; }
.empty-detail { padding: 24px; }
</style>
