"""后台 API 的公共依赖：token 管理、HTTP（带 gzip）、H5 域名获取。"""
import json
import gzip
import urllib.request
import urllib.error
from pathlib import Path
from .. import database, config

PROJECT_DIR = database.PROJECT_DIR
TOKEN_FILE = PROJECT_DIR / "token.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _opener():
    """配置了 proxy 就用它（如 http://127.0.0.1:10808）；否则走系统默认代理设置。"""
    p = config.proxy()
    if p:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": p, "https": p}))
    return urllib.request.build_opener()


# LLM / Embedding 等第三方 API 不走代理，直连
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def urlopen(req, timeout=30):
    return _opener().open(req, timeout=timeout)


def urlopen_direct(req, timeout=30):
    """直连，不经过任何代理。用于第三方 API（智谱/硅基流动等）。"""
    return _DIRECT_OPENER.open(req, timeout=timeout)


class TokenExpired(Exception):
    pass


def token():
    if not TOKEN_FILE.exists():
        raise TokenExpired("没有 token.json，请先登录后台")
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["token"]


def api(path, data=None, method=None, retries=2):
    """调用后台 API，自动带 token；401/403 抛 TokenExpired。"""
    url = path if path.startswith("http") else config.api_base() + path.lstrip("/")
    headers = {
        "User-Agent": UA,
        "Origin": config.site_base().rstrip("/"),
        "Referer": config.site_base() + "login.html",
        "Accept-Encoding": "gzip",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    headers["Authorization"] = "bearer " + token()

    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise TokenExpired("token 已过期或被拒绝（HTTP %s）" % e.code)
            last = e
        except Exception as e:  # 网络抖动重试
            last = e
    raise RuntimeError("请求失败 %s: %s" % (url, last))


def api_public(path, data=None, method=None):
    url = path if path.startswith("http") else config.api_base() + path.lstrip("/")
    headers = {
        "User-Agent": UA,
        "Origin": config.site_base().rstrip("/"),
        "Referer": config.site_base() + "login.html",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urlopen(req, timeout=30) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8", "replace"))


def h5_base(conn=None, refresh=False):
    """取本账号的 H5 落地页域名（api/HaoKa/H5Dns）。按账号下发且会变，每次现取。"""
    own = conn is None
    conn = conn or database.get_conn()
    base = None if refresh else database.get_meta(conn, "h5_base")
    if not base:
        res = api("api/HaoKa/H5Dns")
        if res.get("code") != 0 or not res.get("data"):
            raise RuntimeError("取 H5 域名失败: %s" % res)
        base = res["data"].rstrip("/")
        database.set_meta(conn, "h5_base", base)
    if own:
        conn.close()
    return base


def get_captcha():
    import base64
    res = api_public("api/User/ImgCode")
    if res.get("code") != 0:
        raise RuntimeError("验证码获取失败: %s" % res)
    b64 = res["data"].split(",", 1)[-1]
    png = PROJECT_DIR / "captcha.png"
    png.write_bytes(base64.b64decode(b64))
    return str(png)


def login(code):
    user, pwd = config.credentials()
    res = api_public("api/User/Login", method="POST",
                     data={"UserName": user, "PassWord": pwd, "Code": code})
    if res.get("code") != 0:
        return False, res.get("message")
    d = res["data"]
    TOKEN_FILE.write_text(json.dumps({"token": d["token"], "user": d}, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    return True, d
