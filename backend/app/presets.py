"""服务商预设：点一下自动填 base_url + model，避免用户填错（尤其 base_url）。"""

PRESETS_LLM = [
    {"name": "智谱 GLM-5.3-Flash（免费）", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "model": "glm-5.3-flash", "extra": {"thinking": {"type": "disabled"}}},
    {"name": "智谱 GLM-5.3-FlashX（更快）", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "model": "glm-5.3-flashx", "extra": {"thinking": {"type": "disabled"}}},
    {"name": "硅基流动", "base_url": "https://api.siliconflow.cn/v1", "model": "deepseek-ai/DeepSeek-V3"},
    {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    {"name": "阿里百炼", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "model": "qwen-plus"},
    {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
]

PRESETS_EMBED = [
    {"name": "智谱 embedding-3（送的 token）", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "model": "embedding-3"},
    {"name": "硅基流动 bge-m3（免费）", "base_url": "https://api.siliconflow.cn/v1",
     "model": "BAAI/bge-m3"},
]
