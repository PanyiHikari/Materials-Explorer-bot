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
        await bot.send(event, f"未找到材料 {material_id} 的 CIF 数据。")
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
    """用 VESTA 渲染并发送图片"""
    png_path = await render_crystal(material_id, view)
    if png_path is None or not os.path.exists(png_path):
        await bot.send(event, f"VESTA 渲染 {material_id} 失败，请检查 VESTA 配置。")
        return

    try:
        with open(png_path, "rb") as f:
            image_data = f.read()
        await bot.send(event, MessageSegment.image(image_data))
    finally:
        # 清理临时文件
        try:
            os.remove(png_path)
            parent = os.path.dirname(png_path)
            if os.path.exists(parent):
                import shutil
                shutil.rmtree(parent, ignore_errors=True)
        except Exception:
            pass

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
            await bot.send(event, f"指令冷却中，剩余{remaining}秒")
            return False
        cooldown_mgr.update_mp(group_id)
    elif check_type == "search":
        ok, remaining = cooldown_mgr.check_search(group_id)
        if not ok:
            await bot.send(event, f"指令冷却中，剩余{remaining}秒")
            return False
        cooldown_mgr.update_search(group_id)

    return True

async def _check_res_cooldown(bot: Bot, event: GroupMessageEvent) -> bool:
    """
    检查 /mp.res 与 /mp.res.prev 的启用状态与冷却。
    规则：同一群聊在 60 秒窗口内，这两个指令的累计成功调用不超过 3 次。
    """
    group_id = _get_group_id(event)

    if not is_enabled(group_id):
        await bot.send(event, "mp 指令已禁用")
        return False

    ok, remaining = cooldown_mgr.check_res(group_id)
    if not ok:
        await bot.send(event, f"指令冷却中，剩余{remaining}秒")
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
        "/mp.prev <material_id> - 默认视图渲染图片\n"
        "/mp.prev <material_id> <hkl> - 沿指定晶面投影渲染\n"
        "/mp.search <搜索条件> - 搜索晶体\n"
        "  nextp / lastp - 翻页（无需 @）\n"
        "/mp.res <序号> - 获取搜索结果 CIF\n"
        "/mp.res.prev <序号> - 渲染搜索结果默认视图\n"
        "/mp.res.prev <序号> <hkl> - 渲染搜索结果投影图\n"
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
        await bot.send(event, "请提供 material_id，例如：/mp mp-162")
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
            "请提供搜索条件：\n"
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
        await bot.send(event, "未找到符合条件的晶体。")
        return

    cache = set_cache(group_id, results, query)
    await bot.send(event, cache.format_page())

# nextp / lastp（无需 @，无需 /）
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
        await bot.send(event, "未进行搜索")
        return

    if not await _check_res_cooldown(bot, event):
        return

    text = args.extract_plain_text().strip()
    if not text.isdigit():
        await bot.send(event, "请提供有效的序号，例如：/mp.res 1")
        return

    idx = int(text)
    result = get_result_by_index(group_id, idx)
    if result is None:
        await bot.send(event, f"序号 {idx} 超出范围。")
        return

    await _send_cif(bot, event, result["material_id"])

# /mp.res.prev
mp_res_prev_cmd = on_command("mp.res.prev", rule=to_me(), priority=10, block=True)

@mp_res_prev_cmd.handle()
async def handle_mp_res_prev(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = _get_group_id(event)

    if get_cache(group_id) is None:
        await bot.send(event, "未进行搜索")
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
        await bot.send(event, f"序号 {idx} 超出范围。")
        return

    await _send_vesta_image(bot, event, result["material_id"], view)

# /mp.res.CLR
mp_res_clr_cmd = on_command("mp.res.CLR", rule=to_me(), priority=10, block=True)

@mp_res_clr_cmd.handle()
async def handle_mp_res_clr(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)
    clear_cache(group_id)
    await bot.send(event, "搜索结果已清除")

# ==================== 管理指令 ====================

# /mp.SWT（不受禁用影响）
mp_swt_cmd = on_command("mp.SWT", rule=to_me(), priority=5, block=True)

@mp_swt_cmd.handle()
async def handle_mp_swt(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)
    new_state = toggle(group_id)
    state_text = "启用" if new_state else "禁用"
    await bot.send(event, f"mp 指令已{state_text}")

# /mp.CD（不受禁用影响）
mp_cd_cmd = on_command("mp.CD", rule=to_me(), priority=5, block=True)

@mp_cd_cmd.handle()
async def handle_mp_cd(bot: Bot, event: GroupMessageEvent):
    group_id = _get_group_id(event)
    cooldown_mgr.reset_all(group_id)
    await bot.send(event, "冷却时间已归零")