import json
from typing import Optional, Dict, Any, List

from nonebot.log import logger
from openai import AsyncOpenAI

from .config import config

# DeepSeek 客户端(延迟初始化)

_client: Optional[AsyncOpenAI] = None

def _get_client() -> Optional[AsyncOpenAI]:
    global _client
    if _client is None:
        if not config.deepseek_api_key:
            logger.warning("DEEPSEEK_API_KEY 未配置，AI 监听功能不可用")
            return None
        _client = AsyncOpenAI(
            api_key=config.deepseek_api_key,
            base_url="https://api.deepseek.com",
            timeout=15.0,
        )
    return _client


# 工具定义

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "mp_search",
            "description": "在 Materials Project 中搜索晶体材料。当用户想查某个化学式或元素组合的结构时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索条件。用 '-' 连接表示仅含这些元素（如 Si-O），用 ',' 连接表示至少含这些元素（如 Si,O），直接写化学式表示精确匹配（如 YBa2Cu3O7）。",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mp_get_cif",
            "description": "根据 material_id 获取 CIF 文件。当用户明确知道 material_id（如 mp-162）并想要文件时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "material_id": {"type": "string", "description": "材料 ID，如 mp-162"}
                },
                "required": ["material_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mp_prev",
            "description": "渲染晶体结构图片。当用户想要看某个晶体的结构图时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "material_id": {"type": "string", "description": "材料 ID，如 mp-162"},
                    "view": {
                        "type": "string",
                        "description": "晶面参数，如 113、111、011。不填则默认沿 (113) 投影。填 'tri' 表示三视图。",
                    },
                },
                "required": ["material_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mp_res_cif",
            "description": "根据搜索结果中的序号获取 CIF 文件。当用户说'第 N 号的结构'、'N 号的 CIF'时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "搜索结果序号，从 1 开始"}
                },
                "required": ["index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mp_res_prev",
            "description": "渲染搜索结果中指定序号的晶体结构图片。当用户说'N 号的投影'、'第 N 个的结构图'时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "搜索结果序号，从 1 开始"},
                    "view": {
                        "type": "string",
                        "description": "晶面参数，如 122、111。不填则默认沿 (113) 投影。填 'tri' 表示三视图。",
                    },
                },
                "required": ["index"],
            },
        },
    },
]


# 消息过滤

# 跳过 AI
_MP_COMMAND_PREFIXES = ("/mp", "／mp")


def _looks_like_mp_command(text: str) -> bool:
    """判断文本是否是一条 MP 插件指令（如 /mp.search SiO2）"""
    t = text.strip()
    for p in _MP_COMMAND_PREFIXES:
        if t.startswith(p):
            # 排除 /mpxxx（不是 MP 指令）
            rest = t[len(p):]
            if not rest or rest[0] in (".", " ", "\t", "/", "／"):
                return True
    return False


def should_analyze(text: str, is_at_bot: bool) -> bool:
    """
    判断消息是否应该送给 AI 分析。

    规则：
      1. 空消息 -> 跳过
      2. 消息本身就是一条 MP 指令（如 /mp.search SiO2）-> 跳过（由指令机制处理）
      3. @bot 的自然语言消息 -> 送 AI（不受长度限制）
      4. 非 @bot 消息超过 100 字符 -> 跳过
      5. 其余 -> 送 AI
    """
    text = text.strip()
    if not text:
        return False

    # 指令消息直接交给指令响应器
    if _looks_like_mp_command(text):
        return False

    # @bot 的消息不受长度限制
    if is_at_bot:
        return True

    # 非 @bot 且过长 -> 跳过
    if len(text) > 100:
        return False

    return True


# AI 分析

async def analyze_message(text: str) -> Optional[List[Dict[str, Any]]]:
    """
    把消息送给 DeepSeek 分析，返回工具调用列表。

    Returns:
        None 表示 AI 认为消息与晶体查询无关。
        否则返回 list of {"name": "...", "arguments": {...}}
    """
    client = _get_client()
    if client is None:
        return None

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个晶体结构查询助手。分析群聊消息，判断用户是否想查询晶体结构。"
                        "如果用户表达了查询意图，调用相应的工具；否则不要调用任何工具。"
                        "注意：'第 N 号'、'N 号'中的 N 是搜索结果中的序号，对应 mp_res_cif / mp_res_prev 的 index 参数。"
                        "如果用户同时想要 CIF 文件和结构图，可以同时调用 mp_res_cif 和 mp_res_prev。"
                    ),
                },
                {"role": "user", "content": text},
            ],
            tools=TOOLS,
            tool_choice="auto",
        )

        message = response.choices[0].message
        if not message.tool_calls:
            return None

        calls: List[Dict[str, Any]] = []
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                logger.warning(f"AI 返回的 arguments 无法解析: {tc.function.arguments}")
                continue
            calls.append({"name": tc.function.name, "arguments": args})

        return calls if calls else None

    except Exception as e:
        logger.error(f"DeepSeek 调用失败: {e}", exc_info=True)
        return None