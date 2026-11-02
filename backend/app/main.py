from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import database, config
from .schemas import StateOut
from .routers import products, kb, ask, settings, kuanpro, xhs

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(title="172号卡辅助平台", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(kuanpro.router)
app.include_router(kb.router)
app.include_router(ask.router)
app.include_router(xhs.router)
app.include_router(settings.router)


@app.get("/api/state", response_model=StateOut)
def state():
    conn = database.get_conn()
    try:
        p = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()
        d = conn.execute("SELECT COUNT(*) AS c FROM kb_docs").fetchone()
    finally:
        conn.close()
    return StateOut(
        version=1,
        configured=config.is_configured(),
        product_count=p["c"] if p else 0,
        doc_count=d["c"] if d else 0,
    )


@app.get("/api/health")
def health():
    return {"ok": True}


# ---- 前端静态托管（联调/生产单进程） ----
# 前端构建产物存在时，由 mount 处理 "/" 与 SPA 深链回退；
# 不存在时（开发期用 Vite dev server）给个提示，API 路由已在前方注册、不受影响。
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
else:
    @app.get("/")
    def index():
        return {"ok": True, "hint": "前端尚未构建，请访问 /docs 使用 API 或运行前端 dev server"}
