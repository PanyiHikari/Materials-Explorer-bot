import asyncio
import os
import shutil
import tempfile
from typing import Optional

from nonebot.log import logger

from .config import config
from .mp_api import get_cif


def _sync_render_vesta(
    cif_path: str,
    output_png: str,
    view: Optional[str] = None,
    vesta_exec: str = "VESTA",
) -> bool:
    """
    用 VESTA 命令行渲染 CIF 并导出 PNG。
    view 形如 "011"、"111"，表示沿该晶面法线方向观察。
    """
    import subprocess
    import time

    args = [vesta_exec, "-open", cif_path]

    if view:
        try:
            h, k, l = int(view[0]), int(view[1]), int(view[2])
        except (IndexError, ValueError):
            logger.error(f"无效的晶面参数: {view}")
            return False

        import math
        total = math.sqrt(h*h + k*k + l*l) or 1
        rx = int(math.degrees(math.acos(max(-1, min(1, l / total)))))
        ry = int(math.degrees(math.atan2(k, h))) if (h or k) else 0
        args += ["-rotate_x", str(rx), "-rotate_y", str(ry)]

    args += ["-export_img", output_png, "-close"]

    proc = None
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 轮询等待图片文件生成，而不是等待进程退出
        for _ in range(config.image_timeout):
            if os.path.exists(output_png) and os.path.getsize(output_png) > 0:
                # 图片已生成，主动终止 VESTA 进程
                logger.info(f"VESTA 图片已生成: {output_png}，正在终止进程...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                return True
            time.sleep(1)

        # 超时后仍未生成图片
        logger.warning(f"VESTA 图片生成超时: {output_png}")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return False

    except FileNotFoundError:
        logger.error(f"VESTA 可执行文件未找到: {vesta_exec}")
        return False
    except Exception as e:
        logger.error(f"VESTA 渲染失败: {e}", exc_info=True)
        if proc:
            try:
                proc.kill()
                proc.wait()
            except Exception:
                pass
        return False


async def render_crystal_vesta(
    material_id: str,
    view: Optional[str] = None,
) -> Optional[str]:
    """用 VESTA 渲染晶体结构，返回 PNG 路径，失败返回 None"""
    cif_text = await get_cif(material_id)
    if cif_text is None:
        return None

    tmpdir = tempfile.mkdtemp(prefix="mp_vesta_")
    cif_path = os.path.join(tmpdir, f"{material_id}.cif")
    png_path = os.path.join(tmpdir, f"{material_id}.png")

    with open(cif_path, "w") as f:
        f.write(cif_text)

    vesta_exec = config.vesta_exec or "VESTA"
    # 如果配置的路径不存在，尝试在 PATH 中查找
    if not os.path.exists(vesta_exec):
        found = shutil.which("VESTA")
        if found:
            vesta_exec = found

    success = await asyncio.to_thread(
        _sync_render_vesta,
        cif_path,
        png_path,
        view,
        vesta_exec,
    )

    if success and os.path.exists(png_path):
        return png_path

    shutil.rmtree(tmpdir, ignore_errors=True)
    return None