import math
import time
from typing import Dict, Tuple


class CooldownManager:
    """冷却时间管理器，按群聊分别计时"""

    def __init__(self, cooldown_seconds: int = 60):
        self.cooldown = cooldown_seconds
        # group_id -> (last_mp_time, last_search_time)
        self._timers: Dict[str, Tuple[float, float]] = {}
        # group_id -> (window_start, count)  用于 /mp.res 与 /mp.res.prev
        self._res_windows: Dict[str, Tuple[float, int]] = {}

    # 内部工具

    def _get_timers(self, group_id: str) -> Tuple[float, float]:
        if group_id not in self._timers:
            self._timers[group_id] = (0.0, 0.0)
        return self._timers[group_id]

    def _remaining(self, elapsed: float) -> int:
        """向上取整返回剩余秒数，至少 1 秒"""
        return max(1, math.ceil(self.cooldown - elapsed))

    # /mp 与 /mp.prev

    def check_mp(self, group_id: str) -> Tuple[bool, int]:
        mp_time, _ = self._get_timers(group_id)
        elapsed = time.time() - mp_time
        if elapsed >= self.cooldown:
            return True, 0
        return False, self._remaining(elapsed)

    def update_mp(self, group_id: str):
        mp_time, search_time = self._get_timers(group_id)
        self._timers[group_id] = (time.time(), search_time)

    # /mp.search

    def check_search(self, group_id: str) -> Tuple[bool, int]:
        _, search_time = self._get_timers(group_id)
        elapsed = time.time() - search_time
        if elapsed >= self.cooldown:
            return True, 0
        return False, self._remaining(elapsed)

    def update_search(self, group_id: str):
        mp_time, search_time = self._get_timers(group_id)
        self._timers[group_id] = (mp_time, time.time())

    # /mp.res 与 /mp.res.prev

    def check_res(self, group_id: str) -> Tuple[bool, int]:
        now = time.time()
        start, count = self._res_windows.get(group_id, (0.0, 0))

        # 距离窗口开启已超过冷却时长 -> 新窗口，允许
        if now - start >= self.cooldown:
            return True, 0

        # 窗口内调用次数未满 3 次 -> 允许
        if count < 3:
            return True, 0

        # 已满 3 次 -> 拒绝
        return False, self._remaining(now - start)

    def update_res(self, group_id: str):
        now = time.time()
        start, count = self._res_windows.get(group_id, (0.0, 0))
        if now - start >= self.cooldown:
            self._res_windows[group_id] = (now, 1)
        else:
            self._res_windows[group_id] = (start, count + 1)

    # 管理指令

    def reset_all(self, group_id: str):
        """将该群所有冷却时间归零"""
        self._timers[group_id] = (0.0, 0.0)
        self._res_windows.pop(group_id, None)


cooldown_mgr = CooldownManager(cooldown_seconds=60)