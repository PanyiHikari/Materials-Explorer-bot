import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .config import config

@dataclass
class SearchCache:
    """每个群聊的搜索缓存"""
    results: List[Dict] = field(default_factory=list)
    page: int = 0  # 当前页码（从 0 开始）
    timestamp: float = 0.0
    query: str = ""

    @property
    def total_pages(self) -> int:
        if not self.results:
            return 0
        return (len(self.results) + config.search_page_size - 1) // config.search_page_size

    def get_page_items(self) -> List[Dict]:
        """获取当前页的结果"""
        start = self.page * config.search_page_size
        end = start + config.search_page_size
        return self.results[start:end]

    def format_page(self) -> str:
        """格式化当前页为文本（含表头）"""
        if not self.results:
            return "未找到符合条件的晶体。"

        items = self.get_page_items()
        lines = [
            "| 序号 | 是否测得 | mp ID | 化学式 | 空间群 | 原子数 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for i, item in enumerate(items):
            idx = self.page * config.search_page_size + i + 1
            star = "*" if item.get("is_experimental") else " "
            lines.append(
                f"| {idx} | {star} | {item['material_id']} | "
                f"{item['formula']} | {item['spacegroup']} | {item['nsites']} |"
            )

        lines.append(f"\n第{self.page + 1}页，共{self.total_pages}页")
        return "\n".join(lines)

# 群聊 -> SearchCache
_search_caches: Dict[str, SearchCache] = {}

def get_cache(group_id: str) -> Optional[SearchCache]:
    return _search_caches.get(group_id)

def set_cache(group_id: str, results: List[Dict], query: str) -> SearchCache:
    """设置搜索结果并重置到第一页"""
    cache = SearchCache(
        results=results,
        page=0,
        timestamp=time.time(),
        query=query,
    )
    _search_caches[group_id] = cache
    return cache

def clear_cache(group_id: str):
    _search_caches.pop(group_id, None)

def next_page(group_id: str) -> Optional[str]:
    cache = get_cache(group_id)
    if cache is None:
        return None
    if cache.page < cache.total_pages - 1:
        cache.page += 1
    return cache.format_page()

def prev_page(group_id: str) -> Optional[str]:
    cache = get_cache(group_id)
    if cache is None:
        return None
    if cache.page > 0:
        cache.page -= 1
    return cache.format_page()

def get_result_by_index(group_id: str, index: int) -> Optional[Dict]:
    """根据序号获取搜索结果（序号从1开始）"""
    cache = get_cache(group_id)
    if cache is None:
        return None
    if 1 <= index <= len(cache.results):
        return cache.results[index - 1]
    return None