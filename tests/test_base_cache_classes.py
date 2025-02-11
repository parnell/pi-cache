import pytest
from datetime import datetime, UTC
from pydantic import BaseModel
from dataclasses import dataclass
from typing import Optional

from pi_cache.base_cache import BaseCache, cache_decorator, CacheSettings
from pi_cache.models import ModelMetadata
from tests.test_base_cache import MockCache


@dataclass
class DataClassResult:
    """A dataclass to be used as a return type"""
    value: str
    timestamp: datetime
    extra: Optional[str] = None


class ReturnDataClass:
    # Create a single shared cache instance for all instances
    _shared_cache = MockCache()

    def __init__(self):
        self.instance_value = "instance"

    @cache_decorator(_shared_cache)
    def instance_method(self, value: str) -> DataClassResult:
        """This method should NOT share cache between instances by default"""
        return DataClassResult(
            value=f"{self.instance_value}_{value}",
            timestamp=datetime.now(UTC),
        )

    @cache_decorator(_shared_cache, ignore_self=True)
    def shared_instance_method(self, value: str) -> DataClassResult:
        """This method SHOULD share cache between instances because ignore_self=True"""
        return DataClassResult(
            value=f"{self.instance_value}_{value}",
            timestamp=datetime.now(UTC),
            extra="shared",
        )


class TestReturnDataClass:
    def setup_method(self):
        """Clear the cache before each test"""
        ReturnDataClass._shared_cache._storage.clear()

    def test_instance_method_cache(self):
        """Test that the same instance's repeated calls use cache"""
        test_obj = ReturnDataClass()
        
        # First call - should not be from cache
        result1 = test_obj.instance_method("test")
        assert isinstance(result1, DataClassResult)
        assert result1.value == "instance_test"
        assert result1._metadata.from_cache is False # type: ignore
        
        # Second call - should be from cache
        result2 = test_obj.instance_method("test")
        assert isinstance(result2, DataClassResult)
        assert result2.value == "instance_test"
        assert result2._metadata.from_cache is True # type: ignore  
        
        # Timestamps should be identical since second result is from cache
        assert result1.timestamp == result2.timestamp

    def test_different_instances_no_share_cache(self):
        """Test that different instances don't share cache by default"""
        test_obj1 = ReturnDataClass()
        test_obj2 = ReturnDataClass()
        
        # Call with first instance
        result1 = test_obj1.instance_method("test")
        assert result1._metadata.from_cache is False # type: ignore
        first_timestamp = result1.timestamp
        
        # Call with second instance - should NOT hit cache
        result2 = test_obj2.instance_method("test")
        assert result2._metadata.from_cache is False # type: ignore
        assert result1.value == result2.value
        # Timestamps should be different since it's a new call
        assert first_timestamp != result2.timestamp

    def test_different_instances_share_cache(self):
        """Test that different instances share cache when ignore_self=True"""
        test_obj1 = ReturnDataClass()
        test_obj2 = ReturnDataClass()
        
        # Call with first instance
        result1 = test_obj1.shared_instance_method("test")
        assert result1._metadata.from_cache is False # type: ignore
        first_timestamp = result1.timestamp
        
        # Call with second instance - should hit cache because ignore_self=True
        result2 = test_obj2.shared_instance_method("test")
        assert result2._metadata.from_cache is True # type: ignore
        assert result1.value == result2.value
        # Timestamps should be identical since second result is from cache
        assert first_timestamp == result2.timestamp
        assert result1.extra == result2.extra == "shared"

    def test_different_parameters_different_cache(self):
        """Test that different parameters create different cache entries"""
        test_obj = ReturnDataClass()
        
        # Call with different parameters
        result1 = test_obj.instance_method("test1")
        result2 = test_obj.instance_method("test2")
        
        assert result1.value != result2.value
        assert result1._metadata.from_cache is False # type: ignore
        assert result2._metadata.from_cache is False # type: ignore
        assert result1.timestamp != result2.timestamp
        
        # Repeat calls should hit cache
        result3 = test_obj.instance_method("test1")
        result4 = test_obj.instance_method("test2")
        
        assert result3._metadata.from_cache is True # type: ignore
        assert result4._metadata.from_cache is True # type: ignore  
        # Cached calls should have same timestamps as original calls
        assert result1.timestamp == result3.timestamp
        assert result2.timestamp == result4.timestamp


if __name__ == "__main__":
    pytest.main(["-v",  __file__])
