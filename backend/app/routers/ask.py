"""问答 API。"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import config
from ..services import ask as ask_svc

router = APIRouter(prefix="/api", tags=["ask"])


class AskIn(BaseModel):
    q: str
    audience: str = "agent"
    dry_run: bool = False


def _sse(obj):
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


@router.post("/ask")
def do_ask(req: AskIn):
    return ask_svc.ask(req.q, dry_run=req.dry_run, audience=req.audience)


@router.post("/ask/stream")
def do_ask_stream(req: AskIn):
    """流式问答：先推 sources，再逐段推 delta，最后 [DONE]。"""
    system, user, sources = ask_svc.build_prompt(req.q, req.audience)

    def gen():
        yield _sse({"type": "sources", "sources": sources})
        if not config.llm_cfg().get("api_key"):
            yield _sse({"type": "error",
                        "error": "未配置大模型（请在设置页填写 LLM 的 base_url / model / api_key）"})
            yield "data: [DONE]\n\n"
            return
        try:
            messages = [{"role": "system", "content": system},
                        {"role": "user", "content": user}]
            for delta in ask_svc.call_llm_stream(messages):
                yield _sse({"type": "delta", "content": delta})
        except Exception as e:
            yield _sse({"type": "error", "error": str(e)})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
