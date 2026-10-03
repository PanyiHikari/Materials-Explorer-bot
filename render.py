import asyncio
import os
import tempfile
from typing import Optional

import numpy as np
from nonebot.log import logger

from .mp_api import get_structure


def _sync_render(structure, output_png: str, view: Optional[str] = None) -> bool:
    """用 ASE + matplotlib 渲染晶体结构为 PNG"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from ase import Atoms
        from ase.visualize.plot import plot_atoms
    except ImportError as e:
        logger.error(f"缺少绘图依赖，请 pip install ase matplotlib: {e}")
        return False

    try:
        atoms = Atoms(
            symbols=[str(s.specie) for s in structure],
            positions=[s.coords for s in structure],
            cell=structure.lattice.matrix,
            pbc=True,
        )

        # 若指定了 (hkl)，先计算把该法线旋转到 z 轴的旋转矩阵，再手动应用到原子和晶胞
        if view:
            try:
                h, k, l = int(view[0]), int(view[1]), int(view[2])
            except (IndexError, ValueError):
                logger.error(f"无效的晶面参数: {view}")
                return False

            # 倒格基（列向量）
            recip = np.linalg.inv(atoms.cell.array).T
            normal = h * recip[:, 0] + k * recip[:, 1] + l * recip[:, 2]
            n_norm = np.linalg.norm(normal)
            if n_norm < 1e-12:
                logger.error(f"非法法线: {view}")
                return False
            normal = normal / n_norm

            z = np.array([0.0, 0.0, 1.0])
            v = np.cross(normal, z)
            s = np.linalg.norm(v)
            c = float(np.dot(normal, z))

            if s < 1e-8:
                # 法线已平行于 z 轴
                if c > 0:
                    R = np.eye(3)
                else:
                    R = np.diag([1.0, -1.0, -1.0])
            else:
                vx = np.array([
                    [0.0, -v[2], v[1]],
                    [v[2], 0.0, -v[0]],
                    [-v[1], v[0], 0.0],
                ])
                R = np.eye(3) + vx + vx @ vx * (1 - c) / (s * s)

            # 手动应用旋转：位置按行，晶胞按行
            pos = atoms.get_positions()
            atoms.set_positions((R @ pos.T).T)

            cell = atoms.cell.array
            atoms.set_cell((R @ cell.T).T)

        fig, ax = plt.subplots(figsize=(6, 6), dpi=120)
        plot_atoms(
            atoms, ax,
            radii=0.6,
            rotation="0x,0y,0z",
            show_unit_cell=2,
        )
        ax.set_axis_off()
        fig.savefig(output_png, bbox_inches="tight", pad_inches=0.05, dpi=120)
        plt.close(fig)
        return True
    except Exception as e:
        logger.error(f"渲染失败: {e}", exc_info=True)
        return False


async def render_crystal(material_id: str, view: Optional[str] = None) -> Optional[str]:
    """渲染晶体结构，返回 PNG 路径，失败返回 None"""
    structure = await get_structure(material_id)
    if structure is None:
        return None

    tmpdir = tempfile.mkdtemp(prefix="mp_render_")
    png_path = os.path.join(tmpdir, f"{material_id}.png")

    success = await asyncio.to_thread(_sync_render, structure, png_path, view)
    if success and os.path.exists(png_path):
        return png_path

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    return None