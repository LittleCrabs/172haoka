<template>
  <el-container class="fill">
    <el-header class="app-header" height="56px">
      <div class="brand">172号卡辅助平台</div>
      <el-menu
        :default-active="activeIndex"
        mode="horizontal"
        :router="true"
        :ellipsis="false"
        class="nav"
        background-color="transparent"
        text-color="#303133"
        active-text-color="#409eff"
      >
        <el-menu-item index="/ask">智能问答</el-menu-item>
        <el-menu-item index="/products">商品库</el-menu-item>
        <el-menu-item index="/kuanpro">宽带选品</el-menu-item>
        <el-menu-item index="/kb">知识库</el-menu-item>
        <el-menu-item index="/changes">更新日志</el-menu-item>
      </el-menu>
      <div class="spacer"></div>
      <el-tooltip :content="configured ? '设置' : '大模型未配置，点此设置'" placement="bottom">
        <el-badge :is-dot="!configured" :offset="[-2, 2]">
          <el-button :icon="Setting" circle @click="goSettings" />
        </el-badge>
      </el-tooltip>
    </el-header>
    <el-main class="app-main">
      <router-view v-slot="{ Component }">
        <keep-alive :include="['AskView']">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Setting } from '@element-plus/icons-vue'
import { api } from './api'

const route = useRoute()
const router = useRouter()
const configured = ref(true)

const activeIndex = computed(() => route.path)

function goSettings() {
  router.push('/settings')
}

onMounted(async () => {
  try {
    const s = await api.state()
    configured.value = !!s.configured
  } catch (e) {
    configured.value = false
  }
})
</script>

<style>
.app-header {
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  padding: 0 16px;
}
.brand {
  font-size: 17px;
  font-weight: 600;
  color: #303133;
  margin-right: 24px;
  white-space: nowrap;
}
.nav {
  border-bottom: none !important;
  flex: 0 0 auto;
}
.app-main {
  padding: 16px;
  overflow: auto;
}
</style>
