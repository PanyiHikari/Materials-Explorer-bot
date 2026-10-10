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
from .ai_watcher import should_analyze, analyze_message

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

async def _send_vesta_image(
    bot: Bot,
    event: GroupMessageEvent,
    material_id: str,
    view: str = None,
):
    """
    渲染并发送晶体结构图片。
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

        any_success = True
        try:
            with open(png_path, "rb") as f:
                image_data = f.read()
            await bot.send(event, MessageSegment.image(image_data))
        finally:
            try:
                os.remove(png_path)
                parent = os.path.dirname(png_path)
                if os.path.exists(parent):
                    import shutil
                    shutil.rmtree(parent, ignore_errors=True)
            except Exception:
                pass

    if not any_success:
        await bot.send(event, f"晶体结构渲染 {material_id} 失败，请查看后台日志。")

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
        "/mp <material_id> - 获取 CIF 文件\n"
        "/mp.prev <material_id> [hkl] - 渲染晶体图片，可指定投影方向\n"
        "/mp.prev <material_id> tri - 渲染三视图\n"
        "/mp.search <搜索条件> - 搜索晶体\n"
        "  nextp / lastp - 翻页（无需 @）\n"
        "/mp.res <序号> - 获取搜索结果 CIF\n"
        "/mp.res.prev <序号> [hkl] - 渲染搜索结果图片，可指定投影方向\n"
        "/mp.res.prev <序号> tri - 渲染搜索结果三视图\n"
        "/mp.res.CLR - 清除搜索结果"
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
        await bot.send(event, 
            "请提供搜索条件喵：\n"
            "  only:Si,O        —— 仅含 Si 和 O\n"
            "  atleast:Si,O     —— 至少含 Si 和 O\n"
            "  formula:Fe2O3    —— 化学式为 Fe2O3"
        )
        return

    group_id = _get_group_id(event)
    clear_cache(group_id)

    await bot.send(event, f"正在搜索：{query} ...")
    results = await search_materials(query, num_results=50)
    if not results:
        await bot.send(event, "没找到符合条件的晶体喵")
        return

    cache = set_cache(group_id, results, query)
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

# AI 消息监听

ai_watch_msg = on_message(priority=20, block=False)

@ai_watch_msg.handle()
async def handle_ai_watch(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)

    # 未开启 WATCH 则忽略
    if not is_watch_enabled(group_id):
        return

    # 插件被禁用则忽略
    if not is_enabled(group_id):
        return

    # 判断消息是否应该送给 AI
    plain = event.get_plaintext()
    is_at_bot = event.is_tome()
    if not should_analyze(plain, is_at_bot):
        return

    # 调用 AI 分析
    calls = await analyze_message(plain)
    if not calls:
        return

    # 逐条执行 AI 返回的指令
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
        logger.warning(f"发送调用通知失败: {e}")

    try:
        if name == "mp_search":
            query = args.get("query", "").strip()
            if not query:
                return
            clear_cache(group_id)
            results = await search_materials(query, num_results=50)
            if not results:
                await bot.send(event, f"未找到匹配 {query} 的晶体。")
                return
            cache = set_cache(group_id, results, query)
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

        else:
            logger.warning(f"AI 返回了未知工具: {name}")

    except Exception as e:
        logger.error(f"执行 AI 指令 {name} 失败: {e}", exc_info=True)