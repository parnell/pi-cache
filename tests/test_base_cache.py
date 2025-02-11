import json
from datetime import UTC, datetime, timedelta
from typing import Any, Hashable, Optional, cast, Union
import hashlib

import pytest
from pydantic import BaseModel

from pi_cache.base_cache import (
    BaseCache,
    CacheEntry,
    CacheSettings,
    FuncCall,
    ModelMetadata,
    TimeCheck,
    TypeRegistry,
    cache_decorator,
    custom_decoder,
    custom_encoder,
    is_cache_valid,
    make_hashable,
)
from pi_cache.models import MetadataCarrier, MetaMixin
from tests.conftest import create_cache_entry


class SampleData(BaseModel):
    value: str


class MockCache(BaseCache):
    def __init__(self, settings: Optional[CacheSettings] = None):
        super().__init__(settings)
        self._storage = {}
        self.use_flat_metadata = False

    def _generate_cache_key(self, func_call: Union[FuncCall, str]) -> str:
        if isinstance(func_call, str):
            return func_call  # Use string directly as key
        # Use the proper key generation from BaseCache
        key_content = self._generate_key_content(func_call)
        # Convert all values to hashable types
        hashable_content = make_hashable(key_content)
        # Convert to a stable string representation
        key_str = str(hashable_content)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, func_call: Union[FuncCall, str]) -> Optional[CacheEntry]:
        key = self._generate_cache_key(func_call)
        return self._storage.get(key)

    def set(self, func_call: Union[FuncCall, str], entry: CacheEntry) -> None:
        key = self._generate_cache_key(func_call)
        self._storage[key] = entry

    def exists(self, func_call: Union[FuncCall, str]) -> bool:
        key = self._generate_cache_key(func_call)
        return key in self._storage


@pytest.fixture
def cache():
    return MockCache()

class TestBaseCache:
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

    def test_serialization_deserialization(self, cache):
        key = "test_key"
        data = SampleData(value="test_value")
        entry = create_cache_entry(data)

        cache.set(key, entry)
        serialized = cache.serialize(entry)
        deserialized = cache.deserialize(serialized)

        assert deserialized.data == data
        assert deserialized.metadata == entry.metadata


    def test_cache_validation(self, cache):
        key = "test_key"
        data = SampleData(value="test_value")
        entry = create_cache_entry(data, expires_in_hours=1)

        cache.set(key, entry)

        # Create CacheSettings with a 1-hour expiration
        settings = CacheSettings(expiration="1h", time_check=TimeCheck.CREATION)

        now = datetime.now(UTC)
        # Test that the entry is valid now
        assert is_cache_valid(entry.metadata, now, settings=settings)

        # Test that the entry is invalid after expiration
        future_time = datetime.now(UTC) + timedelta(hours=2)
        assert not is_cache_valid(entry.metadata, future_time, settings=settings)

    def test_type_registry(self):
        # Register SampleData with TypeRegistry
        TypeRegistry.register_pydantic_model(SampleData)

        data = SampleData(value="test")
        serialized = custom_encoder(data)
        deserialized = custom_decoder(serialized)

        assert isinstance(deserialized, SampleData)
        assert deserialized.value == "test"

        # Test that the serialized form matches what we expect
        expected_serialized = {
            "__pydantic_model__": BaseCache._qualified_name(data),
            "__data__": {"value": "test"},
        }
        assert serialized == expected_serialized

    def test_metadata_carrier(self):
        data = SampleData(value="test")
        metadata = ModelMetadata(
            creation_timestamp=datetime.now(),
            last_update_timestamp=datetime.now(),
            expires_at=None,
            args=(),
            kwargs={},
            from_cache=False,
            data_type=BaseCache._qualified_name(data),
        )
        carrier = MetadataCarrier(data, metadata)

        assert carrier.metadata == metadata
        assert str(carrier) == str(data)
        assert carrier == data

    def test_primitive_cache_int_raw_type(self, cache):
        data = 1

        @cache_decorator(cache)
        def cached_int_function(x) -> int:
            return x

        r = cached_int_function(data)
        assert r == 1
        assert r + 1 == 2
        assert type(r) == int

        r = cached_int_function(data)
        assert r == 1
        assert type(r) == int

    def test_cache_models(self, cache):
        class T(BaseModel):
            x: int

        @cache_decorator(cache)
        def cached_function(x: int) -> T:
            return T(x=x)

        r = cached_function(3)
        assert r._metadata # type: ignore
        assert type(r) == T

        assert r.x == 3

    # def test_primitive_cache_int(self, cache):
    #     data = 1

    #     @cache_decorator(cache, CacheSettings(return_metadata_on_primitives=True))
    #     def cached_int_function(x) -> int:
    #         return x

    #     r = cached_int_function(data)
    #     assert r == 1
    #     assert r + 1 == 2
    #     r = cast(MetaMixin, r)
    #     assert r._metadata.from_cache == False

    #     r = cached_int_function(data)
    #     assert r == 1
    #     r = cast(MetaMixin, r)
    #     assert r._metadata.from_cache == True

    def test_flat_metadata(self, cache):
        class T(BaseModel):
            x: int

        cache.use_flat_metadata = True

        @cache_decorator(cache)
        def cached_function(x: int) -> T:
            return T(x=x)

        r = cached_function(3)
        assert r.x == 3
        r = cast(MetaMixin, r)
        assert r._metadata

        assert r._metadata.from_cache == False

        r = cached_function(3)
        assert r.x == 3
        r = cast(MetaMixin, r)
        assert r._metadata.from_cache == True

    # def test_custom_encoder_decoder(self):
    #     data = {"datetime": datetime.now(), "sample": SampleData(value="test")}
    #     encoded = json.dumps(data, default=custom_encoder)
    #     decoded = json.loads(encoded, object_hook=custom_decoder)

    #     assert isinstance(decoded["datetime"], datetime)
    #     assert isinstance(decoded["sample"], SampleData)
    #     assert decoded["sample"].value == "test"

if __name__ == "__main__":
    pytest.main([__file__])
