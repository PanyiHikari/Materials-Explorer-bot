import asyncio
from typing import Optional, List, Dict, Any, Tuple

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
    自动解析搜索条件
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
                    # theoretical=False 表示实验结构
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

def _sync_get_structure_info(material_id: str) -> Optional[Dict[str, Any]]:
    """
    获取指定晶体的完整结构信息
    """
    try:
        with MPRester(config.mp_api_key) as mpr:
            structure = mpr.get_structure_by_material_id(material_id)
            if structure is None:
                return None

            try:
                summary = mpr.materials.summary.search(
                    material_id=material_id,
                    fields=["symmetry", "formula_pretty", "nsites",
                            "is_stable", "band_gap", "density", "volume"],
                )
                info = summary[0] if summary else None
            except Exception:
                info = None

            lat = structure.lattice
            sites = []
            for site in structure:
                # pymatgen 中占位率存放在 site.species（Composition）里
                species_dict = {
                    str(el): round(float(occ), 4)
                    for el, occ in site.species.items()
                    if occ > 1e-6
                }
                # 主元素（占位率最高的那个）用于展示
                if species_dict:
                    main_el, main_occ = max(species_dict.items(), key=lambda kv: kv[1])
                else:
                    main_el, main_occ = str(site.specie), 1.0

                sites.append({
                    "element": main_el,
                    "species": species_dict,              # 所有元素 + 占位率
                    "fractional_coords": [round(float(x), 6) for x in site.frac_coords],
                    "cartesian_coords": [round(float(x), 6) for x in site.coords],
                    "occupancy": main_occ,                # 兼容旧字段
                })

            result: Dict[str, Any] = {
                "material_id": material_id,
                "formula": structure.composition.reduced_formula,
                "full_formula": structure.composition.formula,
                "nsites": len(structure),
                "lattice": {
                    "a": round(float(lat.a), 6),
                    "b": round(float(lat.b), 6),
                    "c": round(float(lat.c), 6),
                    "alpha": round(float(lat.alpha), 4),
                    "beta": round(float(lat.beta), 4),
                    "gamma": round(float(lat.gamma), 4),
                    "volume": round(float(lat.volume), 4),
                },
                "sites": sites,
            }

            if info is not None:
                if getattr(info, "symmetry", None):
                    sym = info.symmetry
                    result["spacegroup_symbol"] = sym.symbol
                    result["spacegroup_number"] = sym.number
                    result["point_group"] = sym.point_group
                    cs = getattr(sym, "crystal_system", None)
                    result["crystal_system"] = cs.value if hasattr(cs, "value") else str(cs)
                for attr in ("density", "band_gap", "is_stable", "volume"):
                    if hasattr(info, attr):
                        v = getattr(info, attr)
                        if isinstance(v, (int, float)):
                            result[attr] = round(float(v), 4)

            return result

    except Exception as e:
        logger.error(f"获取结构信息失败 {material_id}: {e}", exc_info=True)
        return None


async def get_structure_info(material_id: str) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_sync_get_structure_info, material_id)

def _sync_get_materials_summary(material_ids: List[str]) -> List[Dict[str, Any]]:
    """根据一组 mp ID 批量获取搜索摘要，保持输入顺序"""
    if not material_ids:
        return []
    results: List[Dict[str, Any]] = []
    try:
        with MPRester(config.mp_api_key) as mpr:
            docs = mpr.materials.summary.search(
                material_ids=list(material_ids),
                fields=[
                    "material_id",
                    "formula_pretty",
                    "symmetry",
                    "nsites",
                    "theoretical",
                ],
                num_chunks=1,
                chunk_size=max(len(material_ids), 10),
            )
            doc_map = {str(d.material_id): d for d in docs}
            for mid in material_ids:
                d = doc_map.get(mid)
                if d is None:
                    continue
                results.append({
                    "material_id": str(d.material_id),
                    "formula": d.formula_pretty,
                    "spacegroup": d.symmetry.symbol if d.symmetry else "N/A",
                    "nsites": d.nsites,
                    "is_experimental": not d.theoretical,
                })
    except Exception as e:
        logger.opt(exception=e).error("批量获取材料摘要失败")
    return results


async def get_materials_summary(material_ids: List[str]) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_sync_get_materials_summary, material_ids)


async def resolve_search(
    query: str,
    num_results: int = 50,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    统一搜索入口：
      1. 先查别名字典，命中则返回字典里所有 mp ID 的摘要
      2. 否则调用 MP API 搜索
    Returns:
        (results, hit_alias)
    """
    from .alias_dict import lookup

    alias_mids = lookup(query)
    if alias_mids:
        results = await get_materials_summary(alias_mids)
        return results, True

    results = await search_materials(query, num_results)
    return results, False