import pytest
from datetime import datetime, UTC
from pydantic import BaseModel

from pi_cache.base_cache import BaseCache, cache_decorator, CacheSettings
from pi_cache.models import ModelMetadata
from tests.test_base_cache import MockCache


class SampleData(BaseModel):
    value: str


class MyClass:
    # Create a single shared cache instance for all instances
    _shared_cache = MockCache()

    def __init__(self):
        self.instance_value = "instance"

    @cache_decorator(_shared_cache)
    def instance_method(self, value: str) -> SampleData:
        """This method should NOT share cache between instances by default"""
        return SampleData(value=f"{self.instance_value}_{value}")

    @cache_decorator(_shared_cache, ignore_self=True)
    def shared_instance_method(self, value: str) -> SampleData:
        """This method SHOULD share cache between instances because ignore_self=True"""
        return SampleData(value=f"{self.instance_value}_{value}")


class TestBaseClassCache:
    def setup_method(self):
        """Clear the cache before each test"""
        MyClass._shared_cache._storage.clear()

    def test_instance_method_cache(self):
        """Test that the same instance's repeated calls use cache"""
        test_obj = MyClass()
        
        # First call - should not be from cache
        result1 = test_obj.instance_method("test")
        assert result1.value == "instance_test"
        assert result1._metadata.from_cache is False
        
        # Second call - should be from cache
        result2 = test_obj.instance_method("test")
        assert result2.value == "instance_test"
        assert result2._metadata.from_cache is True

    def test_different_instances_no_share_cache(self):
        """Test that different instances don't share cache by default"""
        test_obj1 = MyClass()
        test_obj2 = MyClass()
        
        # Call with first instance
        result1 = test_obj1.instance_method("test")
        assert result1._metadata.from_cache is False
        
        # Call with second instance - should NOT hit cache
        result2 = test_obj2.instance_method("test")
        assert result2._metadata.from_cache is False
        assert result1.value == result2.value

    def test_different_instances_share_cache(self):
        """Test that different instances share cache when ignore_self=True"""
        test_obj1 = MyClass()
        test_obj2 = MyClass()
        
        # Call with first instance
        result1 = test_obj1.shared_instance_method("test")
        assert result1._metadata.from_cache is False
        
        # Call with second instance - should hit cache because ignore_self=True
        result2 = test_obj2.shared_instance_method("test")
        assert result2._metadata.from_cache is True
        assert result1.value == result2.value

    def test_different_parameters_different_cache(self):
        """Test that different parameters create different cache entries"""
        test_obj = MyClass()
        
        # Call with different parameters
        result1 = test_obj.instance_method("test1")
        result2 = test_obj.instance_method("test2")
        
        assert result1.value != result2.value
        assert result1._metadata.from_cache is False
        assert result2._metadata.from_cache is False
        
        # Repeat calls should hit cache
        result3 = test_obj.instance_method("test1")
        result4 = test_obj.instance_method("test2")
        
        assert result3._metadata.from_cache is True
        assert result4._metadata.from_cache is True


if __name__ == "__main__":
    pytest.main(["-v",  __file__])
