import functools
import inspect
import re
import threading
from logging import getLogger
from typing import Any, Callable, Optional, Union

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure

from qrev_cache.base_cache import (
    BaseCache,
    CacheEntry,
    CacheSettings,
    FuncCall,
    P,
    T,
    TimeCheck,
    cache_decorator,
)

log = getLogger(__name__)


class MissingVariableError(Exception):
    pass


class Var:
    def __init__(self, var_name):
        self.var_name = var_name

    def __str__(self):
        return f"Var({self.var_name})"

    def __repr__(self):
        return self.__str__()

    def resolve(self, context):
        parts = self.var_name.split(".")
        value = context
        for part in parts:
            if value is None:
                return None
            if isinstance(value, dict):
                value = value.get(part)
            else:  # Object
                try:
                    value = getattr(value, part)
                except AttributeError:
                    raise MissingVariableError(
                        f"Variable '{self.var_name}' not found in function arguments"
                    )
        return value


class MongoCacheSettings(CacheSettings):
    uri: str = ""
    database: str = ""
    collection: str = ""
    expiration: Optional[str | int] = None
    key_parameters: Optional[list[str]] = None
    query: dict = {}
    is_flat_data: bool = Field(
        default=True, description="By default we want Mongo to store data as a flat structure"
    )
    skip_initial_verification: bool = False

    model_config = SettingsConfigDict(env_prefix="MONGO_CACHE_")

    def uri_masked(self) -> str:
        # Handle standard MongoDB URI format
        pattern = r"(mongodb(?:\+srv)?):\/\/(?:([^:@]+)(?::([^@]+))?@)?([^/?]+)(.+)?"
        match = re.match(pattern, self.uri)

        if match:
            scheme, username, password, hosts, rest = match.groups()

            if password:
                masked_uri = f"{scheme}://"
                if username:
                    masked_uri += f"{username}:xxxxx@"
                masked_uri += hosts
                if rest:
                    masked_uri += rest
                return masked_uri

        # If the URI doesn't match the expected format, return it unchanged
        return self.uri

    def __repr__(self):
        return (
            f"MongoCacheSettings(uri='{self.uri_masked()}', database='{self.database}', "
            f"collection='{self.collection}', expiration='{self.expiration}', "
            f"key_parameters={self.key_parameters}, query={self.query})"
        )

    def __str__(self):
        return self.__repr__()


def get_args_kwargs_dict(func, *args, **kwargs):
    # Get the signature of the function
    signature = inspect.signature(func)

    # Bind the *args and **kwargs to the function signature
    bound_args = signature.bind(*args, **kwargs)
    bound_args.apply_defaults()

    # Create a dictionary from the bound arguments
    args_kwargs_dict = {k: v for k, v in bound_args.arguments.items()}

    return args_kwargs_dict


class MongoCache(BaseCache):
    def __init__(self, settings: Optional[MongoCacheSettings] = None):
        self.settings: MongoCacheSettings = settings or MongoCacheSettings()
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
        self.collection: Optional[Collection] = None
        if not self.settings.skip_initial_verification:
            self._create_connection()

    def get(self, func_call: FuncCall) -> Optional[CacheEntry]:
        assert self.collection is not None
        query = self._make_query(func_call)
        result = self.collection.find_one(query)
        if result is None:
            return None
        return self.deserialize(result)

    def set(self, func_call: FuncCall, entry: CacheEntry) -> None:
        assert self.collection is not None
        d = self._dump_cache_entry(entry, func_call.settings)
        self.collection.insert_one(d)

    def exists(self, func_call: FuncCall[MongoCacheSettings]) -> bool:
        return self.get(func_call) is not None

    def _create_connection(
        self,
        serverSelectionTimeoutMS: int = 30000,
        connectTimeoutMS: Optional[int] = None,
        socketTimeoutMS: Optional[int] = None,
    ):
        self.client = MongoClient(
            self.settings.uri,
            serverSelectionTimeoutMS=serverSelectionTimeoutMS,
            connectTimeoutMS=connectTimeoutMS,
            socketTimeoutMS=socketTimeoutMS,
        )
        assert self.client is not None
        assert self.settings.database is not None
        self.db = self.client[self.settings.database]
        self.collection = self.db[self.settings.collection]

    def __enter__(self):
        self._create_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.safe_close()

    def _verify_connection(self) -> bool:
        if self.client is None:
            raise ConnectionFailure("MongoDB client is not initialized")
        try:
            self.client.admin.command("ping")
            return True
        except ConnectionFailure:
            log.error(f"MongoDB connection failure {self.settings}")
            return False

    def safe_close(self):
        if self.client:

            def close_client():
                if self.client:
                    self.client.close()

            close_thread = threading.Thread(target=close_client)
            close_thread.start()
            close_thread.join(timeout=5.0)

            if close_thread.is_alive():
                log.warning("MongoDB client close operation timed out")
        self.client = None
        self.db = None
        self.collection = None

    def _make_query(self, func_call: FuncCall[MongoCacheSettings]) -> dict[str, Any]:
        """
        Creates a MongoDB query by substituting variables from function arguments.

        Args:
            func_call: An object containing information about the function call and cache settings.

        Returns:
            A dictionary representing the MongoDB query with variables substituted.

        Raises:
            MissingVariableError: If a variable specified in the query is not found in the function arguments.
        """
        args_dict = get_args_kwargs_dict(func_call.func, *func_call.args, **func_call.kwargs)
        query = func_call.settings.query.copy()  # Shallow copy is usually sufficient
        if not func_call.settings.is_flat_data:
            query = {"data": query}

        def substitute_var(value: Union[Var, Any]) -> Any:
            if isinstance(value, Var):
                resolved = value.resolve(args_dict)
                if resolved is None:
                    raise MissingVariableError(
                        (
                            f"Variable '{value.var_name}' not found in function arguments.\n"
                            f"Available variables: {args_dict}"
                        )
                    )
                return resolved
            elif isinstance(value, dict):
                return {k: substitute_var(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute_var(item) for item in value]
            return value

        return substitute_var(query)


def create_mongo_cache_settings(
    settings: Optional[MongoCacheSettings] = None, env_prefix: Optional[str] = None
) -> MongoCacheSettings:
    if settings:
        return settings

    class DynamicMongoCacheSettings(MongoCacheSettings):
        model_config = (
            SettingsConfigDict(env_prefix=env_prefix) if env_prefix else SettingsConfigDict()
        )

    return DynamicMongoCacheSettings()


def mongo_cache(
    cache: Optional[MongoCache] = None,
    settings: Optional[MongoCacheSettings] = None,
    uri: Optional[str] = None,
    database: Optional[str] = None,
    collection: Optional[str] = None,
    query: Optional[dict] = None,
    env_prefix: Optional[str] = None,
    expiration: Optional[Union[str, int]] = None,
    key_parameters: Optional[list[str]] = None,
    time_check: Optional[TimeCheck] = None,
    return_metadata_as_member: Optional[bool] = None,
    return_metadata_on_primitives: Optional[bool] = None,
    flat_data: Optional[bool] = None,
    data_type: Optional[type] = None,
    cache_only: Optional[bool] = None,
    skip_initial_verification: Optional[bool] = None,
):
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if cache is None:
            cache_settings = create_mongo_cache_settings(settings, env_prefix)
        else:
            cache_settings = cache.settings

        if uri is not None:
            cache_settings.uri = uri
        if database is not None:
            cache_settings.database = database
        if collection is not None:
            cache_settings.collection = collection
        if query is not None:
            cache_settings.query = query
        if expiration is not None:
            cache_settings.expiration = expiration
        if key_parameters is not None:
            cache_settings.key_parameters = key_parameters
        if time_check is not None:
            cache_settings.time_check = time_check
        if return_metadata_as_member is not None:
            cache_settings.return_metadata_as_member = return_metadata_as_member
        if return_metadata_on_primitives is not None:
            cache_settings.return_metadata_on_primitives = return_metadata_on_primitives
        if flat_data is not None:
            cache_settings.is_flat_data = flat_data
        if data_type is not None:
            cache_settings.force_data_type = BaseCache._qualified_name(data_type)
        if cache_only is not None:
            cache_settings.cache_only = cache_only
        if skip_initial_verification is not None:
            cache_settings.skip_initial_verification = skip_initial_verification

        if cache is None:
            cache_instance = MongoCache(settings=cache_settings)
        else:
            cache_instance = cache

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with cache_instance:
                return cache_decorator(cache_instance)(func)(*args, **kwargs)

        return wrapper

    return decorator
