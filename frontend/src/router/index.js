import { createRouter, createWebHashHistory } from 'vue-router'
import AskView from '../views/AskView.vue'
import ProductsView from '../views/ProductsView.vue'
import KuanproView from '../views/KuanproView.vue'
import KnowledgeView from '../views/KnowledgeView.vue'
import ChangesView from '../views/ChangesView.vue'
import SettingsView from '../views/SettingsView.vue'

// 用 hash 路由：既能在 Vite dev 下用，也能被后端 FastAPI 静态托管直接打开（无需服务端 rewrite）。
const routes = [
  { path: '/', redirect: '/ask' },
  { path: '/ask', name: 'ask', component: AskView, meta: { title: '智能问答' } },
  { path: '/products', name: 'products', component: ProductsView, meta: { title: '商品库' } },
  { path: '/kuanpro', name: 'kuanpro', component: KuanproView, meta: { title: '宽带选品' } },
  { path: '/kb', name: 'kb', component: KnowledgeView, meta: { title: '知识库' } },
  { path: '/changes', name: 'changes', component: ChangesView, meta: { title: '更新日志' } },
  { path: '/settings', name: 'settings', component: SettingsView, meta: { title: '设置' } },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
