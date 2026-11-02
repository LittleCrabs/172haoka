<template>
  <div class="fill">
    <el-card shadow="never" class="filter-card">
      <div class="filter-bar">
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
        <div class="spacer"></div>
        <el-button type="primary" :icon="Search" :loading="loading" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table :data="rows" v-loading="loading" stripe height="100%">
        <el-table-column prop="product_name" label="商品名" min-width="300">
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.product_name }}</span>
              <el-tag v-if="row.zhutui" size="small" type="danger" style="margin-left:6px">主推</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="operator" label="运营商" width="84" />
        <el-table-column label="带宽" width="80">
          <template #default="{ row }">{{ row.speed ? row.speed + 'M' : '—' }}</template>
        </el-table-column>
        <el-table-column prop="area" label="地区" width="96" />
        <el-table-column label="价格" width="110">
          <template #default="{ row }">{{ row.price_read || '—' }}</template>
        </el-table-column>
        <el-table-column label="佣金" width="120">
          <template #default="{ row }">{{ row.s_price_read || '—' }}</template>
        </el-table-column>
        <el-table-column label="上架状态" width="92">
          <template #default="{ row }">
            <el-tag size="small" :type="row.flag ? 'success' : 'info'">
              {{ row.flag ? '已上架' : '未上架' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
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
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          :total="pagination.total"
          @change="search"
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
          <el-descriptions-item label="价格">{{ current.price_read || '—' }}</el-descriptions-item>
          <el-descriptions-item label="佣金">{{ current.s_price_read || '—' }}</el-descriptions-item>
          <el-descriptions-item label="佣金类型">{{ current.commission_type || '—' }}</el-descriptions-item>
          <el-descriptions-item label="上架状态">
            <el-tag size="small" :type="current.flag ? 'success' : 'info'">
              {{ current.flag ? '已上架' : '未上架' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="下级状态">
            <el-tag size="small" :type="current.low_flag ? 'success' : 'info'">
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
import { ref, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

defineOptions({ name: 'KuanproView' })

const loading = ref(false)
const rows = ref([])
const facets = ref({ operators: [], areas: [], speeds: [] })
const detailVisible = ref(false)
const current = ref(null)

// 默认看「未上架」内容（选品广场 = 没上架的可选目录）
const filters = ref({ q: '', operator: '', area: '', speed: null, flag: '0', zhutui: null, price_min: null, price_max: null })
const pagination = ref({ page: 1, page_size: 50, total: 0 })

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
    console.error(e)
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.value = { q: '', operator: '', area: '', speed: null, flag: '0', zhutui: null, price_min: null, price_max: null }
  pagination.value.page = 1
  search()
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

onMounted(() => {
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
.filter-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.filter-bar .kw { width: 260px; }
.filter-bar .sel { width: 120px; }
.price-range { display: flex; align-items: center; gap: 4px; }
.price-range :deep(.el-input-number) { width: 96px; }
.tilde { color: #909399; }
.spacer { flex: 1; }
.table-card { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.table-card :deep(.el-card__body) { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 12px; }
.table-card :deep(.el-table) { flex: 1; }
.pagination-bar { margin-top: 10px; display: flex; justify-content: flex-end; }
.name-cell { display: flex; align-items: center; }
.detail-body { display: flex; flex-direction: column; gap: 14px; }
.detail-pics { display: flex; gap: 12px; }
.detail-link { margin-top: 4px; }
</style>
