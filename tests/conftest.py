from datetime import UTC, datetime, timedelta
from typing import Any

from pi_cache.base_cache import BaseCache, CacheEntry, ModelMetadata


def create_cache_entry(data: Any, expires_in_hours: int = 1) -> CacheEntry:
    now = datetime.now(UTC)
    metadata = ModelMetadata(
        creation_timestamp=now,
        last_update_timestamp=now,
        expires_at=now + timedelta(hours=expires_in_hours),
        args=(),
        kwargs={},
        from_cache=False,
        data_type=BaseCache._qualified_name(data),
    )
    return CacheEntry(_metadata=metadata, data=data)
