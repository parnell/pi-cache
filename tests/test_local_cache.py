
import pytest
from pydantic import BaseModel

from qrev_cache.base_cache import FuncCall
from qrev_cache.local_cache import LocalCache, LocalCacheSettings, local_cache
from tests.conftest import create_cache_entry


class SampleData(BaseModel):
    value: str


@pytest.fixture
def cache(tmp_path):
    lc = LocalCache(settings=LocalCacheSettings(cache_dir=tmp_path))

    def _generate_cache_key(func_call: FuncCall) -> str:
        return str(func_call)

    lc._generate_cache_key = _generate_cache_key
    return lc

class SimpleKey:
    def __init__(self, key: str, cache_instance: LocalCache):
        self.key = key
        self.settings = cache_instance.settings

class TestLocalCache:
    def test_set_and_get(self, cache):
        key = SimpleKey("test_key", cache)

        data = SampleData(value="test_value")
        entry = create_cache_entry(data)

        cache.set(key, entry)
        retrieved_entry = cache.get(key)

        assert retrieved_entry is not None
        assert retrieved_entry.data == data
        assert retrieved_entry.metadata == entry.metadata

    def test_exists(self, cache):
        key = SimpleKey("test_key", cache)
        data = SampleData(value="test_value")
        entry = create_cache_entry(data)

        assert not cache.exists(key)
        cache.set(key, entry)
        assert cache.exists(key)

    def test_get_nonexistent_key(self, cache):
        key = SimpleKey("nonexistent_key", cache)
        assert cache.get(key) is None

    def test_overwrite_existing_entry(self, cache):
        key = SimpleKey("test_key", cache)
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
        key = SimpleKey("test_key", cache)
        data = SampleData(value="test_value")
        entry = create_cache_entry(data)

        cache.set(key, entry)
        assert (tmp_path / f"cache_{key}.json").exists()

    def test_local_cache_decorator(self, tmp_path):
        @local_cache(cache_dir=tmp_path)
        def test_func():
            return SampleData(value="test_value")

        data = test_func()
        assert data.value == "test_value"
        assert data._metadata.from_cache is False

        data = test_func()
        assert data.value == "test_value"
        assert data._metadata.from_cache is True


if __name__ == "__main__":
    pytest.main([__file__])
