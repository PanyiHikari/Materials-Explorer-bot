from pydantic import BaseModel
from nonebot import get_driver

class Config(BaseModel):
    mp_api_key: str = ""
    vesta_exec: str = "VESTA"
    image_timeout: int = 30
    search_page_size: int = 10
    deepseek_api_key: str = ""

    # AI 监听灵敏度: strict | normal | loose
    ai_watch_sensitivity: str = "normal"
    ai_watch_keywords: str = ""

    # AI 监听置信度阈值(全局默认, 0-1)
    ai_watch_min_confidence: float = 0.5

    # 思考模式（仅作用于 /mp.ask 的 ask_question）
    ai_ask_thinking: bool = True          # 是否在 ask_question 中启用思考
    ai_ask_reasoning_effort: str = "high" # low / high / max

config = Config.model_validate(get_driver().config.model_dump())