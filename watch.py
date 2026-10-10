from typing import Dict

_watch_enabled: Dict[str, bool] = {}

def is_watch_enabled(group_id: str) -> bool:
    """默认关闭"""
    return _watch_enabled.get(group_id, False)

def toggle_watch(group_id: str) -> bool:
    new_state = not is_watch_enabled(group_id)
    _watch_enabled[group_id] = new_state
    return new_state