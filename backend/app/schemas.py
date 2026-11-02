from pydantic import BaseModel
from typing import Optional, List


class StateOut(BaseModel):
    version: int
    configured: bool
    product_count: int = 0
    doc_count: int = 0


class AskReq(BaseModel):
    q: str
    audience: str = "agent"


class AskRes(BaseModel):
    answer: str = ""
    sources: List[dict] = []
    error: str = ""
