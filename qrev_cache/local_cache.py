import os
from pathlib import Path
from typing import Callable, Optional, Union

from pydantic import field_validator

from qrev_cache.base_cache import (
    BaseCache,
    CacheEntry,
    CacheSettings,
    FuncCall,
    P,
    T,
    TimeCheck,
    cache_decorator,
)


class LocalCacheSettings(CacheSettings):
    cache_dir: str | Path = Path("cache")
    expiration: Optional[str | int] = None
    key_parameters: Optional[list[str]] = None

    @field_validator("cache_dir", mode="before")
    def ensure_path(cls, v):
        return Path(v)


class LocalCache(BaseCache):
    def __init__(self, settings: Optional[LocalCacheSettings] = None):
        self.settings = settings or LocalCacheSettings()
        os.makedirs(self.settings.cache_dir, exist_ok=True)

    def get(self, func_call: FuncCall[LocalCacheSettings]) -> Optional[CacheEntry]:
        key = self._generate_cache_key(func_call)
        cache_file = os.path.join(func_call.settings.cache_dir, f"cache_{key}.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                return self.deserialize(f.read())
        return None

    def set(self, func_call: FuncCall[LocalCacheSettings], entry: CacheEntry) -> None:
        key = self._generate_cache_key(func_call)
        cache_file = os.path.join(func_call.settings.cache_dir, f"cache_{key}.json")
        with open(cache_file, "w") as f:
            f.write(self.serialize(entry))

    def exists(self, func_call: FuncCall[LocalCacheSettings]) -> bool:
        key = self._generate_cache_key(func_call)
        cache_file = os.path.join(func_call.settings.cache_dir, f"cache_{key}.json")
        return os.path.exists(cache_file)


def local_cache(
    settings: Optional[LocalCacheSettings] = None,
    expiration: Optional[Union[str, int]] = None,
    key_parameters: Optional[list[str]] = None,
    time_check: Optional[TimeCheck] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    return_metadata_as_member: Optional[bool] = None,
    return_metadata_on_primitives: Optional[bool] = None,
):
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        cache_settings = settings or LocalCacheSettings()

        if expiration is not None:
            cache_settings.expiration = expiration
        if key_parameters is not None:
            cache_settings.key_parameters = key_parameters
        if time_check is not None:
            cache_settings.time_check = time_check
        if cache_dir is not None:
            cache_settings.cache_dir = cache_dir
        if return_metadata_as_member is not None:
            cache_settings.return_metadata_as_member = return_metadata_as_member
        if return_metadata_on_primitives is not None:
            cache_settings.return_metadata_on_primitives = return_metadata_on_primitives

        cache_instance = LocalCache(settings=cache_settings)
        return cache_decorator(cache_instance)(func)

    return decorator
