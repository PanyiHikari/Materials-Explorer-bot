import json
from typing import Optional, Dict, Any, List
import re

from nonebot.log import logger
from openai import AsyncOpenAI

from .config import config

import os
from .ask_context import get_context, set_context
from .ask_swt import is_ask_enabled

from .ai_memory import add_turn, get_history

from .min_conf import get_min_confidence

# DeepSeek 客户端(延迟初始化)

_client: Optional[AsyncOpenAI] = None

def _get_client() -> Optional[AsyncOpenAI]:
    global _client
    if _client is None:
        if not config.deepseek_api_key:
            logger.warning("DEEPSEEK_API_KEY 未配置, AI 监听功能不可用")
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
            "description": (
                "在 Materials Project 中搜索晶体材料。当用户想查某个化学式、元素组合，"
                "或者**某个物质名称/俗名/别名（如'萤石'、'石英'、'金红石'）**时使用。"
                "**如果用户使用的是物质名称/别名，必须原样作为 query 传递，"
                "不要翻译为化学式**——插件会自动查别名字典并返回对应的晶体列表。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "搜索条件。用 '-' 连接表示仅含这些元素（如 Si-O），"
                            "用 ',' 连接表示至少含这些元素（如 Si,O），"
                            "直接写化学式表示精确匹配（如 YBa2Cu3O7），"
                            "或者直接写物质别名（如 '萤石'）。"
                        ),
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
    {
        "type": "function",
        "function": {
            "name": "mp_search_for_ask",
            "description": (
                "在 Materials Project 中搜索晶体材料，用于 /mp.ask 问答过程中需要"
                "定位某个晶体的场景。当问题中指定了一个与当前晶体不同的化学式、"
                "元素组合，或者**某个物质名称/俗名/别名（如'萤石'、'石英'、'金红石'）**时使用。"
                "**如果用户使用的是物质名称/别名，必须原样作为 formula 参数传递，"
                "不要翻译为化学式，不要替换为其他名称**——插件会自动查别名字典并返回"
                "对应的晶体列表，再由用户从中选择。"
                "注意：调用本工具后，程序会发送'你要查以下哪个晶体？'和搜索结果，"
                "并中止本轮问答等待用户选择，因此不要在调用本工具后继续生成最终回答。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "formula": {
                        "type": "string",
                        "description": (
                            "搜索条件。支持以下写法："
                            "1) 用 '-' 连接表示仅含这些元素，如 'Si-O'、'Li-Fe-P-O'；"
                            "2) 用 ',' 连接表示至少含这些元素，如 'Si,O'、'Fe,Co,Ni'；"
                            "3) 直接写化学式表示精确匹配，如 'YBa2Cu3O7'、'CaF2'；"
                            "4) 直接写物质名称/俗名/别名（原样传递，不要翻译），"
                            "如 '萤石'、'石英'、'金红石'。"
                        ),
                    }
                },
                "required": ["formula"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mp_prev_for_ask",
            "description": "为当前晶体渲染沿指定晶面的投影图，用于回答对称元素位置等问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "material_id": {"type": "string"},
                    "view": {"type": "string", "description": "晶面参数，如 001、111"},
                },
                "required": ["material_id", "view"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_question",
            "description": (
                "回答晶体学与材料学的问答类问题，例如'属于什么晶系'、"
                "'4 次旋转轴在哪里'、'为什么具有这个对称性'。"
                "会先获取结构数据再综合分析。对于纯查询类操作"
                "（如'查 SiO2'、'发 mp-162 的 CIF'）不要用这个，直接用其他工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用户的原始问题",
                    }
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mp_add_alias",
            "description": (
                "把别名关联到某个 mp ID。当用户说'记住 X 就是 mp-xxx'、"
                "'X 的 ID 是 mp-xxx'、'以后 X 就查 mp-xxx'时使用。"
                "若不填 material_id，则使用本群最近查询的晶体。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "alias": {"type": "string", "description": "别名，如'石英'"},
                    "material_id": {"type": "string", "description": "mp ID，如 mp-6930"},
                },
                "required": ["alias"],
            },
        },
    },
]

def _inject_confidence(tool: dict) -> dict:
    """为每个工具自动添加 confidence 参数，要求 AI 返回置信度"""
    params = tool["function"]["parameters"]
    params.setdefault("properties", {})["confidence"] = {
        "type": "number",
        "description": (
            "你对该次工具调用的信心，范围 0-1。"
            "0.9 及以上: 用户意图明确，几乎确定；"
            "0.7-0.9: 很可能正确；"
            "0.5-0.7: 只是猜测；"
            "低于 0.5: 不确定，最好不调用。"
        ),
    }
    if "required" not in params:
        params["required"] = []
    if "confidence" not in params["required"]:
        params["required"].append("confidence")
    return tool


TOOLS = [_inject_confidence(t) for t in TOOLS]


# 消息过滤

# 跳过 AI
_MP_COMMAND_PREFIXES = ("/mp", "／mp")


def _looks_like_mp_command(text: str) -> bool:
    """判断文本是否是一条 MP 插件指令（如 /mp.search SiO2）"""
    t = text.strip()
    for p in _MP_COMMAND_PREFIXES:
        if t.startswith(p):
            rest = t[len(p):]
            if not rest or rest[0] in (".", " ", "\t", "/", "／"):
                return True
    return False

def _get_alias_hint(text: str) -> str:
    """
    扫描文本中出现的所有别名，生成一段提示，附加到 system prompt 中。
    目的是让 AI 知道这些词是别名，调用 mp_search 时必须原样传递，
    而不是翻译成化学式（如"萤石"→"CaF2"）。
    """
    from .alias_dict import all_aliases

    aliases = all_aliases()
    if not aliases:
        return ""

    text_lower = text.lower()
    hits = [a for a in aliases if a and a.lower() in text_lower]
    if not hits:
        return ""

    hit_str = "、".join(f"「{h}」" for h in hits)
    return (
        f"\n\n**重要提示**：用户消息中出现了别名字典中的词 {hit_str}。"
        "调用 mp_search 或 mp_search_for_ask 时，必须把这些别名**原样**作为 "
        "query / formula 参数传递，**不要翻译为化学式，不要替换为其他名称**。"
        "插件会自动查别名字典并返回对应的晶体列表。"
    )

# 内置关键词：覆盖常见查询/问答表达
_DEFAULT_KEYWORDS = (
    # 动作
    "查", "找", "搜", "看", "问", "告诉", "给", "发", "要", "为什么", "在哪",
    # 对象
    "晶体", "结构", "cif", "CIF", "mp-", "材料",
    # 参数与属性
    "晶胞", "参数", "晶格", "坐标", "原子", "空间群", "点群",
    "晶系", "对称", "投影", "晶面", "配位", "多面体",
    "带隙", "能带", "态密度", "衍射", "xrd", "XRD",
    "晶族", "旋转", "反轴", "映轴", "螺旋轴", "镜面", 
    "反映", "反演", "滑移", "次轴", "键长", "原子", "间距",
    # 指代
    "这个", "那个", "它", "第", "号",
    # 字典
    "别名", "记住", "关联", "俗称",
)


def _get_all_keywords() -> tuple:
    from .config import config
    custom = [
        k.strip()
        for k in config.ai_watch_keywords.split(",")
        if k.strip()
    ]
    return _DEFAULT_KEYWORDS + tuple(custom)


def _has_keyword(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in _get_all_keywords())


def should_analyze(
    text: str,
    is_at_bot: bool,
    has_context: bool = False,
) -> bool:
    """
    判断消息是否应该送给 AI 分析。

    规则按 ai_watch_sensitivity 分三档：

    strict:
      - 必须 @bot
      - 必须命中关键词
      - 长度 ≤ 200

    normal (默认):
      - @bot 的消息直接送(长度 ≤ 200)
      - 非 @bot 的消息须命中关键词且 ≤ 100 字符
      - 若本群无查询上下文(has_context=False), 非 @bot 消息须同时命中
        mp-\\d+ 或关键词，以过滤纯闲聊

    loose:
      - @bot 全送
      - 非 @bot 且 ≤ 100 字符全送
    """
    text = text.strip()
    if not text:
        return False

    # 指令消息直接交给指令响应器
    if _looks_like_mp_command(text):
        return False

    from .config import config
    mode = config.ai_watch_sensitivity.lower()

    if mode == "loose":
        if is_at_bot:
            return True
        return len(text) <= 100

    if mode == "strict":
        if not is_at_bot:
            return False
        if len(text) > 200:
            return False
        return _has_keyword(text)

    # normal（默认）
    if is_at_bot:
        return len(text) <= 200
    if len(text) > 100:
        return False
    if not _has_keyword(text):
        return False
    # 无上下文时，非 @bot 消息还须包含 mp-\d+ 才放行，避免"这个怎么样"类闲聊
    if not has_context:
        import re
        if re.search(r"mp-\d+", text, re.IGNORECASE) is None:
            return False
    return True


# AI 分析

async def analyze_message(
    text: str,
    group_id: str = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    把消息送给 DeepSeek 分析，返回工具调用列表。
    每次调用都会读取当前群的有效置信度阈值并过滤低置信度的工具调用。
    """
    client = _get_client()
    if client is None:
        return None

    # 读取阈值
    # 优先取群级配置（/mp.minconf 写入），否则用 config 里的全局默认值
    from .config import config
    threshold = get_min_confidence(group_id) if group_id else config.ai_watch_min_confidence

    try:
        system_content = (
            "你是一个晶体结构查询助手。分析群聊消息，判断用户是否想查询晶体结构。\n\n"
            "**判断原则（重要）**：\n"
            "1. 仅在用户消息**明确表达**晶体结构查询或晶体学问答意图时才调用工具。\n"
            "2. 如果消息是闲聊、表情、对 bot 的赞美/吐槽、或其他 bot 的输出，"
            "**不要调用任何工具**。\n"
            "3. 如果消息需要大量推测才能理解为查询，**不要调用任何工具**。\n"
            "4. 不确定时倾向于**不调用**——宁可漏一次，不要误触发。\n\n"
            "**关于 confidence 参数**：\n"
            "每个工具调用必须附带 confidence 参数（0-1），表示你对该调用的信心。"
            "系统会根据当前群的阈值过滤低置信度的调用。\n\n"
            "其余规则：\n"
            "- '第 N 号'、'N 号' 中的 N 是搜索结果序号，对应 mp_res_cif / mp_res_prev 的 index。\n"
            "- 简短追问（'那它呢''第二个呢'）可以结合历史理解，但若历史中无相关晶体，则不调用。\n"
            "- 对于晶体学问答类问题（'属于什么晶系''4 次轴在哪里'），调用 ask_question。\n"
        )
        # 别名提示（保留之前的逻辑）
        system_content += _get_alias_hint(text)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_content}
        ]

        # 注入最近 3 轮历史
        if group_id:
            for turn in get_history(group_id, max_turns=3):
                messages.append({"role": "user", "content": turn.user})
                messages.append({"role": "assistant", "content": turn.assistant})

        messages.append({"role": "user", "content": text})

        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            reasoning_effort="none",
        )

        message = response.choices[0].message
        if not message.tool_calls:
            return None

        # 过滤低置信度调用
        calls: List[Dict[str, Any]] = []
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                logger.warning(f"AI 返回的 arguments 无法解析: {tc.function.arguments}")
                continue

            # 取出 confidence 并从 args 中删除，避免传给业务函数
            # 默认 1.0: AI 既然调用了工具，视为较高信心
            conf_raw = args.pop("confidence", 1.0)
            try:
                conf = float(conf_raw)
            except (TypeError, ValueError):
                conf = 1.0

            if conf < threshold:
                logger.info(
                    f"[AI-WATCH] 丢弃低置信度调用: {tc.function.name} "
                    f"conf={conf:.2f} < threshold={threshold:.2f} "
                    f"args={args}"
                )
                continue

            calls.append({"name": tc.function.name, "arguments": args})

        return calls if calls else None

    except Exception as e:
        logger.opt(exception=e).error("DeepSeek 调用失败")
        return None

_VERBOSE_KEYWORDS = ("详细", "展开", "详述", "深入", "推理过程", "逐步", "理由", "原因")

def _build_ask_kwargs() -> dict:
    """
    根据配置构造 ask_question 的 DeepSeek 调用参数。
    """
    from .config import config

    kwargs = {
        "model": "deepseek-flash",   
        "tools": TOOLS,
        "tool_choice": "auto",
    }

    if config.ai_ask_thinking:
        kwargs["reasoning_effort"] = config.ai_ask_reasoning_effort
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    else:
        # 显式关闭，避免继承服务端默认的“思考开启”
        kwargs["reasoning_effort"] = "none"

    return kwargs

async def ask_question(bot, event, question: str):
    """回答晶体学/材料学问题。安全处理 ctx 为空的情况。"""
    from . import (
        _get_group_id,
        search_materials,
        set_cache,
        clear_cache,
        _send_vesta_image,
    )
    from .ask_context import get_context
    from .ask_swt import is_ask_enabled
    from .mp_api import get_structure_info, get_cif

    group_id = _get_group_id(event)
    if not is_ask_enabled(group_id):
        await bot.send(event, "/mp.ask 指令已禁用")
        return

    ctx = get_context(group_id)

    # 1. 确定目标晶体
    material_id_match = re.search(r"mp-\d+", question)
    explicit_mid = material_id_match.group(0) if material_id_match else None

    if explicit_mid:
        target_mid = explicit_mid
    elif ctx is not None:
        target_mid = ctx.material_id
    else:
        target_mid = None

    # 2. 构造当前晶体数据段
    if target_mid is None:
        current_section = (
            "### 当前晶体: 无\n"
            "用户未指定 material_id，且无历史上下文。"
            "请根据用户问题中提到的化学式调用 mp_search_for_ask 搜索并询问用户。"
        )
    else:
        structure_data = await get_structure_info(target_mid)
        if structure_data:
            current_section = _format_structure_for_prompt(structure_data)
        else:
            # CIF 兜底
            current_section = f"### 当前晶体: {target_mid}\n"
            try:
                cif_text = await get_cif(target_mid)
                if cif_text:
                    from pymatgen.core import Structure as PmgStructure
                    st = PmgStructure.from_str(cif_text, fmt="cif")
                    current_section += (
                        f"- 化学式: {st.composition.reduced_formula}\n"
                        f"- 晶胞: a={st.lattice.a:.4f}, b={st.lattice.b:.4f}, "
                        f"c={st.lattice.c:.4f}, α={st.lattice.alpha:.2f}°, "
                        f"β={st.lattice.beta:.2f}°, γ={st.lattice.gamma:.2f}°\n"
                        f"- 原子数: {len(st)}\n"
                        "（注：结构信息 API 获取失败，以下数据来自 CIF 解析。）"
                    )
                else:
                    current_section += "（结构数据获取失败。）"
            except Exception as e:
                logger.opt(exception=e).warning("CIF 兜底解析失败")
                current_section += "（结构数据获取失败。）"

    # ---------- 3. 构造 system prompt ----------
    skill_text = _load_skill_text()

    want_detail = any(k in question for k in _VERBOSE_KEYWORDS)

    if want_detail:
        length_rule = (
            "**回答长度**：用户希望详细解释。请分点展开，给出推理依据，"
            "但避免罗列原始数据表格。"
        )
    else:
        length_rule = (
            "**回答长度**：默认用 1–2 句话直接给出结论，"
            "不要展开推导、不要列出数据表、不要加客套结尾。"
            "仅当用户明确要求详细时才展开。"
        )

    system_prompt = (
        "你是一个晶体学与材料学专家。根据下面的晶体数据和参考资料回答问题。\n\n"
        "**回答长度**（重要）：\n"
        "- **默认用 1–2 句话直接给出结论**，例如：\"四方晶系（空间群 P4₂/mnm，点群 4/mmm）。\"\n"
        "- 问\"为什么\"时，只给**核心原因**（1–2 句），不展开推导过程。\n"
        "- **仅当用户明确要求**（如\"详细解释\"、\"展开说明\"、\"为什么……请详述\"、\"写出推理过程\"）时，"
        "才给出多段详细说明。\n"
        "- 不要在回答里重复列出晶胞参数表或原子坐标表，这些数据你已经看过，"
        "只在需要佐证结论时引用关键数字。\n"
        "- 除非用户要求，不要附\"参考资料\"、\"注：\"、\"如需更多信息请……\"这类结尾。\n\n"
        "**数据规则**：\n"
        "1. 所有定量参数（晶胞参数、原子坐标、空间群、点群）必须来自下面的结构数据，"
        "或通过调用 mp_get_structure_info 工具获取，**不得猜测**。\n"
        "2. 如果问题涉及对称元素的位置（例如'4 次轴在哪里'），必须调用 "
        "mp_prev_for_ask 工具，沿该对称元素的晶向渲染投影图，"
        "并在文字回答中说明投影方向。\n"
        "3. 如果问题中指定了一个与当前晶体不同的化学式，"
        "必须先调用 mp_search_for_ask 搜索，然后询问用户选择哪一个结果。\n"
        "4. 如果问题中明确提到 material_id（如 mp-390），"
        "必须调用 mp_get_structure_info(material_id) 获取该晶体的数据。\n"
        "5. 如果当前晶体为'无'且问题中没有明确 material_id，"
        "根据化学式调用 mp_search_for_ask。\n"
        "6. 如果问题中使用'它'、'这个晶体'、'刚才那个'等指代词，"
        "请结合上文对话历史理解指代对象。\n\n"
        f"{current_section}\n\n"
        f"## 参考资料\n{skill_text}"
    )
    # 别名提示
    system_prompt += _get_alias_hint(question)

    # 4. 构造 message, 含历史

    messages = [{"role": "system", "content": system_prompt}]

    # 注入本群历史（最多 10 轮）
    for turn in get_history(group_id):
        messages.append({"role": "user", "content": turn.user})
        messages.append({"role": "assistant", "content": turn.assistant})

    messages.append({"role": "user", "content": question})

    # 5. 多轮工具循环调用

    client = _get_client()
    if client is None:
        await bot.send(event, "AI 服务未配置，请检查 DEEPSEEK_API_KEY。")
        return

    for _ in range(5):
        try:
            response = await client.chat.completions.create(
                messages=messages,
                **_build_ask_kwargs(),
            )
        except Exception as e:
            logger.opt(exception=e).error("DeepSeek 调用失败")
            await bot.send(event, "AI 分析失败，请稍后再试。")
            return

        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            if msg.content:
                await bot.send(event, msg.content)
                add_turn(group_id, question, msg.content)
            return

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": "参数解析失败",
                })
                continue

            if name == "mp_prev_for_ask":
                try:
                    await _send_vesta_image(
                        bot, event, args["material_id"], args["view"]
                    )
                    tool_result = f"已发送 {args['material_id']} 沿 {args['view']} 的投影图。"
                except Exception as e:
                    logger.opt(exception=e).error("mp_prev_for_ask 失败")
                    tool_result = f"投影渲染失败: {type(e).__name__}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

            elif name == "mp_search_for_ask":
                formula = args.get("formula", "").strip()
                if not formula:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "化学式为空",
                    })
                    continue
                from .mp_api import resolve_search
                clear_cache(group_id)
                results, hit_alias = await resolve_search(formula, num_results=50)
                if not results:
                    await bot.send(event, f"未找到化学式 {formula} 的晶体。")
                    return
                cache = set_cache(group_id, results, formula)
                if hit_alias:
                    await bot.send(event, f"命中别名字典「{formula}」，共 {len(results)} 个条目：")
                await bot.send(event, "你要查以下哪个晶体？")
                await bot.send(event, cache.format_page())
                return

            elif name == "mp_get_structure_info":
                mid = args.get("material_id", "").strip()
                data = await get_structure_info(mid) if mid else None
                if data:
                    tool_result = _format_structure_for_prompt(data)
                else:
                    tool_result = f"无法获取 {mid} 的结构数据。"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"未知工具: {name}",
                })

    await bot.send(event, "暂时无法确定答案呢, 请尝试更具体地描述问题喵")

def _load_skill_text() -> str:
    skill_path = os.path.join(os.path.dirname(__file__), "crystallography_skill.md")
    if os.path.exists(skill_path):
        with open(skill_path, "r", encoding="utf-8") as f:
            return f.read()
    return "（晶体学参考资料未找到，请根据通用知识回答。）"

def _format_structure_for_prompt(data: dict) -> str:
    """
    把 get_structure_info() 返回的结构信息 dict 格式化为可读文本，
    用于拼入 system prompt 或作为 tool 调用结果回传给 AI。
    """
    lines: list[str] = []

    # 1. 基本信息
    lines.append(f"### 结构数据: {data.get('material_id', '?')}")
    formula = data.get("full_formula") or data.get("formula") or ""
    if formula:
        lines.append(f"- 化学式: {formula}")
    if "nsites" in data:
        lines.append(f"- 晶胞内原子数: {data['nsites']}")

    # 2. 晶胞参数
    lat = data.get("lattice")
    if lat:
        lines.append(
            f"- 晶胞参数: a={lat.get('a')} Å, b={lat.get('b')} Å, c={lat.get('c')} Å, "
            f"α={lat.get('alpha')}°, β={lat.get('beta')}°, γ={lat.get('gamma')}°, "
            f"V={lat.get('volume')} Å³"
        )

    # 3. 对称性
    if data.get("spacegroup_symbol"):
        sg_num = data.get("spacegroup_number", "?")
        lines.append(f"- 空间群: {data['spacegroup_symbol']} (No. {sg_num})")
    if data.get("point_group"):
        lines.append(f"- 点群: {data['point_group']}")
    if data.get("crystal_system"):
        lines.append(f"- 晶系: {data['crystal_system']}")

    # 4. 物性
    for key, label in (
        ("density", "密度 (g/cm³)"),
        ("band_gap", "带隙 (eV)"),
        ("is_stable", "热力学稳定"),
    ):
        if key in data and data[key] is not None:
            lines.append(f"- {label}: {data[key]}")

    # 5. 原子位点表
    sites = data.get("sites") or []
    if sites:
        lines.append("")
        lines.append("原子位点（分数坐标）:")
        lines.append("| 元素/占位 | x | y | z |")
        lines.append("| --- | --- | --- | --- |")

        for s in sites:
            coords = s.get("fractional_coords") or [0.0, 0.0, 0.0]
            x = coords[0] if len(coords) > 0 else 0.0
            y = coords[1] if len(coords) > 1 else 0.0
            z = coords[2] if len(coords) > 2 else 0.0

            species = s.get("species")
            if isinstance(species, dict) and species:
                if len(species) == 1:
                    # 有序位点：只显示元素名；若占位率 < 1，附带数值
                    el, occ = next(iter(species.items()))
                    if occ is None or float(occ) >= 0.999:
                        species_text = str(el)
                    else:
                        species_text = f"{el}:{float(occ):.2f}"
                else:
                    # 无序位点：显示所有元素及占位率
                    species_text = " / ".join(
                        f"{el}:{float(occ):.2f}"
                        for el, occ in species.items()
                        if occ is None or float(occ) > 1e-6
                    )
            else:
                # 旧格式 fallback
                el = s.get("element", "?")
                occ = s.get("occupancy", 1.0)
                if occ is None or float(occ) >= 0.999:
                    species_text = str(el)
                else:
                    species_text = f"{el}:{float(occ):.2f}"

            lines.append(f"| {species_text} | {x} | {y} | {z} |")

    return "\n".join(lines)