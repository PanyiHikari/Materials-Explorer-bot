import glob
import json
import os
import threading
from typing import Dict, List, Optional

from nonebot.log import logger

_PLUGIN_DIR = os.path.dirname(__file__)
_PRIMARY_FILENAME = "alias_dict.json"
_GLOB_PATTERN = "alias_dict*.json"

_LOCK = threading.RLock()
_cache: Optional[Dict[str, List[str]]] = None
_cache_fingerprint: Optional[tuple] = None


# ---------------- 文件发现与加载 ----------------

def _dict_files() -> List[str]:
    """返回所有别名 JSON 文件的绝对路径，按文件名排序"""
    pattern = os.path.join(_PLUGIN_DIR, _GLOB_PATTERN)
    return sorted(glob.glob(pattern))


def _primary_path() -> str:
    """主字典路径（/mp.dict 写入目标）"""
    return os.path.join(_PLUGIN_DIR, _PRIMARY_FILENAME)


def _load_one(path: str) -> Dict[str, List[str]]:
    """读取单个字典文件，格式非法时返回空字典"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.opt(exception=e).warning("读取别名字典失败: {}", path)
        return {}

    if not isinstance(data, dict):
        logger.warning("别名字典格式异常（顶层应为对象）: {}", path)
        return {}

    result: Dict[str, List[str]] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            logger.warning("别名字典键非字符串，已跳过: {} -> {}", k, path)
            continue
        if isinstance(v, str):
            ids = [v]
        elif isinstance(v, list):
            ids = [str(x) for x in v]
        else:
            logger.warning("别名字典项 {} 值类型异常，已跳过: {}", k, path)
            continue
        result[k] = ids
    return result


def _merge_all(files: List[str]) -> Dict[str, List[str]]:
    """
    合并所有文件。同名别名取 ID 的并集（去重，保留首次出现顺序）。
    若想改为"后加载覆盖前加载"，把 union 逻辑改为 merged[alias] = list(ids) 即可。
    """
    merged: Dict[str, List[str]] = {}
    for path in files:
        data = _load_one(path)
        for alias, ids in data.items():
            if alias in merged:
                existing = merged[alias]
                for mid in ids:
                    if mid not in existing:
                        existing.append(mid)
            else:
                merged[alias] = list(ids)
    return merged


def _fingerprint(files: List[str]) -> tuple:
    """生成文件集合 + mtime 的指纹，用于检测变更"""
    items = []
    for p in files:
        try:
            items.append((p, os.path.getmtime(p)))
        except OSError:
            items.append((p, 0.0))
    return tuple(items)


def _get_cache() -> Dict[str, List[str]]:
    """获取合并后的缓存；文件集合或任一文件 mtime 变化时重新加载"""
    global _cache, _cache_fingerprint
    with _LOCK:
        files = _dict_files()
        fp = _fingerprint(files)
        if _cache is None or fp != _cache_fingerprint:
            _cache = _merge_all(files)
            _cache_fingerprint = fp
            logger.info(
                "别名字典已加载：{} 个文件，{} 个别名",
                len(files), len(_cache),
            )
        return _cache


def _force_reload():
    global _cache, _cache_fingerprint
    with _LOCK:
        _cache = None
        _cache_fingerprint = None


# ---------------- 对外接口 ----------------

def lookup(alias: str) -> List[str]:
    """查询别名对应的所有 mp ID（大小写不敏感）"""
    if not alias:
        return []
    with _LOCK:
        data = _get_cache()
        if alias in data:
            return list(data[alias])
        alias_lower = alias.lower()
        for k, v in data.items():
            if k.lower() == alias_lower:
                return list(v)
    return []


def add(alias: str, material_id: str) -> bool:
    """添加别名 -> mp ID，写入主文件 alias_dict.json（不存在时创建）"""
    alias = alias.strip()
    material_id = material_id.strip()
    if not alias or not material_id:
        return False

    with _LOCK:
        path = _primary_path()

        # 读取主文件现有内容
        current: Dict[str, List[str]] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        if isinstance(v, str):
                            current[k] = [v]
                        elif isinstance(v, list):
                            current[k] = [str(x) for x in v]
            except Exception as e:
                logger.opt(exception=e).warning("读取主别名字典失败: {}", path)

        # 追加
        ids = current.setdefault(alias, [])
        if material_id in ids:
            # 已存在，无需写盘，但视为成功
            _force_reload()
            return True

        ids.append(material_id)

        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except Exception as e:
            logger.opt(exception=e).error("写入主别名字典失败: {}", path)
            return False

        _force_reload()
        return True


def get_aliases_for_id(material_id: str) -> List[str]:
    """反向查询：返回所有映射到该 mp ID 的别名"""
    with _LOCK:
        data = _get_cache()
        return [alias for alias, mids in data.items() if material_id in mids]


def all_aliases() -> List[str]:
    """返回合并后的所有别名（供 AI 提示注入使用）"""
    with _LOCK:
        return list(_get_cache().keys())


def stats() -> dict:
    """返回字典的加载统计信息（用于 /mp.dict.stats）"""
    with _LOCK:
        files = _dict_files()
        data = _get_cache()
        return {
            "files": files,
            "primary": _primary_path(),
            "alias_count": len(data),
            "id_count": len({mid for ids in data.values() for mid in ids}),
        }


def reload():
    """强制重新加载（通常无需手动调用）"""
    _force_reload()