<template>
  <div class="settings">
    <el-tabs v-model="tab" class="cfg-tabs">
      <!-- ================= 模型服务 ================= -->
      <el-tab-pane label="模型服务" name="model">
        <p class="tab-desc">
          问答与知识库检索依赖的模型。均为 OpenAI 兼容接口，填 Base URL + 模型名 + API Key 即可。
          向量模型不配也能用关键词检索，但语义检索效果会差一些。
        </p>
        <el-row :gutter="16" align="top">
          <el-col :span="12">
            <el-card shadow="never" class="block">
              <template #header>
                <div class="card-head">
                  <span>大模型</span>
                  <el-tag size="small" effect="plain" type="info">问答 / 对话</el-tag>
                </div>
              </template>
              <el-form label-width="88px" label-position="right" @submit.prevent>
                <el-form-item label="服务商预设">
                  <el-select v-model="llmPreset" placeholder="手动填写" clearable style="width: 100%"
                    @change="applyLlmPreset">
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
                  <span class="field-hint">越低越稳定，问答建议 0.2–0.4</span>
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

          <el-col :span="12">
            <el-card shadow="never" class="block">
              <template #header>
                <div class="card-head">
                  <span>向量模型</span>
                  <el-tag size="small" effect="plain" type="info">知识库检索</el-tag>
                </div>
              </template>
              <el-form label-width="88px" label-position="right" @submit.prevent>
                <el-form-item label="服务商预设">
                  <el-select v-model="embedPreset" placeholder="手动填写" clearable style="width: 100%"
                    @change="applyEmbedPreset">
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
                  <span class="field-hint">不配也能用关键词检索</span>
                </el-form-item>
              </el-form>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ================= 数据源账号 ================= -->
      <el-tab-pane label="数据源账号" name="account">
        <p class="tab-desc">
          172号卡后台的登录凭据，用于同步商品与获取 H5 详情域名。登录后 token 有效 7 天，过期需要重新登录。
        </p>
        <!-- 不写 align：默认 stretch，两列才会等高 -->
        <el-row :gutter="16" class="acc-row">
          <el-col :span="12">
            <el-card shadow="never" class="block">
              <template #header>后台账号</template>
              <el-form label-width="88px" label-position="right" @submit.prevent>
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
                  <el-input v-model="haoka.password" type="password" show-password
                    placeholder="已配置则留空不修改" />
                </el-form-item>
                <el-form-item label="网络代理">
                  <el-input v-model="haoka.proxy" placeholder="http://127.0.0.1:10808（留空 = 系统默认）" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="savingHaoka" @click="saveHaoka">保存账号</el-button>
                </el-form-item>
              </el-form>
            </el-card>
          </el-col>

          <el-col :span="12">
            <el-card shadow="never" class="block">
              <template #header>
                <div class="card-head">
                  <span>登录状态</span>
                  <el-tag size="small" :type="loginInfo.logged_in ? 'success' : 'info'" effect="plain">
                    {{ loginInfo.logged_in ? '已登录' : '未登录' }}
                  </el-tag>
                </div>
              </template>

              <!-- 以前这张卡叫「登录状态」却只有验证码表单，看不出自己登着还是掉了，
                   同步失败时只能去翻日志。现在先给状态，表单收进「重新登录」。 -->
              <div v-if="loginInfo.logged_in" class="state-box">
                <div class="state-row">
                  <el-icon class="state-ico ok"><CircleCheckFilled /></el-icon>
                  <div class="state-text">
                    <div class="state-main">
                      {{ loginInfo.username || '已登录' }}
                      <span v-if="loginInfo.role" class="state-role">{{ loginInfo.role }}</span>
                    </div>
                    <div class="state-sub">
                      有效期至 {{ loginInfo.expire_at }}
                      <span :class="loginInfo.expiring ? 'state-warn' : 'state-dim'">
                        · 剩余 {{ loginInfo.days_left }} 天
                      </span>
                    </div>
                  </div>
                </div>
                <div class="state-meta">
                  上次登录 {{ loginInfo.login_at }}<span v-if="loginInfo.agent_id"> · AgentID {{ loginInfo.agent_id }}</span>
                </div>
                <el-alert v-if="loginInfo.expiring" type="warning" :closable="false" show-icon
                  title="token 快过期了，过期后同步会直接失败，建议现在重新登录一次" class="state-alert" />
                <div class="state-actions">
                  <el-button v-if="!relogin" size="small" :icon="Refresh" @click="startRelogin">重新登录</el-button>
                  <el-button v-else size="small" text @click="relogin = false">收起</el-button>
                </div>
                <!-- 左卡比右卡高一大截，右边看着像缺了一块。这里把 token 相关的事实说清楚，
                     既填平高度，也回答「什么时候会失效、失效了会怎样」。 -->
                <div v-if="!relogin" class="state-tip">
                  <div class="tip-line"><b>token 有效期</b> 7 天，只在登录成功时刷新</div>
                  <div class="tip-line"><b>过期后</b> 同步会直接失败并提示 token_expired，需回来重新登录</div>
                  <div class="tip-line"><b>存放位置</b> 项目根目录 token.json，请勿外传</div>
                </div>
              </div>

              <div v-else class="state-box">
                <div class="state-row">
                  <el-icon class="state-ico warn"><WarningFilled /></el-icon>
                  <div class="state-text">
                    <div class="state-main">尚未登录后台</div>
                    <div class="state-sub">{{ loginInfo.reason || '同步商品前需要先登录一次' }}</div>
                  </div>
                </div>
              </div>

              <div v-if="!loginInfo.logged_in || relogin" class="login-box mt12">
                <div class="muted">输入图形验证码完成登录，登录成功后即可同步数据。</div>
                <div class="captcha-row">
                  <div class="captcha-slot">
                    <img v-if="captchaImg" :src="captchaImg" class="captcha-img" alt="验证码"
                      @click="getCaptcha" />
                    <el-button v-else :loading="gettingCaptcha" @click="getCaptcha">获取验证码</el-button>
                  </div>
                  <el-button v-if="captchaImg" text :icon="Refresh" @click="getCaptcha">换一张</el-button>
                </div>
                <el-input v-model="captchaCode" placeholder="输入图形验证码" style="max-width: 220px"
                  @keyup.enter="doLogin" />
                <div class="login-actions">
                  <el-button type="primary" :loading="logging" @click="doLogin">登录</el-button>
                </div>
                <el-alert v-if="loginMsg" :type="loginOk ? 'success' : 'error'" :closable="false"
                  :title="loginMsg" style="margin-top: 12px" />
              </div>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ================= 数据同步 ================= -->
      <el-tab-pane label="数据同步" name="sync">
        <p class="tab-desc">
          从 172号卡后台拉取商品并写入本地库。同步会比对字段差异，只有真正变化的字段才写入更新日志。
          手机卡与宽带是两条独立通道，互不影响。
        </p>

        <!-- 状态带：这一页最该回答「上次同步是什么时候、成功了吗」，原来一个字都没有 -->
        <el-card shadow="never" class="block status-band">
          <div class="band">
            <el-icon class="band-ico" :class="bandState"><component :is="bandIcon" /></el-icon>
            <div class="band-main">
              <div class="band-title">{{ bandTitle }}</div>
              <div class="band-sub">{{ bandSub }}</div>
            </div>
            <div class="band-right">
              <template v-if="bandCounts">
                <span class="cnt"><b>{{ bandCounts.inserted }}</b> 新增</span>
                <span class="cnt"><b>{{ bandCounts.updated }}</b> 更新</span>
                <span class="cnt"><b>{{ bandCounts.offsale }}</b> 下架</span>
              </template>
              <el-button link type="primary" @click="$router.push('/changes')">查看变更日志</el-button>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="block mt12">
          <div class="sync-hero">
            <div class="sync-hero-text">
              <div class="sync-hero-title">一键同步全部</div>
              <div class="sync-hero-desc">依次同步手机卡（约 170 条）与宽带选品（约 890 条）</div>
            </div>
            <el-button type="primary" size="large" :loading="syncingAll"
              :disabled="syncingAll || syncingPhone || syncingKuan" @click="syncAll">
              {{ syncingAll ? '同步中…' : '开始同步' }}
            </el-button>
          </div>
          <el-alert v-if="allResult" type="success" :closable="false" style="margin-top: 12px"
            :title="`合计 ${allResult.total} 条：新增 ${allResult.inserted}，更新 ${allResult.updated}，下架 ${allResult.offsale}`" />
          <el-alert v-if="allError" type="error" :closable="false" :title="allError" style="margin-top: 12px" />
        </el-card>

        <el-row :gutter="16" align="top" class="mt12">
          <el-col :span="12">
            <el-card shadow="never" class="block">
              <template #header>
                <div class="card-head">
                  <span>手机卡商品</span>
                  <span class="head-meta">{{ lastOf('手机卡') }}</span>
                </div>
              </template>
              <div class="sync-box">
                <div class="sync-desc">来源 api/Products/Query</div>
                <el-button :loading="syncingPhone" :disabled="syncingPhone || syncingAll" @click="syncPhone">
                  {{ syncingPhone ? '同步中…' : '单独同步手机卡' }}
                </el-button>
                <div v-if="syncPhoneResult" class="sync-result">
                  共 {{ syncPhoneResult.total }} 条 · 新增 {{ syncPhoneResult.inserted }} · 更新
                  {{ syncPhoneResult.updated }} · 下架 {{ syncPhoneResult.offsale }}
                </div>
                <el-alert v-if="syncPhoneError" type="error" :closable="false" :title="syncPhoneError"
                  style="margin-top: 10px" />
              </div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never" class="block">
              <template #header>
                <div class="card-head">
                  <span>宽带选品</span>
                  <span class="head-meta">{{ lastOf('宽带') }}</span>
                </div>
              </template>
              <div class="sync-box">
                <div class="sync-desc">来源 api/ProKuan/GroundProQuery</div>
                <el-button :loading="syncingKuan" :disabled="syncingKuan || syncingAll" @click="syncKuan">
                  {{ syncingKuan ? '同步中…' : '单独同步宽带' }}
                </el-button>
                <div v-if="syncKuanResult" class="sync-result">
                  共 {{ syncKuanResult.total }} 条 · 新增 {{ syncKuanResult.inserted }} · 更新
                  {{ syncKuanResult.updated }} · 下架 {{ syncKuanResult.offsale }}
                </div>
                <el-alert v-if="syncKuanError" type="error" :closable="false" :title="syncKuanError"
                  style="margin-top: 10px" />
              </div>
            </el-card>
          </el-col>
        </el-row>

        <!-- 最近同步记录：正好填掉这页下方原本空着的半屏 -->
        <el-card shadow="never" class="block mt12">
          <template #header>
            <div class="card-head">
              <span>最近同步记录</span>
              <el-button link type="primary" :icon="Refresh" :loading="syncLoading" @click="loadSync">刷新</el-button>
            </div>
          </template>
          <el-table :data="syncInfo.items" size="small" v-loading="syncLoading" :show-header="true">
            <el-table-column label="开始时间" width="150">
              <template #default="{ row }">
                <span class="num-cell">{{ row.started_at }}</span>
              </template>
            </el-table-column>
            <el-table-column label="通道" width="90">
              <template #default="{ row }">
                <el-tag size="small" type="info" effect="plain">{{ row.kind }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="结果" width="110">
              <template #default="{ row }">
                <span class="st" :class="row.status">
                  {{ STATUS_LABEL[row.status] || row.status }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="条数" width="90" align="right">
              <template #default="{ row }"><span class="num-cell">{{ row.total ?? '—' }}</span></template>
            </el-table-column>
            <el-table-column label="新增 / 更新 / 下架" width="160" align="right">
              <template #default="{ row }">
                <span class="num-cell">{{ row.inserted ?? 0 }} / {{ row.updated ?? 0 }} / {{ row.offsale ?? 0 }}</span>
              </template>
            </el-table-column>
            <el-table-column label="用时" width="80" align="right">
              <template #default="{ row }">
                <span class="num-cell">{{ row.duration != null ? row.duration + 's' : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <span :class="{ muted: !row.message }">{{ row.message || '—' }}</span>
              </template>
            </el-table-column>
            <template #empty>
              <EmptyState compact type="table" title="还没有同步记录"
                desc="点上方「开始同步」跑一次，这里就会出现每条通道的结果" />
            </template>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- ================= 小红书判定 ================= -->
      <el-tab-pane label="小红书" name="xhs">
        <p class="tab-desc">
          自动回复的判定规则与口吻。保存后对下一次运行立即生效——阈值只在后端判一次，
          机器人本身不再带自己的阈值。关键词表仍在代码里，这里调的是分数。
        </p>
        <el-row :gutter="16" align="top">
          <el-col :span="9">
            <el-card shadow="never" class="block">
              <template #header>
                <div class="card-head">
                  <span>判定阈值</span>
                  <el-tag size="small" effect="plain" type="info">目标人群</el-tag>
                </div>
              </template>
              <el-form label-width="76px" label-position="right" @submit.prevent>
                <el-form-item label="最低分">
                  <el-input-number v-model="xhs.min_score" :min="0" :max="20" />
                  <span class="field-hint">低于此分不回复</span>
                </el-form-item>
              </el-form>
              <div class="sub-title">信号权重</div>
              <div class="w-grid">
                <div v-for="(w, name) in xhs.weights" :key="name" class="w-item">
                  <span class="w-name">{{ name }}</span>
                  <el-input-number v-model="xhs.weights[name]" :min="0" :max="10" size="small"
                    controls-position="right" class="w-num" />
                </div>
              </div>
              <div class="xhs-note">
                「办卡意图」「流量需求」是强信号，单独命中即可回；
                「资费敏感」「学生校园」需两类共现；「异地流动」「网络体验」只加分，永不单独成立。
                这个分级条件写死在代码里，换算不了。
              </div>
              <div class="xhs-sum">
                六类全中合计 {{ totalWeight }} 分 · 当前阈值 {{ xhs.min_score }} 分
              </div>
            </el-card>
          </el-col>

          <el-col :span="15">
            <el-card shadow="never" class="block">
              <template #header>
                <div class="card-head">
                  <span>人格（口吻）</span>
                  <el-tag size="small" effect="plain" type="info">文案可改</el-tag>
                </div>
              </template>
              <el-form label-width="76px" label-position="right" @submit.prevent>
                <el-form-item label="默认人格">
                  <el-select v-model="xhs.default_tone" style="width: 200px">
                    <el-option v-for="(t, n) in xhs.tones" :key="n" :label="n" :value="n" />
                  </el-select>
                </el-form-item>
                <el-form-item label="自动轮换">
                  <el-switch v-model="xhs.rotate_tone" />
                  <span class="field-hint">
                    {{ xhs.rotate_tone ? '同一帖子始终同口吻，重跑时换热' : '固定用默认人格' }}
                  </span>
                </el-form-item>
              </el-form>

              <!-- 四个人格做成独立卡片：原来是四块无边框 textarea 紧挨着，
                   视觉上糊成一大段散文，改哪一块都看不出来。 -->
              <div class="tone-grid">
                <div v-for="(t, n) in xhs.tones" :key="n" class="tone-card" :class="{ isDefault: n === xhs.default_tone }">
                  <div class="tone-head">
                    <div class="tone-title">
                      <span class="tone-name">{{ n }}</span>
                      <el-tag v-if="n === xhs.default_tone" size="small" type="primary" effect="plain">默认</el-tag>
                      <span v-if="toneChanged(n)" class="tone-dirty">已修改</span>
                    </div>
                    <div class="tone-tools">
                      <el-button link type="primary" @click="toggleTone(n)">
                        {{ toneOpen[n] ? '收起' : '编辑' }}
                      </el-button>
                      <el-button
                        link :disabled="!toneChanged(n) && t === factoryTones[n]"
                        @click="resetTone(n)"
                      >恢复默认</el-button>
                    </div>
                  </div>
                  <div class="tone-preview" v-if="!toneOpen[n]" @click="toggleTone(n)">
                    {{ t }}
                  </div>
                  <el-input
                    v-else
                    v-model="xhs.tones[n]"
                    type="textarea"
                    :autosize="{ minRows: 2, maxRows: 5 }"
                    resize="none"
                  />
                </div>
              </div>

              <div class="xhs-actions">
                <el-button type="primary" :loading="savingXhs" @click="saveXhs">保存小红书配置</el-button>
                <span class="field-hint">合规约束那段是所有人生效、不可改的</span>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ================= 系统信息 ================= -->
      <el-tab-pane label="系统信息" name="about">
        <p class="tab-desc">本平台为单机自用，所有配置与数据都保存在本机，不上传任何第三方服务。</p>
        <el-row :gutter="16" align="top">
          <el-col :span="8">
            <el-card shadow="never" class="stat">
              <div class="stat-val">{{ state.product_count ?? '—' }}</div>
              <div class="stat-label">商品总数</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" class="stat">
              <div class="stat-val">{{ state.doc_count ?? '—' }}</div>
              <div class="stat-label">知识文档</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" class="stat">
              <div class="stat-val" :class="state.configured ? 'ok' : 'warn'">
                {{ state.configured ? '已配置' : '未配置' }}
              </div>
              <div class="stat-label">大模型</div>
            </el-card>
          </el-col>
        </el-row>

        <el-card shadow="never" class="block mt16">
          <template #header>
            <div class="card-head">
              <span>运行环境</span>
              <!-- 版本号原来是键值表里的第二列，右边凭空多出一个没表头的 v1，
                   和上面的「访问地址」不构成任何对应关系。移到标题右侧当标签。 -->
              <el-tag size="small" type="info" effect="plain">配置版本 v{{ state.version ?? '—' }}</el-tag>
            </div>
          </template>
          <el-descriptions :column="2" border size="small" label-width="96px">
            <el-descriptions-item label="访问地址" :span="2">
              <span class="mono">{{ origin }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="配置文件">
              <span class="mono">backend/config.json</span>
            </el-descriptions-item>
            <el-descriptions-item label="数据文件">
              <span class="mono">data/haoka.db（SQLite）</span>
            </el-descriptions-item>
            <el-descriptions-item label="安全提示" :span="2">
              <span class="warn-text">config.json 含明文后台密码与 API Key，请勿外传或提交到代码仓库。</span>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, CircleCheckFilled, WarningFilled, Loading } from '@element-plus/icons-vue'
import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'

defineOptions({ name: 'SettingsView' })

const tab = ref('model')
const presets = reactive({ llm: [], embed: [] })
const llmPreset = ref('')
const embedPreset = ref('')
const llm = reactive({ base_url: '', model: '', api_key: '', temperature: 0.3, max_tokens: 1200, extra: '' })
const embed = reactive({ base_url: '', model: '', api_key: '' })
const haoka = reactive({ site: '', api: '', username: '', password: '', proxy: '' })
// 小红书判定：阈值 + 六类权重 + 人格文案（都是后端 config.xhs 里的字段）
const xhs = reactive({ min_score: 2, weights: {}, tones: {}, default_tone: '', rotate_tone: true })
const state = reactive({ version: null, configured: false, product_count: null, doc_count: null })

const savingLlm = ref(false)
const savingEmbed = ref(false)
const savingHaoka = ref(false)
const savingXhs = ref(false)
const testing = ref(false)
const testOk = ref(false)
const testMsg = ref('')

const gettingCaptcha = ref(false)
const logging = ref(false)
const captchaImg = ref('')
const captchaCode = ref('')
const loginMsg = ref('')
const loginOk = ref(false)

const syncingPhone = ref(false)
const syncPhoneResult = ref(null)
const syncPhoneError = ref('')
const syncingKuan = ref(false)
const syncKuanResult = ref(null)
const syncKuanError = ref('')
const syncingAll = ref(false)
const allResult = ref(null)
const allError = ref('')

const origin = computed(() => window.location.origin)
const totalWeight = computed(() =>
  Object.values(xhs.weights).reduce((a, b) => a + (Number(b) || 0), 0))

// ---------------- 登录状态 ----------------
const loginInfo = ref({ logged_in: false })
const relogin = ref(false)

async function loadLogin() {
  try {
    loginInfo.value = await api.loginStatus()
    if (!loginInfo.value.logged_in) relogin.value = false
  } catch (e) { /* 拿不到就当未登录，不影响表单可用 */ }
}

function startRelogin() {
  relogin.value = true
  captchaImg.value = ''
  captchaCode.value = ''
  loginMsg.value = ''
  getCaptcha()
}

// ---------------- 同步状态 ----------------
const syncInfo = ref({ items: [], last: null, last_ok: {}, running: null })
const syncLoading = ref(false)

const STATUS_LABEL = { ok: '成功', running: '同步中', failed: '失败', token_expired: '登录过期' }

function fmtShort(t) {
  return t ? String(t).slice(5, 16) : '—'
}

async function loadSync() {
  syncLoading.value = true
  try {
    syncInfo.value = await api.syncStatus(6)
  } catch (e) { /* 同步状态拿不到不影响按钮 */ }
  finally { syncLoading.value = false }
}

const bandLast = computed(() => syncInfo.value.running || syncInfo.value.last)
const bandTitle = computed(() => {
  if (syncInfo.value.running) return `正在同步 ${syncInfo.value.running.kind}…`
  const l = syncInfo.value.last
  if (!l) return '还没有同步过'
  return `上次同步 ${fmtShort(l.started_at)} ${STATUS_LABEL[l.status] || l.status}`
})
const bandSub = computed(() => {
  const l = bandLast.value
  if (!l) return '点下面的「开始同步」拉一次商品，之后这里会显示每通道的结果'
  const parts = [`${l.kind}通道`, `共 ${l.total ?? 0} 条`]
  if (l.duration != null) parts.push(`用时 ${l.duration} 秒`)
  if (l.message) parts.push(l.message)
  return parts.join(' · ')
})
const bandCounts = computed(() => {
  const l = syncInfo.value.last
  return l && l.status === 'ok' ? l : null
})
const bandIcon = computed(() => {
  if (syncInfo.value.running) return Loading
  const l = syncInfo.value.last
  if (!l) return WarningFilled
  return l.status === 'ok' ? CircleCheckFilled : WarningFilled
})
const bandState = computed(() => {
  if (syncInfo.value.running) return 'running'
  const l = syncInfo.value.last
  if (!l) return 'warn'
  return l.status === 'ok' ? 'ok' : 'fail'
})

function lastOf(kind) {
  const r = syncInfo.value.last_ok ? syncInfo.value.last_ok[kind] : null
  if (!r) return '暂无记录'
  return `上次 ${fmtShort(r.started_at)} · ${r.total ?? 0} 条`
}

// ---------------- 人格卡片 ----------------
// 默认文案来自后端 factory_tones：改坏了要能一键还原，而不是去翻代码
const factoryTones = ref({})
const toneOpen = reactive({})
const toneSnapshot = ref({})

function toneChanged(name) {
  const saved = toneSnapshot.value[name]
  return saved !== undefined && saved !== xhs.tones[name]
}
function toggleTone(name) {
  toneOpen[name] = !toneOpen[name]
}
function resetTone(name) {
  const dv = factoryTones.value[name]
  if (dv) xhs.tones[name] = dv
}

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
    // 小红书配置走 /api/xhs/config：后端会把缺的字段用默认值补齐，
    // 所以第一次打开（config.json 里还没有 xhs）也是完整的四人格 + 六权重
    try {
      const X = await api.xhsConfig()
      xhs.min_score = X.min_score ?? 2
      xhs.weights = { ...(X.weights || {}) }
      xhs.tones = { ...(X.tones || {}) }
      xhs.default_tone = X.default_tone || ''
      xhs.rotate_tone = X.rotate_tone !== false
      factoryTones.value = { ...(X.factory_tones || {}) }
      toneSnapshot.value = { ...xhs.tones }
    } catch (e) { /* 小红书配置拿不到不影响其它 Tab */ }
  } catch (e) {
    ElMessage.error('加载设置失败：' + e.message)
  }
}

async function loadState() {
  try {
    Object.assign(state, await api.state())
  } catch (e) { /* 状态拿不到不影响配置编辑 */ }
}

async function saveLlm() {
  savingLlm.value = true
  try {
    const body = { llm: { ...llm } }
    if (!body.llm.api_key) delete body.llm.api_key
    if (body.llm.extra) {
      try { body.llm.extra = JSON.parse(body.llm.extra) } catch { throw new Error('扩展参数不是合法 JSON') }
    } else delete body.llm.extra
    await api.saveSettings(body)
    ElMessage.success('大模型配置已保存')
    loadState()
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

async function saveXhs() {
  const blank = Object.entries(xhs.tones).find(([, v]) => !String(v || '').trim())
  if (blank) {
    ElMessage.warning(`「${blank[0]}」的人格文案不能为空`)
    return
  }
  savingXhs.value = true
  try {
    await api.saveSettings({
      xhs: {
        min_score: xhs.min_score,
        weights: { ...xhs.weights },
        tones: { ...xhs.tones },
        default_tone: xhs.default_tone,
        rotate_tone: xhs.rotate_tone,
      },
    })
    ElMessage.success('小红书配置已保存')
    toneSnapshot.value = { ...xhs.tones }
  } catch (e) {
    ElMessage.error('保存失败：' + e.message)
  } finally {
    savingXhs.value = false
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
    if (body.llm.extra) {
      try { body.llm.extra = JSON.parse(body.llm.extra) } catch { throw new Error('扩展参数不是合法 JSON') }
    } else delete body.llm.extra
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
    relogin.value = false
    loadLogin()
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
        loadState()
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
    loadSync()
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
        loadState()
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
    loadSync()
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
    await api.syncStream((ev) => {
      if (ev.type === 'done') {
        syncPhoneResult.value = ev
        phoneDone = ev
      } else if (ev.type === 'error') {
        throw new Error(ev.message || '手机卡同步失败')
      }
    })
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
    loadState()
  } catch (e) {
    allError.value = e.message
    ElMessage.error('同步失败：' + e.message)
  } finally {
    syncingAll.value = false
    syncingPhone.value = false
    syncingKuan.value = false
    loadSync()
  }
}

onMounted(() => {
  load()
  loadState()
  loadLogin()
  loadSync()
})
</script>

<style scoped>
.settings {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 4px 22px 22px;
}
.cfg-tabs :deep(.el-tabs__header) { margin-bottom: 14px; }
.cfg-tabs :deep(.el-tabs__nav-wrap::after) { height: 1px; background: var(--line); }
.cfg-tabs :deep(.el-tabs__item) { font-size: 14px; height: 44px; }

.tab-desc {
  margin: 0 0 14px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-3);
  max-width: 860px;
}

.block :deep(.el-card__body) { padding: 16px 18px; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.field-hint { margin-left: 10px; font-size: 12px; color: var(--text-3); }

.login-box { display: flex; flex-direction: column; gap: 12px; }

/* ---------- 登录状态 ---------- */
.state-box { display: flex; flex-direction: column; gap: 10px; flex: 1; justify-content: space-between; }
.state-row { display: flex; align-items: center; gap: 10px; }
.state-ico { font-size: 22px; flex: 0 0 auto; }
.state-ico.ok { color: var(--ok); }
.state-ico.warn { color: #e8912d; }
.state-text { min-width: 0; }
.state-main { font-size: 14px; font-weight: 600; color: var(--text-1); display: flex; align-items: center; gap: 8px; }
.state-role {
  font-size: 11px;
  font-weight: normal;
  color: var(--text-3);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 0 5px;
}
.state-sub { margin-top: 3px; font-size: 12.5px; color: var(--text-2); }
.state-dim { color: var(--text-3); }
.state-warn { color: #b97424; font-weight: 600; }
.state-meta {
  font-size: 12px;
  color: var(--text-3);
  padding: 8px 10px;
  background: #fafbfc;
  border-radius: 6px;
  font-variant-numeric: tabular-nums;
}
.state-alert { margin-top: 2px; }
.state-actions { display: flex; gap: 8px; }
.state-tip {
  padding-top: 12px;
  border-top: 1px dashed var(--line);
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.5;
}
.state-tip b { font-weight: 600; color: var(--text-2); margin-right: 6px; }
/* 左右两张卡等高：不然左卡五个输入框、右卡三行字，底边差着一大截，像缺了一块 */
.acc-row :deep(.el-col) { display: flex; }
.acc-row :deep(.el-card) { width: 100%; display: flex; flex-direction: column; }
.acc-row :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; }

/* ---------- 同步状态带 ---------- */
.status-band :deep(.el-card__body) { padding: 14px 18px; }
.band { display: flex; align-items: center; gap: 12px; }
.band-ico { font-size: 22px; flex: 0 0 auto; }
.band-ico.ok { color: var(--ok); }
.band-ico.warn { color: #e8912d; }
.band-ico.fail { color: #e5484d; }
.band-ico.running { color: var(--brand); animation: spin 1.4s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.band-main { flex: 1; min-width: 0; }
.band-title { font-size: 14px; font-weight: 600; color: var(--text-1); }
.band-sub { margin-top: 3px; font-size: 12.5px; color: var(--text-3); }
.band-right { display: flex; align-items: center; gap: 14px; flex: 0 0 auto; }
.cnt { font-size: 12.5px; color: var(--text-3); font-variant-numeric: tabular-nums; }
.cnt b { color: var(--text-1); font-weight: 600; margin-right: 2px; }
.st { font-size: 12.5px; }
.st.ok { color: var(--ok); }
.st.failed, .st.token_expired { color: #e5484d; }
.st.running { color: var(--brand); }
.head-meta { font-size: 12px; font-weight: normal; color: var(--text-3); }
.mt12 { margin-top: 12px; }

.captcha-row { display: flex; align-items: center; gap: 10px; min-height: 40px; }
.captcha-slot { min-width: 120px; }
.captcha-img {
  width: 120px; height: 40px;
  border: 1px solid var(--line);
  border-radius: 6px;
  cursor: pointer;
  display: block;
}
.login-actions { display: flex; gap: 8px; }

.sync-hero { display: flex; align-items: center; gap: 20px; }
.sync-hero-title { font-size: 15px; font-weight: 600; color: var(--text-1); }
.sync-hero-desc { margin-top: 4px; font-size: 12.5px; color: var(--text-3); }
.sync-hero .el-button { margin-left: auto; min-width: 150px; }
.sync-box { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; }
.sync-desc { font-size: 12.5px; color: var(--text-3); }
.sync-result { font-size: 12.5px; color: var(--ok); }
.mt16 { margin-top: 16px; }

/* ---------- 小红书判定 Tab ---------- */
.sub-title { margin: 6px 0 10px; font-size: 13px; font-weight: 600; color: var(--text-1); }
.w-grid { display: flex; flex-direction: column; gap: 8px; }
.w-item { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.w-name { font-size: 13px; color: var(--text-2); }
.w-num { width: 96px; }
.xhs-note {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--brand-soft);
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-2);
}
.xhs-sum { margin-top: 10px; font-size: 12.5px; color: var(--text-3); }
/* ---------- 人格卡片 ---------- */
.tone-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.tone-card {
  border: 1px solid var(--line);
  border-left: 3px solid #dfe4ec;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fcfdff;
  transition: border-color .15s, background .15s;
}
.tone-card.isDefault { border-left-color: var(--brand); background: var(--brand-soft); }
.tone-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.tone-title { display: flex; align-items: center; gap: 6px; min-width: 0; }
.tone-name { font-size: 13px; font-weight: 600; color: var(--text-1); }
.tone-dirty { font-size: 11px; color: #b97424; }
.tone-tools { display: flex; gap: 2px; flex: 0 0 auto; }
.tone-tools :deep(.el-button) { font-size: 12px; padding: 0 4px; }
.tone-preview {
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-2);
  cursor: pointer;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tone-preview:hover { color: var(--text-1); }
.xhs-actions { margin-top: 18px; display: flex; align-items: center; gap: 12px; }

.stat :deep(.el-card__body) { padding: 16px 18px; }
.stat-val { font-size: 24px; font-weight: 700; color: var(--text-1); line-height: 1.2; }
.stat-val.ok { color: var(--ok); font-size: 20px; }
.stat-val.warn { color: #f0a020; font-size: 20px; }
.stat-label { margin-top: 4px; font-size: 12.5px; color: var(--text-3); }
.mono { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12.5px; color: var(--text-2); }
.warn-text { color: #b97424; }
.mt16 { margin-top: 16px; }
</style>
