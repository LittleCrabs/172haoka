<template>
  <!-- 统一空态：原来各页面是「暂无」「暂无命中记录」「暂无输出」三个字灰字，
       有的连边距都没给，看着像加载失败。现在一律是「图标 + 一句说明 + 一个动作」。 -->
  <div class="empty" :class="{ compact }">
    <div class="empty-ico">
      <el-icon><component :is="icon" /></el-icon>
    </div>
    <div class="empty-title">{{ title }}</div>
    <div v-if="desc" class="empty-desc">{{ desc }}</div>
    <div v-if="$slots.action" class="empty-action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Box, Search, Document, ChatLineSquare } from '@element-plus/icons-vue'

const props = defineProps({
  // table 表格无数据 / search 搜索无结果 / doc 空文档 / chat 空对话
  type: { type: String, default: 'table' },
  title: { type: String, default: '暂无数据' },
  desc: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})

const ICONS = { table: Box, search: Search, doc: Document, chat: ChatLineSquare }
const icon = computed(() => ICONS[props.type] || Box)
</script>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 48px 20px;
  color: var(--text-3);
}
.empty.compact { padding: 24px 16px; }

.empty-ico {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: #f4f6fa;
  color: #b6bdca;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  margin-bottom: 2px;
}
.empty-title { font-size: 13.5px; color: var(--text-2); font-weight: 500; }
.empty-desc {
  font-size: 12.5px;
  color: var(--text-3);
  line-height: 1.6;
  max-width: 420px;
  text-align: center;
}
.empty-action { margin-top: 6px; }
</style>
