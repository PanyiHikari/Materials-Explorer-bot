import asyncio
import os
import shutil
import tempfile
from typing import Optional

import numpy as np
from nonebot.log import logger

from .config import config
from .mp_api import get_cif


def compute_vesta_rotation(structure, view: str):
    h, k, l = int(view[0]), int(view[1]), int(view[2])

    # pymatgen 的 lattice.matrix 行向量为 a, b, c
    lat = np.array(structure.lattice.matrix)
    # 倒格基：列向量为 a*, b*, c*
    recip = np.linalg.inv(lat).T

    # (hkl) 晶面法线方向在笛卡尔坐标中的向量
    normal = h * recip[:, 0] + k * recip[:, 1] + l * recip[:, 2]
    norm = np.linalg.norm(normal)
    if norm < 1e-12:
        return 0.0, 0.0, 0.0
    vx, vy, vz = normal / norm

    # 步骤 1：绕 x 轴旋转 a，使 vy -> 0
    a = float(np.degrees(np.arctan2(vy, vz)))

    # 步骤 2：绕 y 轴旋转 b，使 vx -> 0
    v_z_after_x = float(np.sqrt(vy ** 2 + vz ** 2))
    b = float(np.degrees(np.arctan2(-vx, v_z_after_x)))

    return a, b, 0.0


def _sync_render_vesta(
    cif_path: str,
    output_png: str,
    view: Optional[str] = None,
    vesta_exec: str = "VESTA",
) -> bool:
    import subprocess
    import time
    from pymatgen.core import Structure

    args = [vesta_exec, "-open", cif_path]

    if view:
        try:
            structure = Structure.from_file(cif_path)
            rx, ry, rz = compute_vesta_rotation(structure, view)
            logger.info(
                f"(hkl)={view} 计算得到的旋转角: "
                f"rotate_x={rx:.3f}°, rotate_y={ry:.3f}°, rotate_z={rz:.3f}°"
            )
            args += ["-rotate_x", f"{rx:.3f}", "-rotate_y", f"{ry:.3f}"]
            if abs(rz) > 1e-3:
                args += ["-rotate_z", f"{rz:.3f}"]
        except Exception as e:
            logger.error(f"计算投影角度失败: {e}", exc_info=True)
            return False

    args += ["-export_img", output_png, "-close"]

    proc = None
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(config.image_timeout):
            if os.path.exists(output_png) and os.path.getsize(output_png) > 0:
                logger.info(f"VESTA 图片已生成: {output_png}，正在终止进程...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                return True
            time.sleep(1)

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
    cif_text = await get_cif(material_id)
    if cif_text is None:
        return None

    tmpdir = tempfile.mkdtemp(prefix="mp_vesta_")
    cif_path = os.path.join(tmpdir, f"{material_id}.cif")
    png_path = os.path.join(tmpdir, f"{material_id}.png")

    with open(cif_path, "w") as f:
        f.write(cif_text)

    vesta_exec = config.vesta_exec or "VESTA"
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