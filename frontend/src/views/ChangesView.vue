<template>
  <div class="fill">
    <el-card shadow="never" class="filter-card">
      <div class="filter-bar">
        <el-select v-model="filters.category" placeholder="品类" clearable class="sel" @change="load">
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
          @keyup.enter="load"
        />
        <div class="spacer"></div>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
      <div class="hint">记录每次同步改变了哪些商品的哪些字段（旧值 → 新值）。变更从本功能上线后开始累积。</div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table :data="rows" v-loading="loading" stripe height="100%">
        <el-table-column label="变更时间" width="170">
          <template #default="{ row }">{{ row.changed_at || '—' }}</template>
        </el-table-column>
        <el-table-column prop="product_name" label="商品名" min-width="280">
          <template #default="{ row }">
            <span>{{ row.product_name || ('商品#' + row.product_id) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="品类" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.category === '宽带' ? 'warning' : 'info'" v-if="row.category">
              {{ row.category }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="字段" width="120">
          <template #default="{ row }">{{ fieldLabel(row.field) }}</template>
        </el-table-column>
        <el-table-column label="变更（旧 → 新）" min-width="360">
          <template #default="{ row }">
            <span class="old">{{ fmt(row.field, row.old_value) }}</span>
            <span class="arrow"> → </span>
            <span class="new">{{ fmt(row.field, row.new_value) }}</span>
          </template>
        </el-table-column>
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import { api } from '../api'

defineOptions({ name: 'ChangesView' })

const loading = ref(false)
const rows = ref([])
const filters = reactive({ category: null, q: '' })
const pagination = reactive({ page: 1, page_size: 100, total: 0 })

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

function fmt(field, v) {
  if (v === null || v === undefined || v === '') return '—'
  if (field === 'on_sale') return v === 1 || v === '1' ? '在售' : '下架'
  if (field === 'is_zhutui') return v === 1 || v === '1' ? '是' : '否'
  return String(v)
}

let timer = null
function debouncedSearch() {
  clearTimeout(timer)
  timer = setTimeout(load, 350)
}

async function load() {
  loading.value = true
  try {
    const res = await api.changes({
      category: filters.category || undefined,
      q: filters.q || undefined,
      page: pagination.page,
      limit: pagination.page_size,
    })
    rows.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
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
.hint { margin-top: 8px; color: #909399; font-size: 12px; }
.table-card { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.table-card :deep(.el-card__body) { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 12px; }
.table-card :deep(.el-table) { flex: 1; }
.pagination-bar { margin-top: 10px; display: flex; justify-content: flex-end; }
.old { color: #f56c6c; text-decoration: line-through; }
.arrow { color: #909399; }
.new { color: #67c23a; font-weight: 600; }
</style>
