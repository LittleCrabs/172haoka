import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "llm": {"base_url": "", "model": "", "api_key": "", "extra": {}},
    "embed": {"base_url": "", "model": "", "api_key": ""},
    "audience": "agent",
}


def load_config():
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def llm_cfg():
    return load_config().get("llm", {})


def embed_cfg():
    c = load_config()
    return c.get("embed") or c.get("embedding") or {}


def is_configured():
    l = llm_cfg()
    return bool(l.get("base_url") and l.get("model") and l.get("api_key"))


# 后台 API（haoka.lot-ml.com）登录与同步所需的配置
def api_base():
    return (load_config().get("api") or "").rstrip("/") + "/"


def site_base():
    return (load_config().get("site") or "").rstrip("/") + "/"


def credentials():
    c = load_config()
    return c.get("username", ""), c.get("password", "")


def get(key, default=None):
    return load_config().get(key, default)


def proxy():
    """网络代理地址（如 http://127.0.0.1:10808）。空 = 用系统默认代理设置。"""
    return (load_config().get("proxy") or "").strip()
