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


# 小红书判分与人格的默认值。设置页改的是 config.json 里的 "xhs"，
# 没写的字段一律回落到这里——用户可能只改权重、不动人格。
XHS_DEFAULTS = {
    "min_score": 2,
    "weights": {"办卡意图": 3, "流量需求": 2, "资费敏感": 2,
                "学生校园": 2, "异地流动": 1, "网络体验": 1},
    "tones": {
        "自然分享": "你是一个自己研究过号卡、换过几次卡的普通用户，在小红书顺手回帖，"
                    "语气像真实用户有感而发，亲切自然。",
        "理性数码": "你是懂行的数码博主，在小红书顺手回帖，语气客观、讲参数和性价比，"
                    "像在认真给建议而不是推销。",
        "省钱过来人": "你是精打细算的过来人，在小红书顺手回帖，语气像劝朋友避坑省钱，"
                      "带点生活经验感。",
        "在校学长": "你是在校大学生，在小红书顺手回帖，语气像同校学长学姐分享校园实用经验，"
                    "贴近宿舍 / 校园场景。",
    },
    "default_tone": "自然分享",
    "rotate_tone": True,
}


def _as_int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def xhs_cfg():
    """小红书判定配置：阈值、六类信号权重、人格文案与默认/轮换。

    逐字段校验后返回，脏值（手改坏了 config.json）不会让判分崩掉。
    """
    raw = load_config().get("xhs") or {}
    if not isinstance(raw, dict):
        raw = {}

    weights = {}
    w = raw.get("weights") if isinstance(raw.get("weights"), dict) else {}
    for name, dv in XHS_DEFAULTS["weights"].items():
        weights[name] = max(0, _as_int(w.get(name, dv), dv))

    tones = {}
    t = raw.get("tones") if isinstance(raw.get("tones"), dict) else {}
    for name, dv in XHS_DEFAULTS["tones"].items():
        v = t.get(name)
        tones[name] = v if isinstance(v, str) and v.strip() else dv

    default_tone = raw.get("default_tone")
    if default_tone not in tones:
        default_tone = XHS_DEFAULTS["default_tone"]

    return {
        "min_score": max(0, _as_int(raw.get("min_score"), XHS_DEFAULTS["min_score"])),
        "weights": weights,
        "tones": tones,
        "default_tone": default_tone,
        "rotate_tone": bool(raw.get("rotate_tone", XHS_DEFAULTS["rotate_tone"])),
    }
