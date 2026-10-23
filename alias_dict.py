import json
import os
import threading
from typing import Dict, List, Optional

from nonebot.log import logger

_DICT_PATH = os.path.join(os.path.dirname(__file__), "alias_dict.json")
_LOCK = threading.RLock()
_cache: Optional[Dict[str, List[str]]] = None
_cache_mtime: float = 0.0


def _normalize(data) -> Dict[str, List[str]]:
    if not isinstance(data, dict):
        logger.warning("别名字典格式异常，期望 dict")
        return {}
    out: Dict[str, List[str]] = {}
    for k, v in data.items():
        if isinstance(v, str):
            out[k] = [v]
        elif isinstance(v, list):
            out[k] = [str(x) for x in v]
        else:
            logger.warning(f"别名字典项 {k!r} 值类型异常，已跳过")
    return out


def _load_from_disk() -> Dict[str, List[str]]:
    if not os.path.exists(_DICT_PATH):
        return {}
    try:
        with open(_DICT_PATH, "r", encoding="utf-8") as f:
            return _normalize(json.load(f))
    except Exception as e:
        logger.opt(exception=e).error("读取别名字典失败")
        return {}


def _save_to_disk(data: Dict[str, List[str]]) -> bool:
    try:
        tmp_path = _DICT_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, _DICT_PATH)
        return True
    except Exception as e:
        logger.opt(exception=e).error("写入别名字典失败")
        return False


def _get_cache() -> Dict[str, List[str]]:
    """获取缓存；若磁盘 mtime 变化则重新加载（兼容后端手动编辑）"""
    global _cache, _cache_mtime
    with _LOCK:
        try:
            mtime = os.path.getmtime(_DICT_PATH) if os.path.exists(_DICT_PATH) else 0.0
        except OSError:
            mtime = 0.0
        if _cache is None or mtime != _cache_mtime:
            _cache = _load_from_disk()
            _cache_mtime = mtime
        return _cache


def lookup(alias: str) -> List[str]:
    """查询别名对应的所有 mp ID。大小写不敏感。"""
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
    """添加别名 -> mp ID。重复添加不产生副本。"""
    global _cache_mtime
    alias = alias.strip()
    material_id = material_id.strip()
    if not alias or not material_id:
        return False
    with _LOCK:
        data = _get_cache()
        mids = data.setdefault(alias, [])
        if material_id not in mids:
            mids.append(material_id)
        if not _save_to_disk(data):
            return False
        try:
            _cache_mtime = os.path.getmtime(_DICT_PATH)
        except OSError:
            _cache_mtime = 0.0
        return True


def get_aliases_for_id(material_id: str) -> List[str]:
    """反向查询：给定 mp ID 返回所有别名"""
    with _LOCK:
        data = _get_cache()
        return [alias for alias, mids in data.items() if material_id in mids]


def reload():
    """强制重新加载（一般无需手动调用）"""
    global _cache, _cache_mtime
    with _LOCK:
        _cache = None
        _cache_mtime = 0.0

def all_aliases() -> List[str]:
    """返回当前字典中所有别名（用于 AI 提示注入）"""
    with _LOCK:
        return list(_get_cache().keys())