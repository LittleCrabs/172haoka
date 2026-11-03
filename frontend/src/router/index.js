import { createRouter, createWebHashHistory } from 'vue-router'
import AskView from '../views/AskView.vue'
import ProductsView from '../views/ProductsView.vue'
import KuanproView from '../views/KuanproView.vue'
import KnowledgeView from '../views/KnowledgeView.vue'
import ChangesView from '../views/ChangesView.vue'
import XhsView from '../views/XhsView.vue'
import SettingsView from '../views/SettingsView.vue'

// 用 hash 路由：既能在 Vite dev 下用，也能被后端 FastAPI 静态托管直接打开（无需服务端 rewrite）。
// meta.desc 会显示在顶部页头，说明这个页面是干什么的。
const routes = [
  { path: '/', redirect: '/ask' },
  {
    path: '/ask', name: 'ask', component: AskView,
    meta: { title: '智能问答', desc: '检索商品库与知识库，生成带出处的答案' },
  },
  {
    path: '/products', name: 'products', component: ProductsView,
    meta: { title: '商品库', desc: '手机卡商品，支持运营商 / 地区 / 资费组合筛选' },
  },
  {
    path: '/kuanpro', name: 'kuanpro', component: KuanproView,
    meta: { title: '宽带选品', desc: '宽带商品，按地区、带宽与上架状态筛选' },
  },
  {
    path: '/xhs', name: 'xhs', component: XhsView,
    meta: { title: '小红书', desc: '浏览信息流、判定目标人群、生成并发送回复' },
  },
  {
    path: '/kb', name: 'kb', component: KnowledgeView,
    meta: { title: '知识库', desc: '知识文档与检索分块，可重建向量索引' },
  },
  {
    path: '/changes', name: 'changes', component: ChangesView,
    meta: { title: '更新日志', desc: '同步过程中商品字段的变更记录' },
  },
  {
    path: '/settings', name: 'settings', component: SettingsView,
    meta: { title: '设置', desc: '模型服务、数据源账号与同步配置' },
  },
  // 兜底：hash 路由匹配不到任何页面时（例如浏览器「返回上一级」退到了历史里的旧地址、
  // 或手改了 # 后面的内容），直接回智能问答。没有这条时 router-view 会渲染空白，
  // 整个应用只剩侧边栏，表现为「页面卡住」。
  { path: '/:pathMatch(.*)*', redirect: '/ask' },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
