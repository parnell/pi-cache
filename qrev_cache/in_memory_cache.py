from typing import Optional

from qrev_cache.base_cache import BaseCache, CacheEntry


class InMemoryCache(BaseCache):
    def __init__(self):
        self._cache = {}

    def get(self, key: str) -> Optional[CacheEntry]:
        return self._cache.get(key)

    def set(self, key: str, entry: CacheEntry) -> None:
        self._cache[key] = entry

    def exists(self, key: str) -> bool:
        return key in self._cache
