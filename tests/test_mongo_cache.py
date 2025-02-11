import uuid
from typing import Any

import pytest
from pi_conf import load_config
from pydantic import BaseModel

# Try to import pymongo at module level
try:
    from pymongo import MongoClient

    from pi_cache import MongoCache, MongoCacheSettings, Var, mongo_cache

    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False


cfg = load_config(".config-test.toml")
cfg.to_env()

# Skip all tests in this module if pymongo is not installed
pytestmark = pytest.mark.skipif(not PYMONGO_AVAILABLE, reason="pymongo is not installed")


class SampleData(BaseModel):
    s: str
    i: int


@pytest.fixture(scope="session")
def mongo_database():
    if not cfg:
        pytest.skip("Skipping MongoDB tests. Set environment variables to run these tests.")

    # Check if MongoDB URI is valid
    try:
        settings = MongoCacheSettings()
        client = MongoClient(settings.uri)
        # Try to ping the server to check the connection
        client.admin.command("ping")
    except ValueError as e:
        pytest.skip(f"Skipping MongoDB tests due to configuration error: {str(e)}")
    except Exception as e:
        pytest.skip(f"Skipping MongoDB tests due to connection error: {str(e)}")

    # Setup: Create the database
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
        unique_collection_name = f"test_collection_{uuid.uuid4().hex}"
        cache = MongoCache(
            MongoCacheSettings(
                collection=unique_collection_name, return_metadata_on_primitives=True
            )
        )
        client = cache.client
        assert client
        db = client[cache.settings.database]
        collection = db[cache.settings.collection]
        yield cache
        try:
            collection.delete_many({})
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

    def test_query_with_dict_data(self, cache):
        @mongo_cache(cache=cache, query={"s": Var("filter_variable")}, data_type=SampleData)
        def test_func(filter_variable: str) -> dict[str, Any]:
            return {"s": filter_variable, "i": hash(filter_variable)}

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


if __name__ == "__main__":
    pytest.main(["-v", __file__])
