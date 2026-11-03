<template>
  <div class="fill">
    <el-card shadow="never" class="filter-card toolbar-card">
      <div class="filter-bar">
        <el-select v-model="filters.category" placeholder="品类" clearable class="sel" @change="reload">
          <el-option label="全部品类" :value="null" />
          <el-option label="手机卡" value="手机卡" />
          <el-option label="宽带" value="宽带" />
          <el-option label="靓号" value="靓号" />
        </el-select>
        <el-input
          v-model="filters.q"
          class="kw"
          placeholder="搜索商品名 / 字段"
          :prefix-icon="Search"
          clearable
          @input="debouncedSearch"
          @keyup.enter="reload"
        />
        <div class="spacer"></div>
        <el-switch
          v-model="collapseBatch"
          active-text="合并批量变更"
          size="small"
          @change="onCollapseToggle"
        />
        <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
      </div>
      <div class="hint">
        记录每次同步改变了哪些商品的哪些字段（旧值 → 新值）。
        <template v-if="collapseBatch">
          同一次同步里「同字段、同旧值、同新值」超过 5 条的批量修正会合并成一行，
          点右侧「展开」看具体商品——否则一次批量纠正就能刷满几十页，把真正在意的变更埋掉。
        </template>
        <template v-else>当前是逐条明细视图，一次批量修正会产生几十上百行。</template>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table
        :data="rows"
        v-loading="loading"
        stripe
        height="100%"
        :row-class-name="rowClass"
      >
        <el-table-column label="变更时间" width="168">
          <template #default="{ row }">
            <span class="ts">{{ shortTime(row.changed_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="商品名" min-width="230">
          <template #default="{ row }">
            <div v-if="row.kind === 'summary'" class="sum-cell">
              <el-tag size="small" type="primary" effect="plain">{{ row.count }} 个商品</el-tag>
              <span class="sum-samples" :title="(row.samples || []).join('、')">
                {{ (row.samples || []).join('、') }}{{ row.count > (row.samples || []).length ? ' 等' : '' }}
              </span>
            </div>
            <span v-else class="name-text" :title="row.product_name || ''">
              {{ row.product_name || ('商品#' + row.product_id) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="品类" width="86">
          <template #default="{ row }">
            <!-- 品类是纯分类信息，一律灰色描边；橙色留给真正要人处理的状态 -->
            <el-tag size="small" type="info" effect="plain" v-if="row.category">
              {{ row.category }}
            </el-tag>
            <span v-else class="nil">—</span>
          </template>
        </el-table-column>
        <el-table-column label="字段" width="122">
          <template #default="{ row }">
            <span>{{ fieldLabel(row.field) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变更（旧 → 新）" min-width="330">
          <template #default="{ row }">
            <div class="diff">
              <span class="val old" :class="{ nil: isEmpty(row.old_value) }" :title="fullText(row.field, row.old_value)">
                {{ fmt(row.field, row.old_value) }}
              </span>
              <span class="arrow">→</span>
              <span class="val new" :class="{ nil: isEmpty(row.new_value) }" :title="fullText(row.field, row.new_value)">
                {{ fmt(row.field, row.new_value) }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="104" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.kind === 'summary'"
              size="small"
              text
              type="primary"
              @click="openExpand(row)"
            >
              展开
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            type="table"
            :title="filters.q || filters.category ? '没有匹配的变更' : '还没有变更记录'"
            :desc="filters.q || filters.category
              ? '换个关键词，或把品类切到「全部品类」'
              : '每次同步会比对字段差异，只有真正变化的字段才会记在这里'"
          >
            <template #action>
              <el-button v-if="filters.q || filters.category" size="small" @click="resetFilters">
                清空筛选
              </el-button>
              <el-button v-else size="small" type="primary" @click="$router.push('/settings')">
                去同步一次
              </el-button>
            </template>
          </EmptyState>
        </template>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[50, 100, 200]"
          layout="total, sizes, prev, pager, next"
          :total="pagination.total"
          @change="load"
        />
      </div>
    </el-card>

    <!-- 批量变更明细：摘要行只能说明「多少条」，具体是哪些商品得单独查 -->
    <el-dialog
      v-model="expandVisible"
      :title="expandTitle"
      width="860px"
      destroy-on-close
      @opened="relayoutExpand"
    >
      <div class="expand-hint">
        {{ expandRows.length }} 个商品在此次同步中被同时改成<b class="new">{{ fmt(expandField, expandNew) }}</b>（原值 <span class="old">{{ fmt(expandField, expandOld) }}</span>）。
        <span v-if="expandRows.length < expandTotal">仅显示前 {{ expandRows.length }} 条，共 {{ expandTotal }} 条。</span>
      </div>
      <el-table
        ref="expandTableRef"
        :data="expandRows"
        v-loading="expandLoading"
        size="small"
        height="400"
        stripe
        style="width: 100%"
      >
        <el-table-column label="商品名" min-width="320">
          <template #default="{ row }">{{ row.product_name || ('商品#' + row.product_id) }}</template>
        </el-table-column>
        <el-table-column label="品类" width="86">
          <template #default="{ row }">{{ row.category || '—' }}</template>
        </el-table-column>
        <el-table-column label="当前状态" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="row.on_sale ? 'success' : 'info'" effect="light">
              {{ row.on_sale ? '在售' : '下架' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="expandVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'

defineOptions({ name: 'ChangesView' })

const loading = ref(false)
const rows = ref([])
const filters = reactive({ category: null, q: '' })
const pagination = reactive({ page: 1, page_size: 100, total: 0 })

// 筛选条件记在本机，切页面回来不用重选
const FILTER_KEY = 'changes.filters'
try {
  const saved = JSON.parse(localStorage.getItem(FILTER_KEY) || '{}')
  if (saved.category !== undefined) filters.category = saved.category
  if (saved.q) filters.q = saved.q
} catch { /* 坏数据忽略 */ }

// 批量同质变更默认合并。这个页面的用途是「看出业务发生了什么」，
// 不是「审计每一条字段」，一次批量修正刷满几十页等于没日志。
const collapseBatch = ref(localStorage.getItem('changes.collapse') !== '0')

const FIELD_LABELS = {
  product_name: '商品名', category: '品类', monthly_fee: '月租(元)', data_gb: '流量(GB)',
  voice_min: '通话(分钟)', commission: '佣金', commission_type: '佣金类型',
  commission_read: '佣金文案', on_sale: '上架状态', area: '地区', area_read: '地区详情',
  disable_area: '禁售地区', age_min: '最小年龄', age_max: '最大年龄', rule: '结算规则',
  remark: '备注', keywords: '关键词', is_zhutui: '主推', operator: '运营商',
  main_pic: '主图', sn: 'SN', create_time: '添加时间', product_str: '商品串', third_api: '第三方API',
}

function fieldLabel(f) {
  return FIELD_LABELS[f] || f
}

const ENUM_FIELDS = {
  on_sale: { 1: '在售', 0: '下架', true: '在售', false: '下架' },
  is_zhutui: { 1: '是', 0: '否', true: '是', false: '否' },
}

function isEmpty(v) {
  return v === null || v === undefined || v === ''
}

function fullText(field, v) {
  if (isEmpty(v)) return ''
  const e = ENUM_FIELDS[field]
  if (e && e[v] !== undefined) return String(e[v])
  return String(v)
}

// 单元格靠 CSS 截断，这里给完整值，悬停看全文。
// 禁售地区这类字段能写三百多字，硬撑会把整行拉到两屏高。
function fmt(field, v) {
  if (isEmpty(v)) return '—'
  return fullText(field, v)
}

function shortTime(t) {
  if (!t) return '—'
  // 同一批次的变更时间戳全一样，省掉年份让列更紧凑
  return t.length >= 16 ? t.slice(5, 16) : t
}

function rowClass({ row }) {
  return row.kind === 'summary' ? 'summary-row' : ''
}

let timer = null
function debouncedSearch() {
  clearTimeout(timer)
  timer = setTimeout(reload, 350)
}

function reload() {
  pagination.page = 1
  try {
    localStorage.setItem(FILTER_KEY, JSON.stringify({ category: filters.category, q: filters.q }))
  } catch { /* 隐私模式忽略 */ }
  load()
}

function resetFilters() {
  filters.category = null
  filters.q = ''
  reload()
}

function onCollapseToggle() {
  localStorage.setItem('changes.collapse', collapseBatch.value ? '1' : '0')
  reload()
}

async function load() {
  loading.value = true
  try {
    const res = await api.changes({
      category: filters.category || undefined,
      q: filters.q || undefined,
      page: pagination.page,
      limit: pagination.page_size,
      collapse: collapseBatch.value ? 1 : 0,
    })
    rows.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {
    ElMessage.error('加载失败：' + e.message)
  } finally {
    loading.value = false
  }
}

// ---- 展开批量明细 ----
const expandVisible = ref(false)
const expandLoading = ref(false)
const expandRows = ref([])
const expandTotal = ref(0)
const expandTitle = ref('')
const expandField = ref('')
const expandOld = ref(null)
const expandNew = ref(null)
const expandTableRef = ref(null)

// el-table 在弹窗里首次渲染时容器宽度还是 0，列宽会算成最小宽度、
// 表格缩在左边一条。等弹窗动画结束重新量一次。
function relayoutExpand() {
  nextTick(() => expandTableRef.value && expandTableRef.value.doLayout())
}

async function openExpand(row) {
  expandField.value = row.field
  expandOld.value = row.old_value
  expandNew.value = row.new_value
  expandTitle.value = `${fieldLabel(row.field)}：${row.count} 个商品同时变更`
  expandRows.value = []
  expandTotal.value = 0
  expandVisible.value = true
  expandLoading.value = true
  try {
    const res = await api.changesExpand({
      batch_id: row.batch_id,
      field: row.field,
      old_value: row.old_value,
      new_value: row.new_value,
    })
    expandRows.value = res.items || []
    expandTotal.value = res.total || 0
  } catch (e) {
    ElMessage.error('展开失败：' + e.message)
  } finally {
    expandLoading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.fill { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.filter-card { flex-shrink: 0; }
.filter-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.filter-bar .kw { width: 280px; }
.filter-bar .sel { width: 130px; }
.spacer { flex: 1; }
.hint { margin-top: 8px; color: var(--text-3, #909399); font-size: 12px; line-height: 1.6; }
.table-card { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.table-card :deep(.el-card__body) { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 12px; }
.table-card :deep(.el-table) { flex: 1; }
.pagination-bar { margin-top: 10px; display: flex; justify-content: flex-end; }

.ts { color: var(--text-2, #606266); font-variant-numeric: tabular-nums; }
.name-text { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nil { color: var(--text-3, #c0c4cc); }

/* 旧值新值各占一半宽度并各自截断，长字段不会把行撑高、也不会把「→」挤到看不见 */
.diff { display: flex; align-items: center; gap: 6px; min-width: 0; }
.diff .val {
  flex: 0 1 47%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.diff .old { color: #c45656; text-decoration: line-through; text-decoration-color: rgba(196, 86, 86, .45); }
.diff .new { color: #2f9e44; font-weight: 600; }
.diff .val.nil { color: var(--text-3, #c0c4cc); text-decoration: none; font-weight: normal; }
.arrow { flex: 0 0 auto; color: var(--text-3, #b1b3b8); }

.sum-cell { display: flex; align-items: center; gap: 8px; min-width: 0; }
.sum-samples {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-3, #909399);
  font-size: 12px;
}

/* 摘要行整行压暗一点，一眼分出「一条变更」和「一批变更」 */
:deep(.summary-row) { background: #fdfaf3 !important; }
:deep(.summary-row:hover > td) { background: #fbf5e9 !important; }

.expand-hint { margin-bottom: 10px; color: var(--text-2, #606266); font-size: 13px; line-height: 1.7; }
.expand-hint .new { color: #2f9e44; }
.expand-hint .old { color: #c45656; text-decoration: line-through; }
</style>
