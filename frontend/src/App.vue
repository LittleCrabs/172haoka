<template>
  <div class="shell">
    <!-- 左侧导航 -->
    <aside class="side" :class="{ collapsed }">
      <div class="brand" @click="$router.push('/ask')">
        <div class="brand-logo">172</div>
        <div v-show="!collapsed" class="brand-text">
          <div class="brand-name">号卡辅助平台</div>
          <div class="brand-sub">172haoka console</div>
        </div>
      </div>

      <nav class="nav">
        <template v-for="g in GROUPS" :key="g.title">
          <div v-show="!collapsed" class="nav-group">{{ g.title }}</div>
          <div v-show="collapsed" class="nav-group-line"></div>
          <router-link
            v-for="it in g.items"
            :key="it.path"
            :to="it.path"
            class="nav-item"
            :class="{ active: isActive(it.path) }"
            :title="collapsed ? it.title : ''"
          >
            <el-icon class="nav-ico"><component :is="it.icon" /></el-icon>
            <span v-show="!collapsed" class="nav-label">{{ it.title }}</span>
            <span v-if="it.badge && !collapsed" class="nav-badge">{{ it.badge }}</span>
          </router-link>
        </template>
      </nav>

      <div class="side-foot">
        <div class="model-state" :class="{ ok: configured }" :title="configured ? '大模型已配置' : '大模型未配置，点击去设置'"
          @click="$router.push('/settings')">
          <span class="dot"></span>
          <span v-show="!collapsed">{{ configured ? '模型已配置' : '模型未配置' }}</span>
        </div>
      </div>
    </aside>

    <!-- 右侧主体 -->
    <div class="body">
      <header class="topbar">
        <el-tooltip :content="collapsed ? '展开菜单' : '收起菜单'" placement="bottom">
          <button class="collapse-btn" @click="toggle">
            <el-icon><component :is="collapsed ? Expand : Fold" /></el-icon>
          </button>
        </el-tooltip>
        <div class="title-wrap">
          <h1 class="page-title">{{ pageTitle }}</h1>
          <p class="page-desc">{{ pageDesc }}</p>
        </div>
        <div class="spacer"></div>
        <!-- 全局搜索入口：以前 topbar 右侧一半是空的，958 个商品只能进页面再筛 -->
        <button class="search-trigger" @click="searchOpen = true" title="全局搜索（Ctrl+K）">
          <el-icon class="search-ico"><Search /></el-icon>
          <span class="search-ph">搜索商品 / 知识库</span>
          <kbd class="search-kbd">Ctrl K</kbd>
        </button>
        <el-tooltip content="后端服务状态" placement="bottom">
          <span class="health" :class="{ ok: online }">
            <span class="dot"></span>{{ online ? '服务正常' : '连接异常' }}
          </span>
        </el-tooltip>
        <el-tooltip content="设置" placement="bottom">
          <el-button :icon="Setting" circle text class="gear" @click="$router.push('/settings')" />
        </el-tooltip>
      </header>

      <!-- 后端断开提示。以前遇到这种情况页面只会静默停止更新，看起来跟卡死一样；
           但常驻一条全宽横幅会把下面的内容整体推下去，连上又弹回来 —— 反而添乱。
           现在做成右上角悬浮通知，只覆盖不挤压，布局一点不动。 -->
      <transition name="toast">
        <div v-if="showOffline" class="offline-toast" role="alert" :style="{ left: collapsed ? 'calc(50% + 32px)' : 'calc(50% + 104px)' }">
          <el-icon class="offline-ico"><WarningFilled /></el-icon>
          <div class="offline-body">
            <div class="offline-title">后端服务未连接</div>
            <div class="offline-text">页面数据不会更新（127.0.0.1:8123）</div>
          </div>
          <button class="offline-retry" @click="ping">立即重试</button>
        </div>
      </transition>

      <main class="main">
        <router-view v-slot="{ Component }">
          <keep-alive :include="['AskView', 'SettingsView', 'ProductsView', 'KuanproView', 'XhsView']">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </main>
      <GlobalSearch v-model="searchOpen" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChatDotRound, Goods, Connection, Promotion, Notebook, Clock,
  Setting, Fold, Expand, WarningFilled, Search,
} from '@element-plus/icons-vue'
import { api, conn } from './api'
import GlobalSearch from './components/GlobalSearch.vue'

const route = useRoute()
const router = useRouter()

const GROUPS = [
  {
    title: '工作台',
    items: [
      { path: '/ask', title: '智能问答', icon: ChatDotRound },
      { path: '/products', title: '商品库', icon: Goods },
      { path: '/kuanpro', title: '宽带选品', icon: Connection },
    ],
  },
  {
    title: '内容运营',
    items: [
      { path: '/xhs', title: '小红书', icon: Promotion },
      { path: '/kb', title: '知识库', icon: Notebook },
    ],
  },
  {
    title: '系统',
    items: [
      { path: '/changes', title: '更新日志', icon: Clock },
      { path: '/settings', title: '设置', icon: Setting },
    ],
  },
]

const collapsed = ref(localStorage.getItem('nav.collapsed') === '1')
const configured = ref(true)

// 全局搜索：Ctrl/Cmd + K 唤起。只认这个组合，不去劫持 "/"——
// 商品库、宽带选品页自己就有搜索框，抢 "/" 会让用户以为自己打不上字。
const searchOpen = ref(false)
function onKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && String(e.key).toLowerCase() === 'k') {
    e.preventDefault()
    searchOpen.value = !searchOpen.value
  }
}
// 连接状态由 api 层统一维护（任何请求失败都会更新它），这里只做展示，
// 不再像以前那样只在页面加载时查一次、之后永远显示"服务正常"。
//
// 但「一次超时」不等于「后端挂了」：跑同步、调大模型、启动小红书机器人时后端本来就忙，
// 偶发一次健康检查超时很正常。以前一次失败就弹横幅，横幅在文档流里、
// 出现消失都把整页内容上下推 30 多像素，看着就是「页面一直在跳」。
// 现在要求连续两次失败才认账，且提示改成悬浮卡片，只覆盖不挤压。
const stableOk = computed(() => conn.ok && conn.failures < 2)
const online = computed(() => stableOk.value)
const showOffline = computed(() => !stableOk.value)

function toggle() {
  collapsed.value = !collapsed.value
  localStorage.setItem('nav.collapsed', collapsed.value ? '1' : '0')
}

function isActive(path) {
  return route.path === path || route.path.startsWith(path + '/')
}

const pageTitle = computed(() => route.meta?.title || '')
const pageDesc = computed(() => route.meta?.desc || '')

watch(() => route.path, () => {
  document.title = (route.meta?.title ? route.meta.title + ' · ' : '') + '172号卡辅助平台'
})

// 定时探活：后端挂掉时几秒内就能发现，而不是等某个操作失败才暴露
let healthTimer = null
async function ping() {
  try {
    await api.health()
  } catch (e) {
    // conn.ok 已在 api 层被置为 false，横幅会自动出现
  }
}

onMounted(async () => {
  document.title = (route.meta?.title ? route.meta.title + ' · ' : '') + '172号卡辅助平台'
  window.addEventListener('keydown', onKeydown)
  try {
    const s = await api.state()
    configured.value = !!s.configured
  } catch (e) {
    configured.value = false
  }
  ping()
  healthTimer = setInterval(ping, 10000)
})

onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer)
  healthTimer = null
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.shell {
  display: flex;
  height: 100%;
  background: var(--bg);
}

/* ---------------- 侧边栏 ---------------- */
.side {
  position: relative;
  flex: 0 0 208px;
  width: 208px;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-right: 1px solid var(--line);
  transition: flex-basis .18s ease, width .18s ease;
}
.side.collapsed { flex-basis: 64px; width: 64px; }

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 60px;
  padding: 0 16px;
  cursor: pointer;
  flex: 0 0 auto;
}
.collapsed .brand { padding: 0; justify-content: center; }
.brand-logo {
  flex: 0 0 auto;
  width: 30px; height: 30px;
  border-radius: 8px;
  background: linear-gradient(135deg, #3b7bff, #2453d8);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: -.3px;
  display: flex; align-items: center; justify-content: center;
}
.brand-name { font-size: 14px; font-weight: 600; color: var(--text-1); line-height: 1.25; }
.brand-sub { font-size: 11px; color: var(--text-3); letter-spacing: .3px; }

.nav {
  flex: 1;
  overflow-y: auto;
  padding: 4px 10px 12px;
}
.collapsed .nav { padding: 4px 8px 12px; }

.nav-group {
  padding: 14px 8px 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .6px;
  color: var(--text-3);
}
.nav-group-line {
  height: 1px;
  margin: 10px 6px;
  background: var(--line);
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 38px;
  padding: 0 10px;
  margin-bottom: 2px;
  border-radius: 8px;
  color: var(--text-2);
  text-decoration: none;
  font-size: 13.5px;
  transition: background .15s, color .15s;
}
.collapsed .nav-item { justify-content: center; padding: 0; }
.nav-item:hover { background: #f4f6fa; color: var(--text-1); }
.nav-item.active {
  background: var(--brand-soft);
  color: var(--brand);
  font-weight: 600;
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0; top: 9px; bottom: 9px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--brand);
}
.nav-ico { font-size: 17px; flex: 0 0 auto; }
.nav-label { overflow: hidden; white-space: nowrap; }
.nav-badge {
  margin-left: auto;
  font-size: 11px;
  padding: 0 6px;
  border-radius: 8px;
  background: #f0f2f6;
  color: var(--text-3);
}

.side-foot {
  flex: 0 0 auto;
  padding: 10px 12px 12px;
  border-top: 1px solid var(--line);
}
.model-state {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-3);
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 6px;
  white-space: nowrap;
  overflow: hidden;
}
.collapsed .model-state { justify-content: center; padding: 6px 0; }
.model-state:hover { background: #f4f6fa; }
.model-state .dot { width: 6px; height: 6px; border-radius: 50%; background: #f0a020; flex: 0 0 auto; }
.model-state.ok .dot { background: #2fb344; }

.collapse-btn {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  color: var(--text-2);
  font-size: 15px;
  cursor: pointer;
  padding: 0;
  transition: all .15s;
}
.collapse-btn:hover {
  color: var(--brand);
  border-color: #c8d8ff;
  background: var(--brand-soft);
}

/* ---------------- 右侧 ---------------- */
.body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 60px;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid var(--line);
}
.title-wrap { min-width: 0; }
.page-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
  line-height: 1.3;
}
.page-desc {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.spacer { flex: 1; }

/* ---------------- 全局搜索入口 ---------------- */
.search-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 248px;
  height: 30px;
  padding: 0 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fafbfc;
  color: var(--text-3);
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color .15s, background .15s;
}
.search-trigger:hover { border-color: #c8d8ff; background: #fff; }
.search-ico { font-size: 14px; }
.search-ph { flex: 1; text-align: left; }
.search-kbd {
  font-family: inherit;
  font-size: 10.5px;
  color: var(--text-3);
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 1px 5px;
}

.health {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-3);
  padding: 3px 9px;
  border-radius: 20px;
  background: #f6f7f9;
}
.health .dot { width: 6px; height: 6px; border-radius: 50%; background: #f0a020; }
.health.ok .dot { background: #2fb344; box-shadow: 0 0 0 3px rgba(47, 179, 68, .12); }
.gear { color: var(--text-2); }

/* ---------------- 断连提示（悬浮，不占文档流） ---------------- */
/* 放底部居中：顶部右侧会挡住「启动一轮」这类主按钮，底部只是临时通知的常规位置 */
.offline-toast {
  position: fixed;
  bottom: 22px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2100;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: 480px;
  padding: 10px 14px;
  background: #fff8e6;
  border: 1px solid #f5e0b0;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(24, 32, 48, .16);
  color: #8a5b00;
  transition: left .18s ease;   /* 侧栏收起/展开时跟着平滑移动 */
}
.offline-ico { font-size: 18px; color: #e8912d; flex: 0 0 auto; }
.offline-body { min-width: 0; }
.offline-title { font-size: 13px; font-weight: 600; line-height: 1.4; }
.offline-text { font-size: 12px; color: #9a6a17; line-height: 1.4; margin-top: 1px; }
.offline-retry {
  flex: 0 0 auto;
  border: 1px solid #e8c88a;
  background: #fff;
  color: #8a5b00;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background .15s;
}
.offline-retry:hover { background: #fff3d9; }

.toast-enter-active,
.toast-leave-active { transition: opacity .18s ease, transform .18s ease; }
.toast-enter-from,
.toast-leave-to { opacity: 0; transform: translate(-50%, 8px); }

.main {
  flex: 1;
  min-height: 0;
  padding: 16px 20px 20px;
  overflow: auto;
}
</style>
