from typing import Dict

from .config import config

_group_thresholds: Dict[str, float] = {}


def get_min_confidence(group_id: str) -> float:
    """获取本群的有效阈值；未配置时回退到全局默认值"""
    if group_id in _group_thresholds:
        return _group_thresholds[group_id]
    return config.ai_watch_min_confidence


def is_group_configured(group_id: str) -> bool:
    return group_id in _group_thresholds


def set_min_confidence(group_id: str, value: float) -> None:
    """设置群级阈值（调用方负责校验范围）"""
    _group_thresholds[group_id] = float(value)


def clear_min_confidence(group_id: str) -> bool:
    """清除群级阈值，恢复全局默认。返回是否原本存在。"""
    return _group_thresholds.pop(group_id, None) is not None


def get_default_confidence() -> float:
    """获取全局默认值（用于展示）"""
    return config.ai_watch_min_confidence