from typing import Dict

_ask_enabled: Dict[str, bool] = {}

def is_ask_enabled(group_id: str) -> bool:
    return _ask_enabled.get(group_id, True)   # 默认启用

def toggle_ask(group_id: str) -> bool:
    new_state = not is_ask_enabled(group_id)
    _ask_enabled[group_id] = new_state
    return new_state