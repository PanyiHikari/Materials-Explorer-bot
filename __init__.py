from nonebot import on_command, on_message, require
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, Message, MessageSegment
)
from nonebot.params import CommandArg, RegexGroup
from nonebot.typing import T_State
from nonebot.log import logger
from nonebot.plugin import PluginMetadata
import re
import os
import tempfile

from .config import config
from .mp_api import get_cif, search_materials
from .render_vesta import render_crystal_vesta as render_crystal
from .search import (
    set_cache, clear_cache, next_page, prev_page,
    get_cache, get_result_by_index
)
from .cooldown import cooldown_mgr
from .admin import is_enabled, toggle

from .watch import is_watch_enabled, toggle_watch
from .ai_watcher import (
    should_analyze,
    analyze_message,
    _format_structure_for_prompt,
    ask_question,
)

from .ask_context import get_context, set_context
from .ask_swt import is_ask_enabled, toggle_ask
from .ai_memory import clear_group as clear_ai_group, clear_all as clear_ai_all, stats as ai_stats

from .alias_dict import add as add_alias, lookup as lookup_alias
from .mp_api import resolve_search

from .min_conf import (
    get_min_confidence,
    set_min_confidence,
    clear_min_confidence,
    is_group_configured,
    get_default_confidence,
)

import asyncio

# 帮助信息

__plugin_meta__ = PluginMetadata(
    name="Materials Project 工具",
    description="输入 /mp.help 获取帮助信息",
    usage="输入 /mp.help 获取帮助信息",
    type="application",
)

# 工具函数

def _get_group_id(event: GroupMessageEvent) -> str:
    return str(event.group_id)

async def _send_cif(bot: Bot, event: GroupMessageEvent, material_id: str):
    """发送 CIF 文件"""
    cif_text = await get_cif(material_id)
    if cif_text is None:
        await bot.send(event, f"没有找到材料 {material_id} 的 CIF 数据喵")
        return

    # 保存为临时文件并上传
    tmpdir = tempfile.mkdtemp(prefix="mp_cif_")
    cif_path = os.path.join(tmpdir, f"{material_id}.cif")
    with open(cif_path, "w") as f:
        f.write(cif_text)

    try:
        set_context(_get_group_id(event), material_id)
        await bot.call_api(
            "upload_group_file",
            group_id=event.group_id,
            file=cif_path,
            name=f"{material_id}.cif",
        )
    except Exception as e:
        logger.error(f"上传文件失败: {e}")
        # 降级为发送文本
        await bot.send(event, f"CIF 文件上传失败，内容如下：\n```\n{cif_text[:1500]}\n```")
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

from nonebot.adapters.onebot.v11.exception import ActionFailed

async def _send_vesta_image(
    bot: Bot,
    event: GroupMessageEvent,
    material_id: str,
    view: str = None,
):
    """
    渲染并发送晶体结构图片。
    view: None -> (113)；"tri" -> 三视图；其他 -> (hkl)。
    返回是否至少成功发送了一张图片。
    """
    if view is None:
        views = ["113"]
    elif view.lower() == "tri":
        views = ["100", "010", "001"]
    else:
        views = [view]

    any_success = False
    for v in views:
        png_path = await render_crystal(material_id, v)
        if png_path is None or not os.path.exists(png_path):
            logger.warning(f"渲染 {material_id} ({v}) 失败")
            continue

        try:
            with open(png_path, "rb") as f:
                image_data = f.read()

            # 发送，最多重试 1 次
            sent = False
            for attempt in (1, 2):
                try:
                    await bot.send(event, MessageSegment.image(image_data))
                    sent = True
                    break
                except ActionFailed as e:
                    logger.warning(
                        "发送图片失败（第 {} 次）: material={} view={} retcode={}",
                        attempt, material_id, v,
                        getattr(e, "info", {}).get("retcode") if hasattr(e, "info") else "?",
                    )
                    if attempt == 1:
                        await asyncio.sleep(2)
                except Exception as e:
                    logger.opt(exception=e).error(
                        "发送图片时发生未预期错误: material={} view={}", material_id, v
                    )
                    break

            if sent:
                any_success = True

        finally:
            try:
                os.remove(png_path)
                parent = os.path.dirname(png_path)
                if os.path.exists(parent):
                    import shutil
                    shutil.rmtree(parent, ignore_errors=True)
            except Exception:
                pass

    return any_success

async def _check_enabled_and_cooldown(
    bot: Bot,
    event: GroupMessageEvent,
    check_type: str = "mp",
) -> bool:
    group_id = _get_group_id(event)

    if not is_enabled(group_id):
        await bot.send(event, "mp 指令已禁用")
        return False

    if check_type == "mp":
        ok, remaining = cooldown_mgr.check_mp(group_id)
        if not ok:
            await bot.send(event, f"指令冷却中，还剩 {remaining} s 喵")
            return False
        cooldown_mgr.update_mp(group_id)
    elif check_type == "search":
        ok, remaining = cooldown_mgr.check_search(group_id)
        if not ok:
            await bot.send(event, f"指令冷却中，还剩 {remaining} s 喵")
            return False
        cooldown_mgr.update_search(group_id)

    return True

async def _check_res_cooldown(bot: Bot, event: GroupMessageEvent) -> bool:
    """
    检查 /mp.res 与 /mp.res.prev 的启用状态与冷却。
    """
    group_id = _get_group_id(event)

    if not is_enabled(group_id):
        await bot.send(event, "mp 指令已禁用")
        return False

    ok, remaining = cooldown_mgr.check_res(group_id)
    if not ok:
        await bot.send(event, f"指令冷却中，还剩 {remaining} s 喵")
        return False

    cooldown_mgr.update_res(group_id)
    return True

# 事件响应器

# /mp.help
help_cmd = on_command("mp.help", rule=to_me(), priority=10, block=True)

@help_cmd.handle()
async def handle_help(bot: Bot, event: GroupMessageEvent):
    help_text = (
        "Materials Project 插件指令索引\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "【查询】\n"
        "/mp <material_id>                  获取对称化 CIF 文件\n"
        "/mp.prev <material_id> [hkl|tri]   渲染晶体投影图(可指定投影方向和三视图)\n"
        "\n"
        "【搜索与引用】\n"
        "/mp.search <条件>                  搜索晶体\n"
        "  nextp / lastp                    翻页(无需 @)\n"
        "/mp.res <序号>                     获取搜索结果 CIF\n"
        "/mp.res.prev <序号> [hkl|tri]      渲染搜索结果投影图(可指定投影方向和三视图)\n"
        "/mp.res.CLR                        清除本群搜索结果\n"
        "\n"
        "【搜索条件写法】\n"
        "  Si-O        仅含 Si 和 O (用 - 连接)\n"
        "  Si,O        至少含 Si 和 O (用 , 连接)\n"
        "  Fe2O3       按化学式精确匹配\n"
        "  萤石        若已在别名字典中，直接查询别名\n"
        "\n"
        "【问答】\n"
        "/mp.ask <问题>                     询问晶体学或材料学问题\n"
        "  如：/mp.ask 这个晶体属于什么晶系\n"
        "  如：/mp.ask 详细解释为什么它是四方晶系\n"
        "\n"
        "【别名字典】\n"
        "/mp.dict <别名> [mp ID]            关联别名与晶体\n"
        "  不填 mp ID 时使用本群最近查询的晶体\n"
        "\n"
        "【AI 功能】\n"
        "/mp.ai.CLR                         清除本群 AI 对话记忆\n"
        "  AI 胡言乱语时建议使用\n"
        "/mp.minconf <minconf>              设置 AI 监听最小置信度\n"
        "  经常误触时建议调高, 对 AI 说话没反应时建议调低"
    )
    await bot.send(event, help_text)

# /mp <material_id>
mp_cmd = on_command("mp", rule=to_me(), priority=10, block=True)

@mp_cmd.handle()
async def handle_mp(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not await _check_enabled_and_cooldown(bot, event, "mp"):
        return
    material_id = args.extract_plain_text().strip()
    if not material_id:
        await bot.send(event, "请提供 material_id 喵，例如：/mp mp-162")
        return
    await _send_cif(bot, event, material_id)

# /mp.prev
mp_prev_cmd = on_command("mp.prev", rule=to_me(), priority=10, block=True)

@mp_prev_cmd.handle()
async def handle_mp_prev(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not await _check_enabled_and_cooldown(bot, event, "mp"):
        return
    text = args.extract_plain_text().strip()
    parts = text.split()
    if not parts:
        await bot.send(event, "用法：/mp.prev <material_id> [view]")
        return
    material_id = parts[0]
    view = parts[1] if len(parts) > 1 else None
    await _send_vesta_image(bot, event, material_id, view)

# /mp.search
mp_search_cmd = on_command("mp.search", rule=to_me(), priority=10, block=True)

@mp_search_cmd.handle()
async def handle_mp_search(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not await _check_enabled_and_cooldown(bot, event, "search"):
        return
    query = args.extract_plain_text().strip()
    if not query:
        await bot.send(event, "请提供搜索条件喵")
        return

    group_id = _get_group_id(event)
    clear_cache(group_id)

    await bot.send(event, f"正在搜索：{query} ...")
    results, hit_alias = await resolve_search(query, num_results=50)
    if not results:
        await bot.send(event, "未找到符合条件的晶体喵")
        return

    cache = set_cache(group_id, results, query)
    if hit_alias:
        await bot.send(event, f"命中别名字典「{query}」，共 {len(results)} 个条目：")
    await bot.send(event, cache.format_page())

# nextp / lastp
nextp_msg = on_message(priority=5, block=False)

@nextp_msg.handle()
async def handle_nextp(bot: Bot, event: GroupMessageEvent):
    # 只处理群聊
    if not isinstance(event, GroupMessageEvent):
        return
    text = event.get_plaintext().strip().lower()
    if text not in ("nextp", "lastp"):
        return

    group_id = _get_group_id(event)
    cache = get_cache(group_id)
    if cache is None:
        return

    if text == "nextp":
        page_text = next_page(group_id)
    else:
        page_text = prev_page(group_id)

    if page_text:
        await bot.send(event, page_text)

# /mp.res
mp_res_cmd = on_command("mp.res", rule=to_me(), priority=10, block=True)

@mp_res_cmd.handle()
async def handle_mp_res(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = _get_group_id(event)

    # 先检查"未进行搜索"，避免无意义地进入冷却
    if get_cache(group_id) is None:
        await bot.send(event, "还没进行搜索喵")
        return

    if not await _check_res_cooldown(bot, event):
        return

    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await bot.send(event, "请提供有效的序号喵，例如：/mp.res 1")
        return

    idx = int(text)
    result = get_result_by_index(group_id, idx)
    if result is None:
        await bot.send(event, f"序号 {idx} 超出范围喵")
        return

    await _send_cif(bot, event, result["material_id"])

# /mp.res.prev
mp_res_prev_cmd = on_command("mp.res.prev", rule=to_me(), priority=10, block=True)

@mp_res_prev_cmd.handle()
async def handle_mp_res_prev(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = _get_group_id(event)

    if get_cache(group_id) is None:
        await bot.send(event, "还没进行搜索喵")
        return

    if not await _check_res_cooldown(bot, event):
        return

    text = args.extract_plain_text().strip()
    parts = text.split()
    if not parts or not parts[0].isdigit():
        await bot.send(event, "用法：/mp.res.prev <序号> [view]")
        return

    idx = int(parts[0])
    view = parts[1] if len(parts) > 1 else None

    result = get_result_by_index(group_id, idx)
    if result is None:
        await bot.send(event, f"序号 {idx} 超出范围喵")
        return

    await _send_vesta_image(bot, event, result["material_id"], view)

# /mp.res.CLR
mp_res_clr_cmd = on_command("mp.res.CLR", rule=to_me(), priority=10, block=True)

@mp_res_clr_cmd.handle()
async def handle_mp_res_clr(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)
    clear_cache(group_id)
    await bot.send(event, "搜索结果已清除喵")

# /mp.dict

mp_dict_cmd = on_command("mp.dict", rule=to_me(), priority=10, block=True)

@mp_dict_cmd.handle()
async def handle_mp_dict(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = _get_group_id(event)
    if not is_enabled(group_id):
        await bot.send(event, "mp 指令已禁用")
        return

    text = args.extract_plain_text().strip()
    parts = text.split()
    if not parts:
        await bot.send(event, "用法：/mp.dict <别名> [mp ID]\n未填 mp ID 时使用本群最近查询的晶体。")
        return

    alias = parts[0]
    if len(parts) >= 2:
        material_id = parts[1]
    else:
        ctx = get_context(group_id)
        if ctx is None:
            await bot.send(event, "未提供 mp ID，且本群无最近查询的晶体。请明确指定，如：/mp.dict 石英 mp-6930")
            return
        material_id = ctx.material_id

    if not re.match(r"^mp-\d+$", material_id):
        await bot.send(event, f"无效的 mp ID：{material_id}")
        return

    if add_alias(alias, material_id):
        aliases = ", ".join(lookup_alias(alias))
        await bot.send(event, f"已将「{alias}」关联到 {material_id}。\n当前「{alias}」对应：{aliases}")
    else:
        await bot.send(event, "写入别名字典失败，请查看后台日志。")

# /mp.dict.stats

from .alias_dict import stats as alias_stats

mp_dict_stats_cmd = on_command("mp.dict.stats", rule=to_me(), priority=10, block=True)

@mp_dict_stats_cmd.handle()
async def handle_mp_dict_stats(bot: Bot, event: GroupMessageEvent):
    info = alias_stats()
    files_text = "\n".join(
        f"  - {os.path.basename(p)}"
        for p in info["files"]
    ) or "  （无）"
    await bot.send(
        event,
        "别名字典加载状态\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"加载文件（{len(info['files'])} 个）：\n{files_text}\n"
        f"主字典：{os.path.basename(info['primary'])}\n"
        f"别名总数：{info['alias_count']}\n"
        f"涉及 mp ID 数：{info['id_count']}"
    )

# 管理指令

# /mp.SWT
mp_swt_cmd = on_command("mp.SWT", rule=to_me(), priority=5, block=True)

@mp_swt_cmd.handle()
async def handle_mp_swt(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)
    new_state = toggle(group_id)
    state_text = "启用" if new_state else "禁用"
    await bot.send(event, f"mp 指令已{state_text}喵")

# /mp.CD
mp_cd_cmd = on_command("mp.CD", rule=to_me(), priority=5, block=True)

@mp_cd_cmd.handle()
async def handle_mp_cd(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)
    cooldown_mgr.reset_all(group_id)
    await bot.send(event, "冷却时间已归零喵")

# /mp.WATCH
mp_watch_cmd = on_command("mp.WATCH", rule=to_me(), priority=5, block=True)

@mp_watch_cmd.handle()
async def handle_mp_watch(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)
    new_state = toggle_watch(group_id)
    state_text = "开启" if new_state else "关闭"
    await bot.send(event, f"{state_text} AI 消息监听了喵")

# /mp.ai.CLR

mp_ai_clr_cmd = on_command("mp.ai.CLR", rule=to_me(), priority=5, block=True)

@mp_ai_clr_cmd.handle()
async def handle_mp_ai_clr(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)
    n = clear_ai_group(group_id)
    await bot.send(event, f"本群 AI 记忆已清除（共 {n} 轮）")

# /mp.ai.CLRALL

mp_ai_clrall_cmd = on_command("mp.ai.CLRALL", rule=to_me(), priority=5, block=True)

@mp_ai_clrall_cmd.handle()
async def handle_mp_ai_clrall(bot: Bot, event: GroupMessageEvent):
    n = clear_ai_all()
    await bot.send(event, f"已清除全部 AI 记忆（共 {n} 个群）")

mp_minconf_cmd = on_command("mp.minconf", rule=to_me(), priority=5, block=True)

# /mp.minconf

@mp_minconf_cmd.handle()
async def handle_mp_minconf(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = _get_group_id(event)
    text = args.extract_plain_text().strip()

    # 无参数：查看当前值
    if not text:
        current = get_min_confidence(group_id)
        source = "本群设置" if is_group_configured(group_id) else "全局默认值"
        await bot.send(
            event,
            f"当前 AI 监听置信度阈值：{current:.2f}（{source}）\n"
            f"全局默认值：{get_default_confidence():.2f}\n"
            f"用法：/mp.minconf <0-1> 设置；/mp.minconf reset 恢复默认"
        )
        return

    # reset：恢复默认
    if text.lower() in ("reset", "clear", "default"):
        removed = clear_min_confidence(group_id)
        if removed:
            await bot.send(
                event,
                f"已恢复本群阈值到全局默认值 {get_default_confidence():.2f}。"
            )
        else:
            await bot.send(
                event,
                f"本群此前未设置阈值，当前使用全局默认值 {get_default_confidence():.2f}。"
            )
        return

    # 数值：设置阈值
    try:
        value = float(text)
    except ValueError:
        await bot.send(event, "请输入 0 到 1 之间的数字，例如：/mp.minconf 0.7")
        return

    if not (0.0 <= value <= 1.0):
        await bot.send(event, "阈值必须在 0 到 1 之间。")
        return

    set_min_confidence(group_id, value)
    await bot.send(event, f"已将本群 AI 监听置信度阈值设为 {value:.2f}。")

# AI 消息监听

ai_watch_msg = on_message(priority=20, block=False)

@ai_watch_msg.handle()
async def handle_ai_watch(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)

    if not is_watch_enabled(group_id):
        return
    if not is_enabled(group_id):
        return

    plain = event.get_plaintext()
    is_at_bot = event.is_tome()

    # 判断本群是否已有查询上下文
    from .ask_context import get_context
    has_context = get_context(group_id) is not None

    if not should_analyze(plain, is_at_bot, has_context=has_context):
        return

    calls = await analyze_message(plain, group_id=group_id)
    if not calls:
        return

    for call in calls:
        await _dispatch_ai_call(bot, event, call)

def _format_call_as_command(name: str, args: dict) -> str:
    """把 AI 的工具调用转成可读的 MP 指令文本，用于通知消息"""
    if name == "mp_search":
        query = args.get("query", "").strip()
        return f"/mp.search {query}".rstrip()

    if name == "mp_get_cif":
        material_id = args.get("material_id", "").strip()
        return f"/mp {material_id}".rstrip()

    if name == "mp_prev":
        material_id = args.get("material_id", "").strip()
        view = args.get("view")
        if view:
            return f"/mp.prev {material_id} {view}".rstrip()
        return f"/mp.prev {material_id}".rstrip()

    if name == "mp_res_cif":
        idx = args.get("index")
        return f"/mp.res {idx}"

    if name == "mp_res_prev":
        idx = args.get("index")
        view = args.get("view")
        if view:
            return f"/mp.res.prev {idx} {view}"
        return f"/mp.res.prev {idx}"

    # 未知工具，原样返回
    return f"{name} {args}"

async def _dispatch_ai_call(
    bot: Bot,
    event: GroupMessageEvent,
    call: dict,
):
    """根据 AI 返回的工具调用，执行对应的现有处理逻辑"""
    name = call["name"]
    args = call["arguments"]
    group_id = _get_group_id(event)

    # 先发一条"正在调用..."的通知
    cmd_text = _format_call_as_command(name, args)
    try:
        await bot.send(event, f"正在调用 {cmd_text}")
    except Exception as e:
        logger.opt(exception=e).warning("发送调用通知失败: {}", name)

    try:
        if name == "mp_search":
            query = args.get("query", "").strip()
            if not query:
                return
            clear_cache(group_id)
            results, hit_alias = await resolve_search(query, num_results=50)
            if not results:
                await bot.send(event, f"未找到匹配 {query} 的晶体。")
                return
            cache = set_cache(group_id, results, query)
            if hit_alias:
                await bot.send(event, f"命中别名字典「{query}」，共 {len(results)} 个条目：")
            await bot.send(event, cache.format_page())

        elif name == "mp_get_cif":
            material_id = args.get("material_id", "").strip()
            if material_id:
                await _send_cif(bot, event, material_id)

        elif name == "mp_prev":
            material_id = args.get("material_id", "").strip()
            if not material_id:
                return
            view = args.get("view")
            await _send_vesta_image(bot, event, material_id, view)

        elif name == "mp_res_cif":
            idx = args.get("index")
            if not isinstance(idx, int):
                return
            result = get_result_by_index(group_id, idx)
            if result is None:
                await bot.send(event, f"序号 {idx} 超出范围或未进行搜索。")
                return
            await _send_cif(bot, event, result["material_id"])

        elif name == "mp_res_prev":
            idx = args.get("index")
            if not isinstance(idx, int):
                return
            result = get_result_by_index(group_id, idx)
            if result is None:
                await bot.send(event, f"序号 {idx} 超出范围或未进行搜索。")
                return
            view = args.get("view")
            await _send_vesta_image(bot, event, result["material_id"], view)

        elif name == "mp_get_structure_info":
            material_id = args.get("material_id", "").strip()
            if not material_id:
                return
            from .mp_api import get_structure_info
            data = await get_structure_info(material_id)
            if data is None:
                await bot.send(event, f"未能获取 {material_id} 的结构数据。")
            else:
                formatted = _format_structure_for_prompt(data)
                # 群消息长度限制，分片发送
                for i in range(0, len(formatted), 1500):
                    await bot.send(event, formatted[i:i + 1500])

        elif name == "ask_question":
            if not is_ask_enabled(group_id):
                await bot.send(event, "/mp.ask 指令已禁用")
                return
            question = args.get("question", "").strip()
            if not question:
                return
            await ask_question(bot, event, question)

        elif name == "mp_add_alias":
            alias = args.get("alias", "").strip()
            material_id = args.get("material_id", "").strip()
            if not alias:
                return
            if not material_id:
                ctx = get_context(group_id)
                if ctx is None:
                    await bot.send(event, "未指定 mp ID，且本群无最近查询的晶体。")
                    return
                material_id = ctx.material_id
            if not re.match(r"^mp-\d+$", material_id):
                await bot.send(event, f"无效的 mp ID：{material_id}")
                return
            if add_alias(alias, material_id):
                await bot.send(event, f"已将「{alias}」关联到 {material_id}")
            else:
                await bot.send(event, "写入别名字典失败。")

        else:
            logger.warning(f"AI 返回了未知工具: {name}")

    except Exception as e:
        logger.opt(exception=e).error("执行 AI 指令 {} 失败", name)

mp_ask_cmd = on_command("mp.ask", rule=to_me(), priority=10, block=True)

@mp_ask_cmd.handle()
async def handle_mp_ask(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = _get_group_id(event)

    if not is_enabled(group_id):
        await bot.send(event, "mp 指令已禁用喵")
        return

    if not is_ask_enabled(group_id):
        await bot.send(event, "/mp.ask 指令已禁用喵")
        return

    question = args.extract_plain_text().strip()
    if not question:
        await bot.send(event, "请提供问题喵, 例如: /mp.ask 这个晶体的 4 次旋转轴在哪里?")
        return

    await ask_question(bot, event, question)

mp_ask_swt_cmd = on_command("mp.ask.SWT", rule=to_me(), priority=5, block=True)

@mp_ask_swt_cmd.handle()
async def handle_mp_ask_swt(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)
    new_state = toggle_ask(group_id)
    state_text = "启用" if new_state else "禁用"
    await bot.send(event, f"/mp.ask 指令已{state_text}喵")