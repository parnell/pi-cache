from datetime import datetime, timedelta
from typing import Any

import pytest
from pydantic import BaseModel

from qrev_cache.base_cache import BaseCache, CacheEntry, ModelMetadata
from qrev_cache.local_cache import LocalCache, LocalCacheSettings


class SampleData(BaseModel):
    value: str


@pytest.fixture
def cache(tmp_path):
    return LocalCache(settings=LocalCacheSettings(cache_dir=tmp_path))


def create_cache_entry(data: Any, expires_in_hours: int = 1) -> CacheEntry:
    now = datetime.now()
    metadata = ModelMetadata(
        creation_timestamp=now,
        last_update_timestamp=now,
        expires_at=now + timedelta(hours=expires_in_hours),
        args=(),
        kwargs={},
        from_cache=False,
        data_type=BaseCache._qualified_name(data),
    )
    return CacheEntry(metadata=metadata, data=data)


class TestLocalCache:
    def test_set_and_get(self, cache):
        key = "test_key"
        data = SampleData(value="test_value")
        entry = create_cache_entry(data)

        cache.set(key, entry)
        retrieved_entry = cache.get(key)

        assert retrieved_entry is not None
        assert retrieved_entry.data == data
        assert retrieved_entry.metadata == entry.metadata

    def test_exists(self, cache):
        key = "test_key"
        data = SampleData(value="test_value")
        entry = create_cache_entry(data)

        assert not cache.exists(key)
        cache.set(key, entry)
        assert cache.exists(key)

    def test_get_nonexistent_key(self, cache):
        assert cache.get("nonexistent_key") is None

    def test_overwrite_existing_entry(self, cache):
        key = "test_key"
        data1 = SampleData(value="test_value_1")
        data2 = SampleData(value="test_value_2")

        entry1 = create_cache_entry(data1)
        entry2 = create_cache_entry(data2, expires_in_hours=2)

        cache.set(key, entry1)
        cache.set(key, entry2)

        retrieved_entry = cache.get(key)
        assert retrieved_entry is not None
        assert retrieved_entry.data == data2
        assert retrieved_entry.metadata == entry2.metadata

    def test_file_creation(self, cache, tmp_path):
        key = "test_key"
        data = SampleData(value="test_value")
        entry = create_cache_entry(data)

        cache.set(key, entry)
        assert (tmp_path / f"cache_{key}.json").exists()


if __name__ == "__main__":
    pytest.main([__file__])