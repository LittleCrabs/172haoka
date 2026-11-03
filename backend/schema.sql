-- 172号卡 本地数据库结构
-- 设计原则：结构化字段进列（可 SQL 过滤），原始返回整包留 raw_json（可回溯）
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------- 杂项键值（H5 域名等） ----------
CREATE TABLE IF NOT EXISTS meta (
    k          TEXT PRIMARY KEY,
    v          TEXT,
    updated_at TEXT
);

-- ---------- 商品 ----------
CREATE TABLE IF NOT EXISTS products (
    product_id       INTEGER PRIMARY KEY,
    product_name     TEXT NOT NULL,
    operator         TEXT,            -- 移动/联通/电信/广电/宽带/靓号
    category         TEXT,            -- 手机卡 / 宽带 / 靓号
    monthly_fee      INTEGER,         -- 月租(元)，仅手机卡解析；宽带留空
    data_gb          INTEGER,         -- 流量(GB)，从名称解析
    voice_min        INTEGER,         -- 通话(分钟)，从名称解析
    commission       REAL,            -- 本账号可见佣金 sPrice
    commission_type  TEXT,            -- 次月返 / 秒返
    commission_read  TEXT,            -- 原始佣金文案
    area             TEXT,            -- 归属地
    area_read        TEXT,
    disable_area     TEXT,            -- 禁发地区（逗号分隔）
    age_min          INTEGER,
    age_max          INTEGER,
    rule             TEXT,            -- 结算规则
    remark           TEXT,            -- 下单备注/限制
    keywords         TEXT,            -- 卖点关键词
    third_api        INTEGER,
    on_sale          INTEGER,         -- 1 在售 0 下架
    is_zhutui        INTEGER,         -- 主推
    main_pic         TEXT,
    sn               TEXT,
    product_str      TEXT,
    detail_url       TEXT,            -- 客户可看的套餐详情页 {h5}/PackInfo/Detail/{productIDStr}
    exclusive_url    TEXT,            -- 代理专属推广链接 {h5}/pdetails?tk={userSn}&pro={productIDStr}
    raw_json         TEXT,
    create_time      TEXT,            -- 原网站商品的添加时间（接口 createTime）
    first_seen       TEXT,
    last_seen        TEXT,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_products_operator ON products(operator);
CREATE INDEX IF NOT EXISTS idx_products_onsale   ON products(on_sale);
CREATE INDEX IF NOT EXISTS idx_products_fee      ON products(monthly_fee);

-- ---------- 变更流水（对比上一版，记录每次同步改了什么） ----------
CREATE TABLE IF NOT EXISTS product_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL,
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_at  TEXT NOT NULL,
    batch_id    TEXT            -- 同一批次同步的变更归到一组，便于按同步查看
);
CREATE INDEX IF NOT EXISTS idx_changes_time ON product_changes(changed_at);
-- idx_changes_batch 在 database.py 的迁移里创建（老库先加列再加索引，避免 executescript 失败）

-- ---------- 抓取日志 ----------
CREATE TABLE IF NOT EXISTS crawl_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT,
    finished_at TEXT,
    total       INTEGER,
    inserted    INTEGER,
    updated     INTEGER,
    unchanged   INTEGER,
    offsale     INTEGER,
    status      TEXT,
    message     TEXT
);

-- ---------- 知识库（语雀等） ----------
-- audience: agent=代理商操作，不给客户看；customer=可对客；shared=两边都能用
CREATE TABLE IF NOT EXISTS kb_docs (
    doc_id       TEXT PRIMARY KEY,
    title        TEXT,
    url          TEXT,
    category     TEXT,
    audience     TEXT DEFAULT 'agent',
    content      TEXT,
    content_hash TEXT,
    fetched_at   TEXT
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id   TEXT PRIMARY KEY,
    source     TEXT NOT NULL,          -- 'kb' | 'product'
    doc_id     TEXT,                   -- kb: 文档id；product: product_id
    audience   TEXT DEFAULT 'agent',   -- 由所属文档继承
    title      TEXT,
    heading    TEXT,
    seq        INTEGER,
    text       TEXT NOT NULL,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON kb_chunks(source, doc_id);

-- ---------- 向量（float32 小端 BLOB） ----------
CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id   TEXT PRIMARY KEY,
    source     TEXT,
    model      TEXT,
    dim        INTEGER,
    vec        BLOB NOT NULL,
    created_at TEXT
);

-- ---------- 关键词检索（trigram 对中文友好） ----------
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
    chunk_id UNINDEXED,
    title,
    text,
    tokenize = 'trigram'
);

-- ---------- 流量结构（specs.py 从详情页解析，派生数据） ----------
-- 不放进 products：sync_products 用 INSERT OR REPLACE 整行覆盖，
-- 派生字段每次同步都会被冲掉。这里由 build_chunks.rebuild() 全量重算。
CREATE TABLE IF NOT EXISTS product_specs (
    product_id     INTEGER PRIMARY KEY,
    total_gb       REAL,
    general_gb     REAL,   -- 通用流量，解析不出来就是 NULL，不拿 total 顶替
    directional_gb REAL,   -- 定向流量
    night_gb       REAL,   -- 夜间/闲时流量
    night_window   TEXT,   -- 如 23:00-07:00
    source         TEXT,   -- 数字取自哪个字段：优惠详情 / remark / product_name
    evidence       TEXT,   -- 命中的原文片段，供人工核对
    updated_at     TEXT
);

-- ---------- 商品详情页（sync_details 从 H5 抓取，SPA 渲染） ----------
CREATE TABLE IF NOT EXISTS product_details (
    product_id   INTEGER PRIMARY KEY,
    sections     TEXT,        -- 各区块文本 JSON
    raw_text     TEXT,
    content_hash TEXT,
    fetched_at   TEXT
);

-- ---------- 小红书回复去重（避免同帖重复回、缓存已生成文案省 token） ----------
CREATE TABLE IF NOT EXISTS xhs_replies (
    key          TEXT PRIMARY KEY,   -- post_id（"id:"前缀）或 正文sha1（"hash:"前缀）
    post_id      TEXT,               -- 小红书帖子 ID（自动化传入，可空）
    post_hash    TEXT,               -- 正文 sha1（无 post_id 时兜底去重）
    region       TEXT,
    should_reply INTEGER,            -- 1=命中人群已回 0=判定不回
    score        INTEGER,
    tone         TEXT,               -- 本次使用的人格话术
    reply_text   TEXT,
    replied_at   TEXT,
    -- 评论真正发出去的时间（机器人发送成功后才回填）。
    -- replied_at 只代表「后端生成了回复」，dry 试跑也会写；两者必须分开，
    -- 否则页面上无法区分「已生成」和「已发送」，会误以为评论已经发出去了。
    delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_xhs_replied_at ON xhs_replies(replied_at);

-- ---------- 机器人运行记录（跨进程/跨重启的状态来源） ----------
-- 以前「这一轮在不在跑」只存在后端内存里，后端一重启就忘，可能启动第二个 Chrome。
-- 这里落库：启动时插一行 state='running'，进程结束后回填 returncode / finished_at。
CREATE TABLE IF NOT EXISTS bot_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT NOT NULL DEFAULT 'xhs',  -- 预留多平台（dy / bili …）
    pid           INTEGER,
    pid_create_ts REAL,        -- 进程创建时间（epoch 秒），用于防 PID 复用误判
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    state         TEXT NOT NULL DEFAULT 'running',  -- running/done/failed/stale/unknown
    returncode    INTEGER,
    params        TEXT,        -- 本轮参数 JSON
    log_path      TEXT
);
-- 同一平台同时只允许一行 running：多 worker / 多次误点也拦得住（靠数据库唯一约束）
CREATE UNIQUE INDEX IF NOT EXISTS uniq_bot_run_running
    ON bot_runs(platform) WHERE state='running';
CREATE INDEX IF NOT EXISTS idx_bot_runs_platform ON bot_runs(platform, id DESC);
