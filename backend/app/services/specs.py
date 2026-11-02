"""从详情页文本解析流量结构：总流量 / 通用 / 定向 / 夜间。

口径（避免自我欺骗）：
  * total_gb 优先取接口 data_gb，接口没给才用 通用+定向+夜间 求和。
  * general_gb 解析不出来就留 NULL，不拿 total 顶替。
  * 解析结果是派生数据，存 product_specs（不与 products 混），由 rebuild() 幂等全量重算。
"""
import datetime as dt
import json
import re
from .. import database

_NUM = r"(\d+(?:\.\d+)?)\s*"
_UNIT = r"(?:GB|G|gb|g)(?![a-zA-Z])"
_SCOPE = r"(?:国内|全国|省内|市内|本地|全省|全区)?"

RE_NIGHT = re.compile(_NUM + _UNIT + r"\s*" + _SCOPE + r"\s*(?:夜间|闲时)")
RE_WINDOW = re.compile(r"(\d{1,2})\s*[点时]\s*(?:至|到|-|~)\s*(?:次日)?\s*(\d{1,2})\s*[点时]")
RE_DIR = re.compile(_NUM + _UNIT + r"\s*" + _SCOPE + r"\s*[^，。；、+＋\s]{0,6}定向(?:流量)?")
RE_GEN = (
    re.compile(_NUM + _UNIT + r"\s*" + _SCOPE + r"\s*通用"),
    re.compile(_NUM + _UNIT + r"\s*" + _SCOPE + r"\s*流量"),
    re.compile(_NUM + _UNIT + r"\s*流量"),
)
RE_GEN_CHAIN = re.compile(
    _NUM + _UNIT + r"\s*" + _SCOPE + r"\s*通用"
    r"(?:\s*[+＋]\s*" + _NUM + _UNIT + r"\s*" + _SCOPE + r"\s*通用)+")
RE_DIR_CHAIN = re.compile(
    _NUM + _UNIT + r"\s*" + _SCOPE + r"\s*[^，。；、+＋\s]{0,6}定向(?:流量)?"
    r"(?:\s*[+＋]\s*" + _NUM + _UNIT + r"\s*" + _SCOPE +
    r"\s*[^，。；、+＋\s]{0,6}定向(?:流量)?)+")

TEXT_FIELDS = ("优惠详情", "主套餐", "产品套餐")


def _nums(pat, text):
    return [float(m.group(1)) for m in pat.finditer(text)]


def _gen_gb(text, pat, chain_pat=RE_GEN_CHAIN):
    cands = _nums(pat, text)
    for m in chain_pat.finditer(text):
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", m.group(0))]
        if len(nums) > 1:
            cands.append(sum(nums))
    return max(cands) if cands else None


def _pick(pat, text):
    vals = _nums(pat, text)
    return max(vals) if vals else None


def _evidence(text, needle_num, pat):
    if needle_num is None:
        return ""
    for m in pat.finditer(text):
        if float(m.group(1)) == needle_num:
            s = max(0, m.start() - 30)
            return re.sub(r"\s+", " ", text[s:m.end() + 30]).strip()
    return ""


def extract(sections, remark, name, data_gb, category):
    out = {"total_gb": data_gb, "general_gb": None, "directional_gb": None,
           "night_gb": None, "night_window": None, "source": "", "evidence": ""}

    cands = []
    for k in TEXT_FIELDS:
        v = sections.get(k)
        if isinstance(v, str) and v.strip():
            cands.append((k, v))
    if remark:
        cands.append(("remark", remark))
    if name:
        cands.append(("product_name", name))

    for src, text in cands:
        night = _pick(RE_NIGHT, text)
        gen = None
        for pat in RE_GEN[:2]:
            v = _gen_gb(text, pat)
            if v is not None and (gen is None or v > gen):
                gen = v
        if gen is None:
            gen = _gen_gb(text, RE_GEN[2])
        dir_ = _gen_gb(text, RE_DIR, RE_DIR_CHAIN)

        if night is None and gen is None and dir_ is None:
            continue

        out["general_gb"] = gen
        out["directional_gb"] = dir_
        out["night_gb"] = night
        out["source"] = src

        if night is not None:
            out["evidence"] = _evidence(text, night, RE_NIGHT)
            m = RE_WINDOW.search(text)
            if m:
                out["night_window"] = "%02d:00-%02d:00" % (int(m.group(1)), int(m.group(2)))
        elif gen is not None:
            for p in RE_GEN:
                out["evidence"] = _evidence(text, gen, p)
                if out["evidence"]:
                    break
            if not out["evidence"]:
                m = RE_GEN_CHAIN.search(text)
                if m:
                    s = max(0, m.start() - 20)
                    out["evidence"] = re.sub(r"\s+", " ", text[s:m.end() + 20]).strip()
        elif dir_ is not None:
            out["evidence"] = _evidence(text, dir_, RE_DIR)
        break

    scope = sections.get("定向范围")
    if out["directional_gb"] is None and isinstance(scope, str) \
            and scope.strip() in ("无", "无。", "-"):
        out["directional_gb"] = 0.0

    parts = [v for v in (out["general_gb"], out["directional_gb"], out["night_gb"]) if v]
    total = out["total_gb"]
    if parts:
        s = sum(parts)
        total = max(total or 0, s)
    out["total_gb"] = total
    return out


def rebuild(conn=None):
    """全量重算 product_specs。幂等，可反复跑。依赖 product_details 表（sections JSON）。"""
    own = conn is None
    conn = conn or database.get_conn()
    try:
        rows = conn.execute(
            "SELECT p.product_id, p.product_name, p.category, p.data_gb, p.remark, "
            "d.sections FROM products p "
            "LEFT JOIN product_details d ON d.product_id = p.product_id").fetchall()
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n = 0
        for r in rows:
            try:
                secs = json.loads(r["sections"] or "{}")
            except Exception:
                secs = {}
            if not isinstance(secs, dict):
                secs = {}
            s = extract(secs, r["remark"], r["product_name"], r["data_gb"], r["category"])
            conn.execute(
                "INSERT OR REPLACE INTO product_specs"
                "(product_id,total_gb,general_gb,directional_gb,night_gb,"
                " night_window,source,evidence,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (r["product_id"], s["total_gb"], s["general_gb"], s["directional_gb"],
                 s["night_gb"], s["night_window"], s["source"], s["evidence"], now))
            n += 1
        conn.commit()
        return n
    finally:
        if own:
            conn.close()
