from typing import Dict

# 群聊 -> 是否启用
_enabled: Dict[str, bool] = {}

def is_enabled(group_id: str) -> bool:
    """默认启用"""
    return _enabled.get(group_id, True)

def toggle(group_id: str) -> bool:
    """切换启用状态，返回新状态"""
    new_state = not is_enabled(group_id)
    _enabled[group_id] = new_state
    return new_state