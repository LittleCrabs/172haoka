<template>
  <div class="fill">
    <el-card shadow="never" class="filter-card toolbar-card">
      <div class="filter-bar">
        <div class="filters">
          <el-input
            v-model="filters.q"
            class="kw"
            placeholder="搜索商品名 / 地区 / 备注 / 套餐"
            :prefix-icon="Search"
            clearable
            @input="debouncedSearch"
            @keyup.enter="search"
          />
          <el-select v-model="filters.operator" placeholder="运营商" clearable class="sel" @change="search">
            <el-option v-for="o in facets.operators" :key="o" :label="o" :value="o" />
          </el-select>
          <el-select v-model="filters.area" placeholder="地区" clearable class="sel" @change="search">
            <el-option v-for="a in facets.areas" :key="a" :label="a" :value="a" />
          </el-select>
          <el-select v-model="filters.speed" placeholder="带宽" clearable class="sel" @change="search">
            <el-option label="全部带宽" :value="null" />
            <el-option v-for="s in facets.speeds" :key="s" :label="s + 'M'" :value="s" />
          </el-select>
          <el-select v-model="filters.flag" placeholder="上架状态" clearable class="sel" @change="search">
            <el-option label="未上架" value="0" />
            <el-option label="已上架" value="1" />
            <el-option label="全部" value="" />
          </el-select>
          <el-select v-model="filters.zhutui" placeholder="主推" clearable class="sel" @change="search">
            <el-option label="仅主推" :value="1" />
            <el-option label="不限" :value="null" />
          </el-select>
          <div class="price-range">
            <el-input-number v-model="filters.price_min" :min="0" :controls="false" placeholder="最低价" @change="search" />
            <span class="tilde">~</span>
            <el-input-number v-model="filters.price_max" :min="0" :controls="false" placeholder="最高价" @change="search" />
          </div>
        </div>
        <div class="actions">
          <el-button type="primary" :icon="Search" :loading="loading" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table
        ref="tableRef"
        :data="rows" v-loading="loading" stripe height="100%"
        row-key="product_id" @selection-change="onSelect"
      >
        <el-table-column type="selection" width="42" fixed="left" />
        <el-table-column prop="product_name" label="商品名" min-width="300">
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.product_name }}</span>
              <el-tag v-if="row.zhutui" size="small" effect="plain" class="zt-tag">主推</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="operator" label="运营商" width="80" />
        <el-table-column label="带宽" width="76" align="right">
          <template #default="{ row }">
            <span v-if="row.speed" class="num-cell">{{ row.speed }}<i class="unit">M</i></span>
            <span v-else class="nil">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="area" label="地区" width="92" />
        <el-table-column width="126" align="right">
          <template #header>
            <span class="th-with-tip">
              价格
              <el-tooltip placement="top" :show-after="200">
                <template #content>
                  平台接口对宽带不下发资费（price 恒为 0、priceRead 恒为「¥0.00」），<br />
                  这里显示的是从商品名解析出来的真实资费，如「600元/年」。<br />
                  名称里没写价格的一律显示「—」，不再用 ¥0.00 占位。
                </template>
                <el-icon class="th-tip"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <template #default="{ row }">
            <span v-if="row.price_read" class="price-text">{{ row.price_read }}</span>
            <span v-else class="nil">—</span>
          </template>
        </el-table-column>
        <el-table-column label="佣金" width="132" align="right">
          <template #default="{ row }">
            <!-- 「¥520.00(次月返)」挤在 110px 里会折成两行，把这一行的行高顶高，
                 整张表看起来参差不齐。金额和结算方式拆开，金额等宽对齐。 -->
            <template v-if="row.s_price_read">
              <span class="num-cell">{{ splitComm(row.s_price_read).amount }}</span>
              <span v-if="splitComm(row.s_price_read).note" class="comm-note">
                {{ splitComm(row.s_price_read).note }}
              </span>
            </template>
            <span v-else class="nil">—</span>
          </template>
        </el-table-column>
        <el-table-column label="上架状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.flag ? 'success' : 'info'" effect="plain">
              {{ row.flag ? '已上架' : '未上架' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openDetail(row)">详情</el-button>
            <el-button
              size="small" text :type="row.flag ? 'warning' : 'success'"
              :loading="row._toggling" @click="toggleShelf(row)"
            >
              {{ row.flag ? '下架' : '上架' }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            type="search"
            :title="hasFilter ? '没有符合条件的宽带' : '选品目录是空的'"
            :desc="hasFilter ? '换个地区或去掉价格区间试试' : '去「设置 · 数据同步」里同步一次宽带选品'"
          >
            <template #action>
              <el-button v-if="hasFilter" size="small" @click="reset">清空筛选</el-button>
              <el-button v-else size="small" type="primary" @click="$router.push('/settings')">去同步</el-button>
            </template>
          </EmptyState>
        </template>
      </el-table>

      <!-- 批量操作：800 多条未上架，逐条点「上架」不现实 -->
      <div v-if="selected.length" class="batch-bar">
        <span class="batch-count">
          已选 <b>{{ selected.length }}</b> 项
          <span class="batch-split">
            （未上架 {{ selectedOff }} · 已上架 {{ selectedOn }}）
          </span>
        </span>
        <div class="batch-actions">
          <el-button
            size="small" type="success" plain :icon="Top"
            :disabled="!selectedOff" :loading="batchBusy" @click="batchToggle(true)"
          >
            批量上架{{ selectedOff ? ` (${selectedOff})` : '' }}
          </el-button>
          <el-button
            size="small" type="warning" plain :icon="Bottom"
            :disabled="!selectedOn" :loading="batchBusy" @click="batchToggle(false)"
          >
            批量下架{{ selectedOn ? ` (${selectedOn})` : '' }}
          </el-button>
          <el-button size="small" :icon="Download" @click="exportCsv">导出 CSV</el-button>
          <el-button size="small" text @click="clearSelection">取消选择</el-button>
        </div>
      </div>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          :total="pagination.total"
          @change="onPageChange"
        />
      </div>
    </el-card>

    <!-- 详情对话框（与商品库详情一致：全字段 + 主图 + H5 链接） -->
    <el-dialog v-model="detailVisible" :title="current?.product_name" width="720px" destroy-on-close>
      <div v-if="current" class="detail-body">
        <div class="detail-pics" v-if="current.main_pic || current.little_picture">
          <el-image v-if="current.main_pic" :src="current.main_pic" fit="contain"
            style="width:140px;height:140px" :preview-src-list="[current.main_pic]" />
          <el-image v-if="current.little_picture" :src="current.little_picture" fit="contain"
            style="width:140px;height:140px" :preview-src-list="[current.little_picture]" />
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="运营商">{{ current.operator || '—' }}</el-descriptions-item>
          <el-descriptions-item label="带宽">{{ current.speed ? current.speed + 'M' : '—' }}</el-descriptions-item>
          <el-descriptions-item label="价格">
            {{ current.price_read || '—' }}
            <span v-if="current.price_source === 'name'" class="est">按商品名解析</span>
          </el-descriptions-item>
          <el-descriptions-item label="佣金">{{ current.s_price_read || '—' }}</el-descriptions-item>
          <el-descriptions-item label="佣金类型">{{ current.commission_type || '—' }}</el-descriptions-item>
          <el-descriptions-item label="上架状态">
            <el-tag size="small" :type="current.flag ? 'success' : 'info'" effect="plain">
              {{ current.flag ? '已上架' : '未上架' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="下级状态">
            <el-tag size="small" :type="current.low_flag ? 'success' : 'info'" effect="plain">
              {{ current.low_flag ? '正常' : '异常' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="主推">{{ current.zhutui ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="地区">{{ current.area || '—' }}</el-descriptions-item>
          <el-descriptions-item label="地区(详)" :span="2">{{ current.area_read || '—' }}</el-descriptions-item>
          <el-descriptions-item label="禁售地区" :span="2">{{ current.disable_area || '—' }}</el-descriptions-item>
          <el-descriptions-item label="套餐">{{ current.taocan || '—' }}</el-descriptions-item>
          <el-descriptions-item label="备注(备)">{{ current.beizhu || '—' }}</el-descriptions-item>
          <el-descriptions-item label="规则" :span="2">{{ current.rule || '—' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ current.remark || '—' }}</el-descriptions-item>
          <el-descriptions-item label="添加时间">{{ current.create_time || '—' }}</el-descriptions-item>
          <el-descriptions-item label="商品ID">{{ current.product_id }}</el-descriptions-item>
        </el-descriptions>
        <div class="detail-link" v-if="current.detail_url">
          <el-link type="primary" :href="current.detail_url" target="_blank">打开 H5 套餐详情页 ↗</el-link>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Search, QuestionFilled, Download, Top, Bottom } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'

defineOptions({ name: 'KuanproView' })

const route = useRoute()

const loading = ref(false)
const rows = ref([])
const facets = ref({ operators: [], areas: [], speeds: [] })
const detailVisible = ref(false)
const current = ref(null)
const selected = ref([])
const batchBusy = ref(false)
const tableRef = ref(null)

// 默认看「未上架」内容（选品广场 = 没上架的可选目录）
const DEFAULT_FILTERS = {
  q: '', operator: '', area: '', speed: null, flag: '0', zhutui: null, price_min: null, price_max: null,
}
const filters = ref({ ...DEFAULT_FILTERS })
const pagination = ref({ page: 1, page_size: 50, total: 0 })

const selectedOn = computed(() => selected.value.filter((r) => r.flag).length)
const selectedOff = computed(() => selected.value.length - selectedOn.value)
const hasFilter = computed(() =>
  !!(filters.value.q || filters.value.operator || filters.value.area ||
     filters.value.speed != null || filters.value.zhutui != null ||
     filters.value.price_min != null || filters.value.price_max != null ||
     (filters.value.flag !== '' && filters.value.flag !== '0')))

// 筛选条件记在本机：来回切页面不用重新点一遍七个下拉
const FILTER_KEY = 'kuanpro.filters'
function saveFilters() {
  try {
    localStorage.setItem(FILTER_KEY, JSON.stringify({
      filters: filters.value, page_size: pagination.value.page_size,
    }))
  } catch { /* 隐私模式忽略 */ }
}
function restoreFilters() {
  try {
    const v = JSON.parse(localStorage.getItem(FILTER_KEY) || '{}')
    if (v.filters) filters.value = { ...DEFAULT_FILTERS, ...v.filters }
    if (v.page_size) pagination.value.page_size = v.page_size
  } catch { /* 坏数据忽略 */ }
}

let debounceTimer = null
function debouncedSearch() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(search, 350)
}

async function search() {
  loading.value = true
  try {
    const f = filters.value
    const res = await api.kuanproList({
      page: pagination.value.page,
      page_size: pagination.value.page_size,
      q: f.q || undefined,
      operator: f.operator || undefined,
      area: f.area || undefined,
      speed: f.speed ?? undefined,
      flag: f.flag === '' ? undefined : f.flag,
      zhutui: f.zhutui ?? undefined,
      price_min: f.price_min ?? undefined,
      price_max: f.price_max ?? undefined,
    })
    rows.value = res.items || []
    pagination.value.total = res.total || 0
  } catch (e) {
    ElMessage.error('加载失败：' + e.message)
  } finally {
    loading.value = false
  }
}

function onPageChange() {
  saveFilters()
  search()
}

function reset() {
  filters.value = { ...DEFAULT_FILTERS }
  pagination.value.page = 1
  saveFilters()
  search()
}

function onSelect(list) {
  selected.value = list
}

function clearSelection() {
  tableRef.value && tableRef.value.clearSelection()
  selected.value = []
}

function openDetail(row) {
  current.value = row
  detailVisible.value = true
}

async function toggleShelf(row) {
  row._toggling = true
  const verb = row.flag ? '下架' : '上架'
  const target = !row.flag
  try {
    const res = await api.kuanproToggle(row.product_id, target)
    // 乐观更新：本地立即翻成目标状态，给即时反馈。
    // 真实上架状态是异步的，需「一键同步」从平台拉回后再校准，
    // 因此这里不自动刷新（否则会把乐观值刷回过时的本地值）。
    row.flag = target
    ElMessage.success(
      `已提交${verb}申请${res.message ? '：' + res.message : ''}` +
      `（本地已标记为${target ? '已上架' : '未上架'}，同步后校准）`
    )
  } catch (e) {
    ElMessage.error('操作失败：' + e.message)
  } finally {
    row._toggling = false
  }
}

async function batchToggle(target) {
  // 上架一批、下架一批分别提交，混选时各自只处理该处理的那部分
  const list = selected.value.filter((r) => !!r.flag !== target)
  if (!list.length) return
  const verb = target ? '上架' : '下架'
  try {
    await ElMessageBox.confirm(
      `确认把选中的 ${list.length} 条宽带提交「${verb}」？\n` +
      '后台上架是异步处理的，本地状态会先标记，同步后校准。',
      `批量${verb}`,
      { confirmButtonText: `确认${verb}`, cancelButtonText: '取消', type: 'warning' }
    )
  } catch (e) {
    return  // 用户取消
  }

  batchBusy.value = true
  try {
    const res = await api.kuanproToggleBatch(list.map((r) => r.product_id), target)
    const okIds = new Set(res.ids || [])
    for (const r of rows.value) {
      if (okIds.has(r.product_id)) r.flag = target
    }
    if (res.failed && res.failed.length) {
      ElMessage.warning(`成功 ${res.succeeded} 条，失败 ${res.failed.length} 条（${res.failed[0].message}）`)
    } else {
      ElMessage.success(`已提交 ${res.succeeded} 条${verb}申请，同步后校准本地状态`)
    }
    clearSelection()
  } catch (e) {
    ElMessage.error(`批量${verb}失败：` + e.message)
  } finally {
    batchBusy.value = false
  }
}

function exportCsv() {
  const list = selected.value.length ? selected.value : rows.value
  if (!list.length) { ElMessage.warning('没有可导出的数据'); return }
  const head = ['商品名', '运营商', '带宽(M)', '地区', '价格', '价格周期', '佣金', '佣金类型',
    '上架状态', '主推', '添加时间', '商品ID']
  const lines = [head.join(',')]
  for (const r of list) {
    lines.push([
      r.product_name, r.operator, r.speed ?? '', r.area, r.price_read ?? '', r.price_period ?? '',
      r.s_price_read ?? '', r.commission_type ?? '', r.flag ? '已上架' : '未上架',
      r.zhutui ? '是' : '否', r.create_time ?? '', r.product_id,
    ].map(csvCell).join(','))
  }
  const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `宽带选品_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(`已导出 ${list.length} 条`)
}

// 「¥520.00(次月返)」→ { amount: '¥520.00', note: '次月返' }
function splitComm(s) {
  const m = /^\s*(.+?)\s*[（(]([^）)]+)[）)]\s*$/.exec(String(s || ''))
  return m ? { amount: m[1], note: m[2] } : { amount: String(s || ''), note: '' }
}

function csvCell(v) {
  const s = String(v ?? '')
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}

watch(filters, saveFilters, { deep: true })

onMounted(() => {
  restoreFilters()
  search()
  api.kuanproFacets().then(r => {
    facets.value.operators = r.operators || []
    facets.value.areas = r.areas || []
    facets.value.speeds = r.speeds || []
  }).catch(() => {})
})
</script>

<style scoped>
.fill { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.filter-card { flex-shrink: 0; }
.filter-bar { display: flex; align-items: center; gap: 12px; }
.filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex: 1; min-width: 0; }
.actions { display: flex; gap: 8px; flex: 0 0 auto; }
.filter-bar .kw { width: 212px; }
.filter-bar .sel { width: 96px; }
.price-range { display: flex; align-items: center; gap: 4px; }
.price-range :deep(.el-input-number) { width: 88px; }
.tilde { color: #909399; }
.table-card { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.table-card :deep(.el-card__body) { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 12px; }
.table-card :deep(.el-table) { flex: 1; }
.pagination-bar { margin-top: 10px; display: flex; justify-content: flex-end; }
.name-cell { display: flex; align-items: center; }
.zt-tag { margin-left: 6px; }
.nil { color: #c3c9d4; }
.unit { font-style: normal; font-size: 11px; color: var(--text-3); margin-left: 1px; }
.detail-body { display: flex; flex-direction: column; gap: 14px; }
.detail-pics { display: flex; gap: 12px; }
.detail-link { margin-top: 4px; }
/* 价格列：数字统一等宽，右边缘才对得齐；无价用浅灰「—」，一眼能看出是缺数据而不是 0 元 */
.price-text { font-variant-numeric: tabular-nums; }
.comm-note {
  margin-left: 3px;
  font-size: 11px;
  color: var(--text-3);
  white-space: nowrap;
}
.th-with-tip { display: inline-flex; align-items: center; gap: 3px; }
.th-tip { font-size: 12px; color: var(--text-3, #c0c4cc); cursor: help; }
.est {
  margin-left: 6px;
  padding: 0 5px;
  border-radius: 3px;
  background: #f4f6fa;
  color: #909399;
  font-size: 11px;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  padding: 7px 12px;
  border-radius: 8px;
  background: var(--brand-soft);
  border: 1px solid #dbe6ff;
}
.batch-count { font-size: 12.5px; color: var(--text-2); }
.batch-split { color: var(--text-3); font-size: 12px; }
.batch-actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }
</style>
