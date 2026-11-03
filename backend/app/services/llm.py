"""大模型调用（OpenAI 兼容协议）。

这里是全项目唯一的模型出入口：问答（services/ask.py）、小红书话术（services/xhs.py）、
设置页的连接测试（routers/settings.py）都只经此调用，业务服务之间不再互相 import。

换模型不需要改代码：设置页填 base_url / model / api_key 即可，每次调用都现读 config，
保存后下一条请求生效（无需重启）。若要接 Anthropic / Gemini 的原生协议（非
/chat/completions），只需在 call_llm / call_llm_stream 内部按 base_url 分流，
调用方完全不用动。
"""
import json
import time
import urllib.request
import urllib.error

from .. import config
from . import common

# 单次请求超时（秒）。长文生成留足余量；流式也用它兜住首包。
TIMEOUT = 120
# 429 / 5xx 的重试次数（指数退避，最多 8 秒一次）
RETRIES = 4


def _prepare(cfg=None, stream=False):
    """组装请求：base_url 结尾、body、headers。cfg 为空时读设置页配置。"""
    L = cfg or config.llm_cfg()
    base = (L.get("base_url") or "").rstrip("/")
    body = {
        "model": L.get("model"),
        "messages": None,          # 由调用方填
        "temperature": L.get("temperature", 0.3),
        "max_tokens": L.get("max_tokens", 1200),
    }
    if stream:
        body["stream"] = True
    extra = L.get("extra")
    if isinstance(extra, dict):
        body.update(extra)
    headers = {"Content-Type": "application/json",
               "Authorization": "Bearer " + L.get("api_key", "")}
    return base, body, headers


def call_llm(messages, cfg=None):
    """非流式调用，返回纯文本。429 / 5xx 自动退避重试，其余错误直接抛。"""
    base, body, headers = _prepare(cfg)
    body["messages"] = messages

    last_err = None
    for attempt in range(RETRIES):
        req = urllib.request.Request(
            base + "/chat/completions",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST")
        try:
            with common.urlopen_direct(req, timeout=TIMEOUT) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
            return json.loads(raw.decode())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 or 500 <= e.code < 600:
                wait = min(8.0, 1.0 * (2 ** attempt))
                ra = e.headers.get("Retry-After")
                if ra and str(ra).isdigit():
                    wait = float(ra)
                if attempt < RETRIES - 1:
                    time.sleep(wait)
                    continue
            raise
    raise last_err


def call_llm_stream(messages, cfg=None):
    """流式调用，逐段 yield 文本增量（OpenAI 兼容 SSE）。"""
    base, body, headers = _prepare(cfg, stream=True)
    body["messages"] = messages

    req = urllib.request.Request(base + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    with common.urlopen_direct(req, timeout=TIMEOUT) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
                delta = obj["choices"][0]["delta"].get("content")
                if delta:
                    yield delta
            except Exception:
                continue
