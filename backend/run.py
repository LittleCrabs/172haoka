"""统一启动入口：关闭 uvicorn 日志的 ANSI 颜色。

uvicorn 默认给日志上色（INFO 绿色、请求加粗）。当输出被重定向到文件、
IDE 输出面板或某些日志视图时，这些颜色控制符不会被渲染，就会显示成
[32mINFO[0m 这类"乱码"。这里把 use_colors 关掉，日志就是纯文本。

用法：
    cd haoka/backend
    .venv/Scripts/python.exe run.py
"""
import copy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

LOG_CONFIG = copy.deepcopy(LOGGING_CONFIG)
for _name in ("default", "access"):
    LOG_CONFIG["formatters"][_name]["use_colors"] = False

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8123,
        log_config=LOG_CONFIG,
    )
