import importlib.util

from pi_cache.base_cache import BaseCache, BaseSettings
from pi_cache.file_cache import FileCache, FileCacheSettings, file_cache
from pi_cache.models import MetaMixin, ModelMetadata, TimeCheck

__all__ = [
    "BaseCache",
    "BaseSettings",
    "ModelMetadata",
    "TimeCheck",
    "FileCache",
    "FileCacheSettings",
    "file_cache",
    "MetaMixin",
]

if importlib.util.find_spec("pymongo"):
    from pi_cache.mongo_cache import (
        MongoCache as MongoCache,
    )
    from pi_cache.mongo_cache import (
        MongoCacheSettings as MongoCacheSettings,
    )
    from pi_cache.mongo_cache import (
        Var as Var,
    )
    from pi_cache.mongo_cache import (
        mongo_cache as mongo_cache,
    )

    __all__.extend(["MongoCache", "MongoCacheSettings", "mongo_cache", "Var"])
