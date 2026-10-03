import time
from typing import Dict, Tuple

class CooldownManager:
    """冷却时间管理器，按群聊分别计时"""

    def __init__(self, cooldown_seconds: int = 60):
        self.cooldown = cooldown_seconds
        # group_id -> (last_mp_time, last_search_time)
        self._timers: Dict[str, Tuple[float, float]] = {}

    def _get_timers(self, group_id: str) -> Tuple[float, float]:
        if group_id not in self._timers:
            self._timers[group_id] = (0.0, 0.0)
        return self._timers[group_id]

    def check_mp(self, group_id: str) -> Tuple[bool, int]:
        """
        检查 /mp 和 /mp.prev 的冷却
        Returns: (是否可用, 剩余秒数)
        """
        mp_time, _ = self._get_timers(group_id)
        elapsed = time.time() - mp_time
        if elapsed >= self.cooldown:
            return True, 0
        return False, int(self.cooldown - elapsed)

    def check_search(self, group_id: str) -> Tuple[bool, int]:
        """检查 /mp.search 的冷却"""
        _, search_time = self._get_timers(group_id)
        elapsed = time.time() - search_time
        if elapsed >= self.cooldown:
            return True, 0
        return False, int(self.cooldown - elapsed)

    def update_mp(self, group_id: str):
        """更新 /mp 计时器"""
        mp_time, search_time = self._get_timers(group_id)
        self._timers[group_id] = (time.time(), search_time)

    def update_search(self, group_id: str):
        """更新 /mp.search 计时器"""
        mp_time, search_time = self._get_timers(group_id)
        self._timers[group_id] = (mp_time, time.time())

    def reset_all(self, group_id: str):
        """将该群所有冷却时间归零"""
        self._timers[group_id] = (0.0, 0.0)

cooldown_mgr = CooldownManager(cooldown_seconds=60)