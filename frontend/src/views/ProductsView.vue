<template>
  <div class="fill">
    <el-card shadow="never" class="filter-card">
      <div class="filter-bar">
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
        <div class="spacer"></div>
        <el-button type="primary" :icon="Search" :loading="loading" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
        <el-button :icon="Refresh" :loading="syncing" @click="sync">同步</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table
        :data="rows" v-loading="loading" stripe height="100%" row-key="product_id"
        @sort-change="onSortChange"
      >
        <el-table-column type="expand">
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
          </template>
        </el-table-column>
        <el-table-column prop="product_name" label="商品名" min-width="340" sortable="custom">
          <template #default="{ row }">
            <div class="name-cell" :title="row.product_name">
              <el-tag v-if="row.is_zhutui" size="small" type="danger" effect="dark" class="zt-tag">主推</el-tag>
              <span>{{ row.product_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="operator" label="运营商" width="78" />
        <el-table-column prop="category" label="分类" width="80" />
        <el-table-column prop="monthly_fee" label="月租" width="90" sortable="custom">
          <template #default="{ row }">{{ row.monthly_fee ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="data_gb" label="流量" width="90" sortable="custom">
          <template #default="{ row }">{{ row.data_gb != null ? row.data_gb + 'G' : '—' }}</template>
        </el-table-column>
        <el-table-column prop="voice_min" label="语音" width="86" sortable="custom">
          <template #default="{ row }">{{ row.voice_min ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="commission" label="佣金" width="150" sortable="custom" show-overflow-tooltip>
          <template #default="{ row }">{{ row.commission_read || '—' }}</template>
        </el-table-column>
        <el-table-column prop="area" label="归属地" width="90" sortable="custom" show-overflow-tooltip />
        <el-table-column prop="age_range" label="年龄" width="86" />
        <el-table-column prop="disable_area" label="禁发地区" min-width="160" show-overflow-tooltip />
        <el-table-column prop="create_time" label="添加时间" width="110" sortable="custom">
          <template #default="{ row }">{{ row.create_time ? row.create_time.slice(0, 10) : '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="78" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="load"
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
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import { api } from '../api'

const facets = reactive({ operators: [], categories: [], areas: [] })
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const loading = ref(false)
const syncing = ref(false)
const filters = reactive({ q: '', operator: '', category: '', max_fee: null, min_data: null, region: '', zhutui: false })
const sortBy = ref('')
const sortOrder = ref('')
const drawerVisible = ref(false)
const detailUrl = ref('')
const currentName = ref('')

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
      age_range: r.age_min && r.age_max ? `${r.age_min}-${r.age_max}` : '—',
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
  load()
}

function debouncedSearch() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { page.value = 1; load() }, 350)
}

function reset() {
  Object.assign(filters, { q: '', operator: '', category: '', max_fee: null, min_data: null, region: '', zhutui: false })
  sortBy.value = ''
  sortOrder.value = ''
  search()
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

onMounted(() => {
  loadFacets()
  load()
})
</script>

<style scoped>
.fill { height: 100%; display: flex; flex-direction: column; gap: 10px; }
.filter-card { flex: 0 0 auto; }
.filter-card :deep(.el-card__body) { padding: 10px 14px; }
.filter-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.filter-bar .kw { width: 280px; }
.filter-bar .sel { width: 118px; }
.filter-bar .sel-wide { width: 140px; }
.filter-bar .num { width: 100px; }
.table-card { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.table-card :deep(.el-card__body) {
  flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; padding: 8px 14px 6px;
}
.name-cell { white-space: normal; line-height: 1.45; word-break: break-word; }
.zt-tag { margin-right: 6px; vertical-align: middle; }
.pager { margin-top: 6px; text-align: right; }
.specs { padding: 8px 16px; line-height: 1.8; }
</style>

<style>
/* 抽屉被 teleport 到 body，用非 scoped 样式才能命中 */
.detail-drawer .el-drawer__body { padding: 0; overflow: hidden; }
.detail-frame { display: block; width: 100%; height: 100%; border: 0; background: #fff; }
.empty-detail { padding: 24px; }
</style>
