# dev_tools — 一次性调试脚本

这里的脚本都是**排障 / 探针**用，不参与线上运行，也不被后端或机器人 import。
统一在**项目根目录**执行（脚本内部已按 `__file__` 定位 `.chrome-xhs`，不会另建登录态目录）：

```bash
backend/.venv/Scripts/python.exe dev_tools/debug_xhs.py
```

| 脚本 | 用途 |
| --- | --- |
| `debug_xhs.py` | DOM 探针：dump 小红书首页信息流卡片 / 详情页结构，页面改版后先跑它 |
| `debug_xhs2.py` | DOM 探针续：首页滚动加载、卡片选择器批量校验 |
| `debug_comment.py` | 探针：打印评论输入框（`#content-textarea`）与提交按钮的真实 DOM |
| `verify_sent.py` | 复核：打开指定帖子，确认评论区里是否真的出现了我们发的内容 |
| `check_sent.py` | 复核（带 xsec_token 版）：从日志取最近几条已发送链接，逐条打开看评论区 |
| `verify_offline.py` | 验证断连提示：用浏览器离线模式模拟断网，确认提示会出现、且不推挤页面布局 |
| `audit_layout.py` | 布局抖动审计：反复采样关键元素位置，把「页面跳来跳去」量化成像素差 |
| `xhs_automation.py` | 早期 demo 骨架（`--demo` 跑内置样例），现由 `xhs_bot.py` 取代，仅留作参考 |

`_legacy/` 是前端最早的手工打包残留（`_admin.html` / `_app.js` / `_vend.js`），
现前端为 Vue 工程（`frontend/`），这些文件无任何引用，留档备查，可随时删除。

## 常用排查顺序

1. 页面改版、抓不到正文 → `debug_xhs.py` 看卡片与详情选择器
2. 评论发不出去 → `debug_comment.py` 看输入框节点，再用 `verify_sent.py` 复核是否发出
3. 判定异常（该回没回 / 不该回乱回） → 直接调接口验证规则，无需开浏览器：

```bash
curl -s -X POST http://127.0.0.1:8123/api/xhs/assess \
  -H "Content-Type: application/json" \
  -d '{"content":"月租太贵了，流量不够用，有没有便宜点的卡"}'
```
