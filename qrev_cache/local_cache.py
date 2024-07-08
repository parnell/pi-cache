import os
from pathlib import Path
from typing import Hashable, List, Literal, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings

from qrev_cache.base_cache import BaseCache, CacheEntry


class LocalCacheSettings(BaseSettings):
    cache_dir: str | Path = Path("cache")
    expiration: Optional[str | int] = None
    key_parameters: Optional[list[str]] = None
    time_check: Literal["creation", "last_update", "expires_at"] = "creation"

    @field_validator("cache_dir", mode="before")
    def ensure_path(cls, v):
        return Path(v)


class LocalCache(BaseCache):
    def __init__(self, settings: Optional[LocalCacheSettings] = None):
        self.settings = settings or LocalCacheSettings()
        os.makedirs(self.settings.cache_dir, exist_ok=True)

    def get(self, key: Hashable) -> Optional[CacheEntry]:
        cache_file = os.path.join(self.settings.cache_dir, f"cache_{key}.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                return self.deserialize(f.read())
        return None

    def set(self, key: Hashable, entry: CacheEntry) -> None:
        cache_file = os.path.join(self.settings.cache_dir, f"cache_{key}.json")
        with open(cache_file, "w") as f:
            f.write(self.serialize(entry))

    def exists(self, key: Hashable) -> bool:
        cache_file = os.path.join(self.settings.cache_dir, f"cache_{key}.json")
        return os.path.exists(cache_file)
