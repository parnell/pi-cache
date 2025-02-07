import importlib.util

from qrev_cache.base_cache import BaseCache, BaseSettings
from qrev_cache.file_cache import FileCache, FileCacheSettings, local_cache
from qrev_cache.models import MetaMixin, ModelMetadata, TimeCheck

__all__ = [
    "BaseCache",
    "BaseSettings",
    "ModelMetadata",
    "TimeCheck",
    "FileCache",
    "FileCacheSettings",
    "local_cache",
    "MetaMixin",
]

if importlib.util.find_spec("pymongo"):
    from qrev_cache.mongo_cache import (
        MongoCache as MongoCache,
    )
    from qrev_cache.mongo_cache import (
        MongoCacheSettings as MongoCacheSettings,
    )
    from qrev_cache.mongo_cache import (
        Var as Var,
    )
    from qrev_cache.mongo_cache import (
        mongo_cache as mongo_cache,
    )

    __all__.extend(["MongoCache", "MongoCacheSettings", "mongo_cache", "Var"])
