from typing import Optional

from qrev_cache.base_cache import BaseCache, CacheEntry, FuncCall


class InMemoryCache(BaseCache):
    def __init__(self):
        self._cache = {}

    def get(self, func_call: FuncCall) -> Optional[CacheEntry]:
        key = self._generate_cache_key(func_call)
        return self._cache.get(key)

    def set(self, func_call: FuncCall, entry: CacheEntry) -> None:
        key = self._generate_cache_key(func_call)
        self._cache[key] = entry

    def exists(self, func_call: FuncCall) -> bool:
        key = self._generate_cache_key(func_call)
        return key in self._cache
