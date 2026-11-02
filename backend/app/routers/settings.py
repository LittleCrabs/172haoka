"""设置 API：配置读写、测试大模型、后台登录（取验证码→填 code）、外挂导入入口。"""
import base64
from fastapi import APIRouter, Body, HTTPException
from .. import config, database
from ..services import common, ask as ask_svc
from ..presets import PRESETS_LLM, PRESETS_EMBED

router = APIRouter(prefix="/api", tags=["settings"])


def _mask(cfg):
    c = dict(cfg)
    # 顶层凭据脱敏：password 是 haoka 后台密码，绝不能明文回传前端
    if c.get("password"):
        c["password"] = "***已配置***"
    # llm / embed 的 api_key 同样脱敏
    for key in ("llm", "embed"):
        if isinstance(c.get(key), dict) and c[key].get("api_key"):
            c[key] = dict(c[key])
            c[key]["api_key"] = "***已配置***"
    return c


@router.get("/settings")
def get_settings():
    return {"config": _mask(config.load_config()),
            "presets": {"llm": PRESETS_LLM, "embed": PRESETS_EMBED}}


@router.post("/settings")
def save_settings(body: dict = Body(...)):
    cur = config.load_config()
    for top in ("llm", "embed"):
        if top in body and isinstance(body[top], dict):
            d = dict(cur.get(top, {}))
            for k, v in body[top].items():
                if k == "api_key" and (v is None or v == ""):
                    continue  # 传空串 = 不改原值
                d[k] = v
            cur[top] = d
    if "audience" in body:
        cur["audience"] = body["audience"]
    # 网络代理 / 后台站点等顶层字段
    for field in ("proxy", "api", "site", "note"):
        if field in body:
            cur[field] = body[field]
    # 顶层凭据：前端回传脱敏串或留空时，保留原值，避免覆盖真实密码
    for field in ("password", "username"):
        if field in body:
            v = body[field]
            if not v or v == "***已配置***":
                body[field] = cur.get(field)
            else:
                cur[field] = v
    config.save_config(cur)
    return {"ok": True}


@router.post("/settings/test-llm")
def test_llm(body: dict = Body(...)):
    save_settings(body)
    cfg = config.llm_cfg()
    if not (cfg.get("base_url") and cfg.get("model") and cfg.get("api_key")):
        raise HTTPException(status_code=400, detail="还没填完整的 LLM 配置")
    try:
        ans = ask_svc.call_llm([
            {"role": "system", "content": "你是测试助手，只回复'可用'两个字。"},
            {"role": "user", "content": "ping"},
        ], cfg)
        return {"ok": True, "reply": (ans or "")[:50]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/captcha")
def captcha():
    try:
        png = common.get_captcha()
        b64 = base64.b64encode(open(png, "rb").read()).decode()
        return {"ok": True, "image": "data:image/png;base64," + b64}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login")
def login(code: dict = Body(...)):
    try:
        ok, d = common.login(code.get("code", ""))
        if not ok:
            raise HTTPException(status_code=400, detail=d or "登录失败")
        return {"ok": True, "user": d}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
