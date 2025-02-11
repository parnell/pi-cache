import os
import fcntl
import errno
from pathlib import Path
from typing import Callable, Optional, Union, Iterator
import time
from contextlib import contextmanager
from pydantic import field_validator

from pi_cache.base_cache import (
    BaseCache,
    CacheEntry,
    CacheSettings,
    FuncCall,
    P,
    T,
    TimeCheck,
    cache_decorator,
)


class FileCacheSettings(CacheSettings):
    cache_dir: str | Path = Path("cache")
    expiration: Optional[str | int] = None
    key_parameters: Optional[list[str]] = None
    lock_timeout: float = 10.0  # Timeout in seconds for acquiring locks

    @field_validator("cache_dir", mode="before")
    def ensure_path(cls, v):
        return Path(v)


class FileCache(BaseCache):
    def __init__(self, settings: Optional[FileCacheSettings] = None):
        self.settings: FileCacheSettings = settings or FileCacheSettings()
        os.makedirs(self.settings.cache_dir, exist_ok=True)

    @contextmanager
    def _file_lock(self, filepath: str | Path) -> Iterator[None]:
        """Provides exclusive file locking using fcntl."""
        lock_path = str(filepath) + '.lock'
        lock_file = None
        
        try:
            lock_file = open(lock_path, 'w')
            # Use non-blocking to implement timeout
            start_time = time.time()
            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (IOError, OSError) as e:
                    if e.errno != errno.EAGAIN:  # Raise if not "temporarily unavailable"
                        raise

                    if time.time() - start_time > self.settings.lock_timeout:
                        raise TimeoutError(f"Could not acquire lock for {filepath} after {self.settings.lock_timeout}s")
                    time.sleep(0.1)
            yield
        finally:
            if lock_file is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
                try:
                    os.unlink(lock_path)
                except OSError:
                    pass

    def get(self, func_call: FuncCall[FileCacheSettings]) -> Optional[CacheEntry]:
        key = self._generate_cache_key(func_call)
        cache_file = os.path.join(func_call.settings.cache_dir, f"cache_{key}.json")
        
        if not os.path.exists(cache_file):
            return None
            
        with self._file_lock(cache_file):
            try:
                with open(cache_file, "r") as f:
                    return self.deserialize(f.read())
            except (ValueError, OSError):
                # Handle corrupted cache files by treating them as cache misses
                try:
                    os.unlink(cache_file)
                except OSError:
                    pass
                return None

    def set(self, func_call: FuncCall[FileCacheSettings], entry: CacheEntry) -> None:
        key = self._generate_cache_key(func_call)
        cache_file = os.path.join(func_call.settings.cache_dir, f"cache_{key}.json")
        
        # Ensure the directory exists (in case it was deleted)
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        
        with self._file_lock(cache_file):
            # Write to temporary file first
            temp_file = cache_file + '.tmp'
            try:
                with open(temp_file, "w") as f:
                    f.write(self.serialize(entry))
                # Atomic rename
                os.replace(temp_file, cache_file)
            finally:
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass

    def exists(self, func_call: FuncCall[FileCacheSettings]) -> bool:
        key = self._generate_cache_key(func_call)
        cache_file = os.path.join(func_call.settings.cache_dir, f"cache_{key}.json")
        
        with self._file_lock(cache_file):
            return os.path.exists(cache_file)


def file_cache(
    settings: Optional[FileCacheSettings] = None,
    expiration: Optional[Union[str, int]] = None,
    key_parameters: Optional[list[str]] = None,
    time_check: Optional[TimeCheck] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    return_metadata_as_member: Optional[bool] = None,
    return_metadata_on_primitives: Optional[bool] = None,
    cache_only: Optional[bool] = None,
    lock_timeout: Optional[float] = None,
    ignore_self: bool = False,
):
    """
    Decorator that caches function results in files.
    
    Args:
        settings: Cache settings
        expiration: Cache expiration time
        key_parameters: List of parameter names to use for cache key
        time_check: How to check if cache is expired
        cache_dir: Directory to store cache files
        return_metadata_as_member: Whether to return metadata as member
        return_metadata_on_primitives: Whether to return metadata for primitives
        cache_only: Whether to only use cache
        lock_timeout: Timeout for file locks
        ignore_self: If True, ignores the self parameter when generating cache key for class methods
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        cache_settings = settings or FileCacheSettings()

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
        if cache_only is not None:
            cache_settings.cache_only = cache_only
        if lock_timeout is not None:
            cache_settings.lock_timeout = lock_timeout

        cache_instance = FileCache(settings=cache_settings)
        return cache_decorator(cache_instance, ignore_self=ignore_self)(func)

    return decorator