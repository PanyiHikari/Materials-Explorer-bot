import time
from typing import Dict, List
from dataclasses import dataclass

@dataclass
class MemoryTurn:
    timestamp: float
    user: str
    assistant: str


_MAX_TURNS = 10           # 每群最多保留 10 轮
_MAX_ASSISTANT_LEN = 2000 # 单条回答截断长度

_memories: Dict[str, List[MemoryTurn]] = {}


def add_turn(group_id: str, user: str, assistant: str):
    """记录一轮问答"""
    if not user or not assistant:
        return

    assistant = assistant.strip()
    if len(assistant) > _MAX_ASSISTANT_LEN:
        assistant = assistant[:_MAX_ASSISTANT_LEN] + "…（已截断）"

    turns = _memories.setdefault(group_id, [])
    turns.append(MemoryTurn(
        timestamp=time.time(),
        user=user.strip(),
        assistant=assistant,
    ))

    if len(turns) > _MAX_TURNS:
        del turns[: len(turns) - _MAX_TURNS]


def get_history(group_id: str, max_turns: int = None) -> List[MemoryTurn]:
    """获取指定群的对话历史，默认返回全部（最多 10 轮）"""
    turns = _memories.get(group_id, [])
    if max_turns is not None and max_turns > 0:
        return turns[-max_turns:]
    return list(turns)


def clear_group(group_id: str) -> int:
    """清除指定群记忆，返回被清除的轮数"""
    turns = _memories.pop(group_id, [])
    return len(turns)


def clear_all() -> int:
    """清除所有群的记忆，返回被清除的群数"""
    count = len(_memories)
    _memories.clear()
    return count


def stats(group_id: str) -> int:
    """返回指定群当前的记忆轮数"""
    return len(_memories.get(group_id, []))