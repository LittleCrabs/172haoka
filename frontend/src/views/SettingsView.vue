<template>
  <div class="settings">
    <el-alert type="info" :closable="false" style="margin-bottom: 12px"
      title="本平台为单机自用，配置仅保存在本机 config.json。大模型用于问答，向量模型用于知识库检索（不配也能用关键词检索）。" />

    <el-row :gutter="16">
      <!-- 大模型（对话/问答） -->
      <el-col :span="12">
        <el-card shadow="never" header="大模型（问答/对话）">
          <el-form label-width="92px" label-position="right">
            <el-form-item label="服务商预设">
              <el-select v-model="llmPreset" placeholder="手动填写" clearable style="width: 100%" @change="applyLlmPreset">
                <el-option v-for="p in presets.llm" :key="p.name" :label="p.name" :value="p.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="Base URL">
              <el-input v-model="llm.base_url" placeholder="https://.../v1" />
            </el-form-item>
            <el-form-item label="模型名">
              <el-input v-model="llm.model" placeholder="如 glm-5.3-flash" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="llm.api_key" type="password" show-password
                placeholder="已配置则留空不修改" />
            </el-form-item>
            <el-form-item label="温度">
              <el-input-number v-model="llm.temperature" :min="0" :max="2" :step="0.1" :precision="1" />
            </el-form-item>
            <el-form-item label="最大输出">
              <el-input-number v-model="llm.max_tokens" :min="200" :max="4000" :step="100" />
            </el-form-item>
            <el-form-item label="扩展参数">
              <el-input v-model="llm.extra" type="textarea" :rows="3"
                placeholder='JSON，如 {"thinking":{"type":"disabled"}}' />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingLlm" @click="saveLlm">保存</el-button>
              <el-button :loading="testing" @click="testLlm">测试连接</el-button>
            </el-form-item>
            <el-form-item v-if="testMsg">
              <el-alert :type="testOk ? 'success' : 'error'" :closable="false" :title="testMsg" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 向量模型（embedding） -->
      <el-col :span="12">
        <el-card shadow="never" header="向量模型（知识库检索）">
          <el-form label-width="92px" label-position="right">
            <el-form-item label="服务商预设">
              <el-select v-model="embedPreset" placeholder="手动填写" clearable style="width: 100%" @change="applyEmbedPreset">
                <el-option v-for="p in presets.embed" :key="p.name" :label="p.name" :value="p.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="Base URL">
              <el-input v-model="embed.base_url" placeholder="https://.../v1" />
            </el-form-item>
            <el-form-item label="模型名">
              <el-input v-model="embed.model" placeholder="如 BAAI/bge-m3" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="embed.api_key" type="password" show-password
                placeholder="已配置则留空不修改" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingEmbed" @click="saveEmbed">保存</el-button>
              <span class="muted">不配向量模型也能用关键词检索</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- 172号卡后台账号 + 登录 -->
    <el-card shadow="never" header="172号卡后台账号（用于同步商品 / 取 H5 域名）" style="margin-top: 16px">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form label-width="92px" label-position="right">
            <el-form-item label="后台网址">
              <el-input v-model="haoka.site" placeholder="https://haoka.lot-ml.com/" />
            </el-form-item>
            <el-form-item label="API 域名">
              <el-input v-model="haoka.api" placeholder="https://haokaapi.lot-ml.com/" />
            </el-form-item>
            <el-form-item label="账号">
              <el-input v-model="haoka.username" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="haoka.password" type="password" show-password placeholder="已配置则留空不修改" />
            </el-form-item>
            <el-form-item label="网络代理">
              <el-input v-model="haoka.proxy" placeholder="http://127.0.0.1:10808（留空=用系统默认代理）" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingHaoka" @click="saveHaoka">保存后台账号</el-button>
            </el-form-item>
          </el-form>
        </el-col>
        <el-col :span="12">
          <div class="login-box">
            <div class="muted">登录以获取后台 token（7 天有效，过期需重新登录）：</div>
            <div v-if="captchaImg" class="captcha-row">
              <img :src="captchaImg" class="captcha-img" alt="验证码" />
              <el-button text :icon="Refresh" @click="getCaptcha">换一张</el-button>
            </div>
            <el-input v-model="captchaCode" placeholder="输入图形验证码" style="max-width: 220px; margin-top: 8px" />
            <div style="margin-top: 10px">
              <el-button :loading="gettingCaptcha" @click="getCaptcha">获取验证码</el-button>
              <el-button type="primary" :loading="logging" @click="doLogin">登录</el-button>
            </div>
            <el-alert v-if="loginMsg" :type="loginOk ? 'success' : 'error'" :closable="false"
              :title="loginMsg" style="margin-top: 10px" />
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 商品同步 -->
    <el-card shadow="never" header="商品同步" style="margin-top: 16px">
      <!-- 一键同步全部：一个总进度（手机卡 + 宽带） -->
      <div class="sync-all">
        <el-button type="success" size="large" :loading="syncingAll"
          :disabled="syncingAll || syncingPhone || syncingKuan" @click="syncAll">
          {{ syncingAll ? '全部同步中...' : '一键同步全部（手机卡 + 宽带）' }}
        </el-button>
        <div v-if="allResult" class="sync-result">
          合计 {{ allResult.total }} 条，新增 {{ allResult.inserted }}，更新 {{ allResult.updated }}，下架 {{ allResult.offsale }}
        </div>
        <el-alert v-if="allError" type="error" :closable="false" :title="allError"
          style="margin-top: 8px; max-width: 480px" />
      </div>
      <el-divider content-position="left">或分别同步</el-divider>
      <el-row :gutter="24">
        <el-col :span="12">
          <div class="sync-box">
            <div class="sync-title">手机卡商品同步</div>
            <div class="sync-desc">从后台 api/Products/Query 拉取手机卡商品（约 150 条）</div>
            <el-button type="primary" :loading="syncingPhone" :disabled="syncingPhone" @click="syncPhone">
              {{ syncingPhone ? '同步中...' : '一键同步手机卡' }}
            </el-button>
            <div v-if="syncPhoneResult" class="sync-result">
              共 {{ syncPhoneResult.total }} 条，新增 {{ syncPhoneResult.inserted }}，更新 {{ syncPhoneResult.updated }}，下架 {{ syncPhoneResult.offsale }}
            </div>
            <el-alert v-if="syncPhoneError" type="error" :closable="false" :title="syncPhoneError" style="margin-top: 8px" />
          </div>
        </el-col>
        <el-col :span="12">
          <div class="sync-box">
            <div class="sync-title">宽带选品同步</div>
            <div class="sync-desc">从后台 api/ProKuan/GroundProQuery 拉取宽带商品（约 865 条）</div>
            <el-button type="primary" :loading="syncingKuan" :disabled="syncingKuan" @click="syncKuan">
              {{ syncingKuan ? '同步中...' : '一键同步宽带选品' }}
            </el-button>
            <div v-if="syncKuanResult" class="sync-result">
              共 {{ syncKuanResult.total }} 条，新增 {{ syncKuanResult.inserted }}，更新 {{ syncKuanResult.updated }}，下架 {{ syncKuanResult.offsale }}
            </div>
            <el-alert v-if="syncKuanError" type="error" :closable="false" :title="syncKuanError" style="margin-top: 8px" />
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { api } from '../api'

const presets = reactive({ llm: [], embed: [] })
const llmPreset = ref('')
const embedPreset = ref('')
const llm = reactive({ base_url: '', model: '', api_key: '', temperature: 0.3, max_tokens: 1200, extra: '' })
const embed = reactive({ base_url: '', model: '', api_key: '' })
const haoka = reactive({ site: '', api: '', username: '', password: '', proxy: '' })

const savingLlm = ref(false)
const savingEmbed = ref(false)
const savingHaoka = ref(false)
const testing = ref(false)
const testOk = ref(false)
const testMsg = ref('')

const gettingCaptcha = ref(false)
const logging = ref(false)
const captchaImg = ref('')
const captchaCode = ref('')
const loginMsg = ref('')
const loginOk = ref(false)

// 同步状态
const syncingPhone = ref(false)
const syncPhoneResult = ref(null)
const syncPhoneError = ref('')
const syncingKuan = ref(false)
const syncKuanResult = ref(null)
const syncKuanError = ref('')

// 一键同步全部（手机卡 + 宽带）
const syncingAll = ref(false)
const allResult = ref(null)
const allError = ref('')

function applyLlmPreset(name) {
  const p = presets.llm.find((x) => x.name === name)
  if (p) { llm.base_url = p.base_url || llm.base_url; llm.model = p.model || llm.model }
}
function applyEmbedPreset(name) {
  const p = presets.embed.find((x) => x.name === name)
  if (p) { embed.base_url = p.base_url || embed.base_url; embed.model = p.model || embed.model }
}

async function load() {
  try {
    const res = await api.settings()
    presets.llm = res.presets?.llm || []
    presets.embed = res.presets?.embed || []
    const c = res.config || {}
    const L = c.llm || {}
    llm.base_url = L.base_url || ''
    llm.model = L.model || ''
    llm.api_key = '' // 已配置则留空，避免回传明文
    llm.temperature = L.temperature ?? 0.3
    llm.max_tokens = L.max_tokens ?? 1200
    llm.extra = L.extra ? JSON.stringify(L.extra, null, 2) : ''
    const E = c.embed || {}
    embed.base_url = E.base_url || ''
    embed.model = E.model || ''
    embed.api_key = ''
    haoka.site = c.site || ''
    haoka.api = c.api || ''
    haoka.username = c.username || ''
    haoka.password = ''
    haoka.proxy = c.proxy || ''
  } catch (e) {
    ElMessage.error('加载设置失败：' + e.message)
  }
}

async function saveLlm() {
  savingLlm.value = true
  try {
    const body = { llm: { ...llm } }
    if (!body.llm.api_key) delete body.llm.api_key
    if (body.llm.extra) { try { body.llm.extra = JSON.parse(body.llm.extra) } catch { throw new Error('扩展参数不是合法 JSON') } }
    else delete body.llm.extra
    await api.saveSettings(body)
    ElMessage.success('大模型配置已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + e.message)
  } finally {
    savingLlm.value = false
  }
}

async function saveEmbed() {
  savingEmbed.value = true
  try {
    const body = { embed: { ...embed } }
    if (!body.embed.api_key) delete body.embed.api_key
    await api.saveSettings(body)
    ElMessage.success('向量模型配置已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + e.message)
  } finally {
    savingEmbed.value = false
  }
}

async function saveHaoka() {
  savingHaoka.value = true
  try {
    const body = {
      username: haoka.username,
      password: haoka.password,
      site: haoka.site,
      api: haoka.api,
      proxy: haoka.proxy,
    }
    if (!body.password) delete body.password
    await api.saveSettings(body)
    ElMessage.success('后台账号已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + e.message)
  } finally {
    savingHaoka.value = false
  }
}

async function testLlm() {
  testing.value = true
  testMsg.value = ''
  try {
    const body = { llm: { ...llm } }
    if (!body.llm.api_key) delete body.llm.api_key
    if (body.llm.extra) { try { body.llm.extra = JSON.parse(body.llm.extra) } catch { throw new Error('扩展参数不是合法 JSON') } }
    else delete body.llm.extra
    const res = await api.testLlm(body)
    testOk.value = true
    testMsg.value = '连接成功：' + (res.reply || '')
  } catch (e) {
    testOk.value = false
    testMsg.value = '连接失败：' + e.message
  } finally {
    testing.value = false
  }
}

async function getCaptcha() {
  gettingCaptcha.value = true
  loginMsg.value = ''
  try {
    const res = await api.captcha()
    captchaImg.value = res.image || ''
  } catch (e) {
    ElMessage.error('获取验证码失败：' + e.message)
  } finally {
    gettingCaptcha.value = false
  }
}

async function doLogin() {
  if (!captchaCode.value.trim()) { ElMessage.warning('请输入验证码'); return }
  logging.value = true
  loginMsg.value = ''
  try {
    const res = await api.login(captchaCode.value.trim())
    loginOk.value = true
    loginMsg.value = '登录成功：' + (res.user?.username || 'ok')
    captchaImg.value = ''
    captchaCode.value = ''
  } catch (e) {
    loginOk.value = false
    loginMsg.value = '登录失败：' + e.message
    getCaptcha()
  } finally {
    logging.value = false
  }
}

async function syncPhone() {
  syncingPhone.value = true
  syncPhoneResult.value = null
  syncPhoneError.value = ''
  try {
    await api.syncStream((ev) => {
      if (ev.type === 'done') {
        syncPhoneResult.value = ev
        ElMessage.success('手机卡同步完成')
      } else if (ev.type === 'error') {
        syncPhoneError.value = ev.message || '同步失败'
        ElMessage.error(syncPhoneError.value)
      }
    })
  } catch (e) {
    syncPhoneError.value = e.message
    ElMessage.error('同步失败：' + e.message)
  } finally {
    syncingPhone.value = false
  }
}

async function syncKuan() {
  syncingKuan.value = true
  syncKuanResult.value = null
  syncKuanError.value = ''
  try {
    await api.kuanproSyncStream((ev) => {
      if (ev.type === 'done') {
        syncKuanResult.value = ev
        ElMessage.success('宽带选品同步完成')
      } else if (ev.type === 'error') {
        syncKuanError.value = ev.message || '同步失败'
        ElMessage.error(syncKuanError.value)
      }
    })
  } catch (e) {
    syncKuanError.value = e.message
    ElMessage.error('同步失败：' + e.message)
  } finally {
    syncingKuan.value = false
  }
}

async function syncAll() {
  syncingAll.value = true
  syncingPhone.value = true
  syncingKuan.value = true
  allResult.value = null
  allError.value = ''
  let phoneDone = null, kuanDone = null
  try {
    // 第一阶段：手机卡
    await api.syncStream((ev) => {
      if (ev.type === 'done') {
        syncPhoneResult.value = ev
        phoneDone = ev
      } else if (ev.type === 'error') {
        throw new Error(ev.message || '手机卡同步失败')
      }
    })
    // 第二阶段：宽带
    await api.kuanproSyncStream((ev) => {
      if (ev.type === 'done') {
        syncKuanResult.value = ev
        kuanDone = ev
      } else if (ev.type === 'error') {
        throw new Error(ev.message || '宽带同步失败')
      }
    })
    allResult.value = {
      total: (phoneDone?.total || 0) + (kuanDone?.total || 0),
      inserted: (phoneDone?.inserted || 0) + (kuanDone?.inserted || 0),
      updated: (phoneDone?.updated || 0) + (kuanDone?.updated || 0),
      offsale: (phoneDone?.offsale || 0) + (kuanDone?.offsale || 0),
    }
    ElMessage.success('全部同步完成')
  } catch (e) {
    allError.value = e.message
    ElMessage.error('同步失败：' + e.message)
  } finally {
    syncingAll.value = false
    syncingPhone.value = false
    syncingKuan.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.settings { max-width: 1100px; margin: 0 auto; }
.captcha-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.captcha-img { width: 120px; height: 40px; border: 1px solid #dcdfe6; border-radius: 4px; }
.login-box { padding: 4px; }
.sync-box { padding: 8px 4px; }
.sync-title { font-weight: 600; font-size: 15px; margin-bottom: 4px; }
.sync-desc { color: #909399; font-size: 13px; margin-bottom: 12px; }
.sync-result { margin-top: 10px; color: #67c23a; font-size: 13px; }
.sync-all { padding: 4px 4px 4px; }
.sync-all .el-button { min-width: 260px; }
</style>
