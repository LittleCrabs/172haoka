# 172 号卡辅助平台（重建版）

代理商自用的一站式辅助工具：**商品库 + 知识库 RAG + 智能问答 + 设置**。
单用户、无需登录。技术栈：后端 **FastAPI + SQLite**，前端 **Vite + Vue 3 + Element Plus**。

> 业务逻辑（套餐解析、二元组中文检索、无头 Chrome 抓 SPA、H5Dns 域名现取）沿用旧版经验，
> 只换壳不重写算法。旧单体脚本（`server.py` / 根目录 `*.py` 等）已清理。

## 目录结构

```
haoka/
├── backend/                # FastAPI 后端（运行时核心）
│   ├── app/
│   │   ├── main.py         # 入口：挂载路由 + 生产环境静态托管 dist/
│   │   ├── config.py       # 读 backend/config.json（账号 / LLM / embedding）
│   │   ├── database.py     # SQLite 连接 + 建表 + 字段补列
│   │   ├── schemas.py      # Pydantic 模型
│   │   ├── presets.py      # 服务商预设（智谱 / 硅基流动 / DeepSeek / 百炼 / OpenAI）
│   │   ├── routers/        # products / kb / ask / settings
│   │   └── services/       # common / products / specs / embed / retrieve / chunks / ingest / ask
│   ├── config.json         # 配置（**含明文密码，注意保管**）
│   ├── schema.sql          # 建表 SQL
│   └── requirements.txt
├── frontend/               # Vue 3 前端（Vite + pnpm）
│   ├── src/views/          # AskView / ProductsView / KnowledgeView / SettingsView
│   ├── src/api/index.js    # 唯一网络出口（/api/*）
│   ├── src/router/         # hash 路由（无需服务端 rewrite）
│   ├── repair-links.cjs    # pnpm 软链失败时的 junction 自愈脚本（postinstall 调用）
│   └── dist/               # 生产构建产物（由后端静态托管）
├── data/haoka.db           # 真实数据库（商品 / 知识块 / 向量，请勿误删）
├── kb_extra/               # 外挂知识库（*.md，顶部可写 `audience: customer/agent/shared`）
├── token.json              # 后台登录 token 缓存（7 天有效）
└── eval_set.json           # 旧质量门用例（保留备查）
```

## 启动

后端（推荐始终先起，端口 8123）：

```bash
cd haoka/backend
.venv/Scripts/python.exe run.py
```

> `run.py` 是统一启动入口，已关闭 uvicorn 日志的 ANSI 颜色（避免在不支持彩色的
> 终端/日志面板里看到 `[32mINFO[0m` 这类乱码）。等价于：
> `python -m uvicorn app.main:app --host 127.0.0.1 --port 8123`。

前端（**pnpm**）两种用法：
- **生产**：先 `cd frontend && pnpm install && pnpm run build`，后端会自动托管 `frontend/dist/`。
  浏览器打开 `http://127.0.0.1:8123/` 即可（SPA + API 同源，无需再开前端服务）。
- **开发**：`cd frontend && pnpm dev`（默认 5173，已配置 `/api` 代理到 8123）。

> **pnpm 适配说明**：本机某些环境（如受限沙箱）里 pnpm 创建目录软链会失败，
> 退化成空目录壳，导致 `vite build` 报 `Cannot find package ... esbuild/index.js`。
> 项目已内置 `frontend/repair-links.cjs`（并挂在 `postinstall`），`pnpm install` 后会自动
> 用 Windows **junction** 把空壳接回 `.pnpm` 里的真包，并补齐 esbuild 平台二进制。
> 若构建仍报缺包，手动跑一次 `node repair-links.cjs` 即可（正常环境该脚本为空操作）。

## 四个页面

1. **智能问答**：左右布局——左侧提问 / 视角切换（代理商 / 对客）/ 历史，右侧答案与来源。
2. **商品库**：顶部通用搜索（商品名/关键词/备注/地区）+ 运营商/分类/地区下拉（地区候选来自真实数据）+ 月租≤/流量≥；改动即自动搜索；表格展开行看流量结构，商品名列加宽可换行。
3. **知识库**：主从长文——左侧文档列表，右侧长内容阅读区，顶部搜索框做中文关键词检索。
4. **设置**：顶栏右上角齿轮入口；大模型与向量模型两张卡片左右并排，外加 172 号卡后台账号与登录。

## 配置位置（重要）

- 真实配置在 **`backend/config.json`**（不是旧版根目录那份，根目录旧 config 已删除）。
- 后端读取 `backend/config.json`；前端设置页的保存也写到这里。
- `/api/settings` 返回时会对 `password` 与 `api_key` 脱敏（`***已配置***`）；
  前端留空不填即表示"不改原值"。
- 服务商预设点一下自动填 `base_url + model`；智谱 Flash 预设自带
  `{"thinking":{"type":"disabled"}}`（省 token、免推理等待）。

## 主要接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/state` | 版本 / 是否配置 / 商品数 / 文档数 |
| GET | `/api/products` | 筛选 + 分页（`q` 通用搜索 / operator / category / region / max_fee / min_data） |
| GET | `/api/products/facets` | 筛选项候选值（运营商 / 分类 / 地区） |
| POST | `/api/sync` | 同步后台商品（需有效 token） |
| GET | `/api/kb/docs` `/api/kb/chunks` | 文档列表 / 块浏览或检索（`q` 为关键词） |
| POST | `/api/kb/rebuild` `/api/kb/ingest` | 重建分块 / 导入 `kb_extra/*.md` |
| POST | `/api/ask` | 问答（`{q, audience, dry_run}`） |
| GET/POST | `/api/settings` `/api/settings/test-llm` | 配置读写 / 测试大模型 |
| GET/POST | `/api/captcha` `/api/login` | 取验证码 / 登录拿 token |

## 已知约定与坑

- **H5 域名每次现取**：`api/HaoKa/H5Dns` 按账号下发且轮换，详情页链接不写死。
- **中文检索**靠二元组 TF-IDF 全表扫描 + SQL 硬过滤，未依赖 FTS5 trigram（对 2 字中文无效）。
- **宽带"N元"是年费**不写月租，靠单位 M/G 区分，不污染价格筛选。
- **受众隔离已取消运行时隔离**（单用户自用）：佣金/结算照常显示给代理商；
  知识库内容仍可逻辑区分内部手册 vs 对客话术，但不再运行时切分。
- 生产构建后首屏较大（Element Plus 全量引入），单机自用可接受。
