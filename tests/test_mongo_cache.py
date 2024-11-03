import time
import uuid
from typing import Any, cast

import pytest
from pi_conf import load_config
from pydantic import BaseModel
from pymongo import MongoClient

from qrev_cache import MetaMixin, MongoCache, MongoCacheSettings, Var, mongo_cache

cfg = load_config(".config-test.toml")
cfg.to_env()


class SampleData(BaseModel):
    s: str
    i: int


@pytest.fixture(scope="session")
def mongo_database():
    if not cfg:
        pytest.skip(f"Skipping MongoDB tests. Set environment variables to run these tests.")

    # Setup: Create the database
    settings = MongoCacheSettings()
    client = MongoClient(settings.uri)
    db = client[settings.database]

    print(f"Created database: {settings.database}")

    yield db

    # Teardown: Delete the database
    client.drop_database(settings.database)
    client.close()
    print(f"Dropped database: {settings.database}")


class TestMongoCache:
    @pytest.fixture
    def cache(self, mongo_database):
        # Generate a unique collection name for this test run
        unique_collection_name = f"test_collection_{uuid.uuid4().hex}"
        cache = MongoCache(MongoCacheSettings(collection=unique_collection_name, return_metadata_on_primitives=True))
        client = cache.client
        assert client
        db = client[cache.settings.database]
        collection = db[cache.settings.collection]
        yield cache
        try:
            # Cleanup after each test
            collection.delete_many({})  # Delete all documents in the collection
            print(
                f"Successfully deleted all documents from collection: {cache.settings.collection}"
            )
            cache.safe_close()
        except Exception as e:
            print(f"Error during cleanup: {e}")
            raise
        finally:
            if cache.client:
                cache.client.close()

    # def test_query(self, cache):
    #     @mongo_cache(cache=cache, query={"s": Var("filter_variable")}, data_type=SampleData)
    #     def test_func(filter_variable: str):
    #         return SampleData(s=filter_variable, i=hash(filter_variable))

    #     # First call, should not be cached
    #     r1 = test_func("test_value")

    #     assert r1 is not None
    #     assert isinstance(r1, SampleData)
    #     r1 = cast(MetaMixin, r1)
    #     assert r1._metadata is not None
    #     assert r1._metadata.from_cache is False

    #     # Second call, should be cached
    #     r2 = test_func("test_value")
    #     r2 = cast(MetaMixin, r2)
    #     assert r2._metadata is not None
    #     assert r2._metadata.from_cache is True
    #     assert r1 == r2

    #     # Different value, should not be cached
    #     r = test_func("another_value")
    #     r = cast(MetaMixin, r)
    #     assert r._metadata is not None
    #     assert r._metadata.from_cache is False

    def test_query_with_dict_data(self, cache):
        @mongo_cache(cache=cache, query={"s": Var("filter_variable")}, data_type=SampleData)
        def test_func(filter_variable: str) -> dict[str, Any]:
            return {"s":filter_variable, "i":hash(filter_variable)}

        # First call, should not be cached
        r1 = test_func("test_value")

        assert r1 is not None
        assert isinstance(r1, dict)
        
        assert r1["_metadata"] is not None
        assert r1["_metadata"].from_cache is False

        # Second call, should be cached
        r2 = test_func("test_value")
        
        assert r2["_metadata"] is not None
        assert r2["_metadata"].from_cache is True
        assert r1 == r2

        # Different value, should not be cached
        r = test_func("another_value")
        
        assert r["_metadata"] is not None
        assert r["_metadata"].from_cache is False
    # def test_multiple_variables(self, cache):
    #     @mongo_cache(cache=cache, query={"s": Var("s"), "i": Var("i")}, data_type=SampleData)
    #     def test_func(s: str, i: int):
    #         return SampleData(s=s, i=i)

    #     r1 = test_func("test", 1)
    #     assert cast(MetaMixin, r1)._metadata.from_cache is False

    #     r2 = test_func("test", 1)
    #     assert cast(MetaMixin, r2)._metadata.from_cache is True
    #     assert r1 == r2

    #     r3 = test_func("test", 2)
    #     assert cast(MetaMixin, r3)._metadata.from_cache is False

    # def test_cache_expiration(self, cache):
    #     @mongo_cache(
    #         cache=cache, query={"s": Var("filter_variable")}, data_type=SampleData, expiration=1
    #     )
    #     def test_func(filter_variable: str):
    #         return SampleData(s=filter_variable, i=hash(filter_variable))

    #     r = test_func("test_value")
    #     assert cast(MetaMixin, r)._metadata.from_cache is False
    #     r = test_func("test_value")
    #     assert cast(MetaMixin, r)._metadata.from_cache is True

    #     time.sleep(1.1)  # Total sleep time > 1 second

    #     r = test_func("test_value")
    #     assert cast(MetaMixin, r)._metadata.from_cache is False


if __name__ == "__main__":
    pytest.main([__file__])
