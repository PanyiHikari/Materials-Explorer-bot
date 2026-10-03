import asyncio
from typing import Optional, List, Dict, Any

from mp_api.client import MPRester
from pymatgen.core import Structure
from pymatgen.io.cif import CifWriter
from nonebot.log import logger

from .config import config


def _sync_get_structure(material_id: str) -> Optional[Structure]:
    """同步获取晶体结构"""
    try:
        with MPRester(config.mp_api_key) as mpr:
            structure = mpr.get_structure_by_material_id(material_id)
            return structure
    except Exception as e:
        logger.error(f"获取结构失败 {material_id}: {e}")
        return None


def _sync_get_cif(material_id: str, symprec: float = 0.1) -> Optional[str]:
    """获取对称化 CIF 文本"""
    structure = _sync_get_structure(material_id)
    if structure is None:
        return None
    try:
        writer = CifWriter(structure, symprec=symprec)
        return str(writer)
    except Exception as e:
        logger.error(f"CIF 生成失败 {material_id}: {e}")
        return None


def _parse_search_query(query: str) -> dict:
    """
    自动解析搜索条件：
      - 含 "-"：按 only elements 处理（chemsys），如 "Si-O"
      - 含 ","：按 at least elements 处理（elements），如 "Si,O"
      - 其他 ：按化学式处理（formula），如 "Fe2O3"
    """
    query = query.strip()

    if "-" in query:
        elements = [e.strip() for e in query.split("-") if e.strip()]
        return {"chemsys": "-".join(elements)}
    elif "," in query:
        elements = [e.strip() for e in query.split(",") if e.strip()]
        return {"elements": elements}
    else:
        return {"formula": query}


def _sync_search(query: str, num_results: int = 50) -> List[Dict[str, Any]]:
    """在 Materials Project 中搜索，自动识别搜索模式"""
    results: List[Dict[str, Any]] = []
    try:
        kwargs = _parse_search_query(query)
        logger.info(f"搜索参数: {kwargs}")

        with MPRester(config.mp_api_key) as mpr:
            docs = mpr.materials.summary.search(
                **kwargs,
                fields=[
                    "material_id",
                    "formula_pretty",
                    "symmetry",
                    "nsites",
                    "theoretical",  # 将 is_experimental 改为 theoretical
                ],
                num_chunks=1,
                chunk_size=num_results,
            )
            logger.info(f"API 返回 {len(docs)} 条结果")

            for doc in docs:
                results.append({
                    "material_id": str(doc.material_id),
                    "formula": doc.formula_pretty,
                    "spacegroup": doc.symmetry.symbol if doc.symmetry else "N/A",
                    "nsites": doc.nsites,
                    # theoretical=False 表示实验结构，对应原来 is_experimental=True 的逻辑
                    "is_experimental": not doc.theoretical,
                })

    except Exception as e:
        logger.error(f"搜索失败: {e}", exc_info=True)
    return results


async def get_structure(material_id: str) -> Optional[Structure]:
    return await asyncio.to_thread(_sync_get_structure, material_id)


async def get_cif(material_id: str, symprec: float = 0.1) -> Optional[str]:
    return await asyncio.to_thread(_sync_get_cif, material_id, symprec)


async def search_materials(query: str, num_results: int = 50) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_sync_search, query, num_results)