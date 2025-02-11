from typing import Optional, Callable

from pi_cache.base_cache import BaseCache, CacheEntry, FuncCall, cache_decorator, P, T


class InMemoryCache(BaseCache):
    def __init__(self):
        super().__init__()  # Initialize with default settings
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


def in_memory_cache(
    ignore_self: bool = False,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator that caches function results in memory.

    Args:
        ignore_self: If True, ignores the self parameter when generating cache key for class methods
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        cache_instance = InMemoryCache()
        return cache_decorator(cache_instance, ignore_self=ignore_self)(func)

    return decorator
