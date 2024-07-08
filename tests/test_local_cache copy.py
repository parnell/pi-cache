from datetime import datetime, timedelta
from typing import Hashable, Optional

import pytest
from pydantic import BaseModel

from qrev_cache.base_cache import BaseCache, CacheEntry, ModelMetadata
from qrev_cache.local_cache import LocalCache, LocalCacheSettings


class TestData(BaseModel):
    value: str


class MockCache(BaseCache):
    def __init__(self):
        self._storage = {}

    def get(self, key: Hashable) -> Optional[CacheEntry]:
        return self._storage.get(key)

    def set(self, key: Hashable, entry: CacheEntry) -> None:
        self._storage[key] = entry

    def exists(self, key: Hashable) -> bool:
        return key in self._storage


@pytest.fixture
def mock_cache():
    return MockCache()


@pytest.fixture
def local_cache(tmp_path):
    return LocalCache(settings=LocalCacheSettings(cache_dir=str(tmp_path)))


@pytest.mark.parametrize("cache_fixture", ["mock_cache", "local_cache"])
# @pytest.mark.parametrize("cache_fixture", ["local_cache"])
class TestBaseCache:
    def test_set_and_get(self, cache_fixture, request):
        cache = request.getfixturevalue(cache_fixture)
        key = "test_key"
        data = TestData(value="test_value")
        metadata = ModelMetadata(
            creation_timestamp=datetime.now(),
            last_update_timestamp=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
            args=(),
            kwargs={},
            from_cache=False,
            data_type=BaseCache._qualified_name(data),
        )
        entry = CacheEntry(metadata=metadata, data=data)

        cache.set(key, entry)
        retrieved_entry = cache.get(key)

        assert retrieved_entry is not None
        assert retrieved_entry.data == data
        assert retrieved_entry.metadata == metadata

    def test_exists(self, cache_fixture, request):
        cache = request.getfixturevalue(cache_fixture)
        key = "test_key"
        data = TestData(value="test_value")
        metadata = ModelMetadata(
            creation_timestamp=datetime.now(),
            last_update_timestamp=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
            args=(),
            kwargs={},
            from_cache=False,
            data_type=BaseCache._qualified_name(data),
        )
        entry = CacheEntry(metadata=metadata, data=data)

        assert not cache.exists(key)
        cache.set(key, entry)
        assert cache.exists(key)

    def test_get_nonexistent_key(self, cache_fixture: str, request):
        cache: BaseCache = request.getfixturevalue(cache_fixture)
        assert cache.get("nonexistent_key") is None

    def test_overwrite_existing_entry(self, cache_fixture: str, request):
        cache: BaseCache = request.getfixturevalue(cache_fixture)
        key = "test_key"
        data1 = TestData(value="test_value_1")
        data2 = TestData(value="test_value_2")

        metadata1 = ModelMetadata(
            creation_timestamp=datetime.now(),
            last_update_timestamp=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
            args=(),
            kwargs={},
            from_cache=False,
            data_type=BaseCache._qualified_name(data1),
        )
        metadata2 = ModelMetadata(
            creation_timestamp=datetime.now(),
            last_update_timestamp=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=2),
            args=(),
            kwargs={},
            from_cache=False,
            data_type=BaseCache._qualified_name(data2),
        )
        entry1 = CacheEntry(metadata=metadata1, data=data1)
        entry2 = CacheEntry(metadata=metadata2, data=data2)

        cache.set(key, entry1)
        cache.set(key, entry2)

        retrieved_entry = cache.get(key)
        assert retrieved_entry
        assert retrieved_entry.data == data2
        assert retrieved_entry.metadata == metadata2


# Add specific tests for LocalCache if needed
class TestLocalCache:
    def test_file_creation(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache = LocalCache(settings=LocalCacheSettings(cache_dir=str(cache_dir)))
        key = "test_key"
        data = TestData(value="test_value")
        metadata = ModelMetadata(
            creation_timestamp=datetime.now(),
            last_update_timestamp=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
            args=(),
            kwargs={},
            from_cache=False,
            data_type=BaseCache._qualified_name(data),
        )
        entry = CacheEntry(metadata=metadata, data=data)

        cache.set(key, entry)
        assert (cache_dir / f"cache_{key}.json").exists()


if __name__ == "__main__":
    pytest.main([__file__])
