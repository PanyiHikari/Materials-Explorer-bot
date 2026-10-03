from pydantic import BaseModel
from nonebot import get_driver

class Config(BaseModel):
    mp_api_key: str = ""
    vesta_exec: str = "VESTA"
    image_timeout: int = 30
    search_page_size: int = 10

config = Config.model_validate(get_driver().config.model_dump())