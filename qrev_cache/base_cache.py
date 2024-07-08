import functools
import importlib
import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from enum import Enum
from importlib import import_module
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    overload,
    Hashable,
    Optional,
    Protocol,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
    cast,
)

from pydantic import BaseModel
from pydantic_settings import BaseSettings

from qrev_cache.utils.time_utils import parse_date_string


T = TypeVar("T")


class TimeCheck(Enum):
    """Enum for specifying which timestamp to use for cache validation."""

    CREATION = "creation"
    LAST_UPDATE = "last_update"
    EXPIRES_AT = "expires_at"


class CacheSettings(BaseSettings, Generic[T]):
    """Configuration settings for cache behavior."""

    expiration: Optional[Union[str, int]] = None
    key_parameters: Optional[list[str]] = None
    time_check: TimeCheck = TimeCheck.CREATION

    return_metadata_as_member: bool = True
    return_metadata_on_primitives: bool = False


class ModelMetadata(BaseModel):
    """Metadata associated with a cached item."""

    creation_timestamp: Optional[datetime] = None
    last_update_timestamp: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    args: tuple
    kwargs: dict[str, Any]
    from_cache: bool
    data_type: str


class MetadataWrapper(Generic[T]):
    def __init__(self, value: T, metadata: Optional[ModelMetadata] = None):
        self._value = value
        self._metadata = metadata

    def __getattr__(self, name: str):
        return getattr(self._value, name)

    @property
    def _metadata(self) -> Optional[ModelMetadata]:
        return self.__dict__["_metadata"]

    @_metadata.setter
    def _metadata(self, value: Optional[ModelMetadata]):
        self.__dict__["_metadata"] = value



@runtime_checkable
class Serializable(Protocol):
    """Protocol for objects that can be serialized and deserialized."""

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> "Serializable": ...


class MetadataCarrier:
    """A wrapper class that carries metadata along with a value."""

    def __init__(self, value: Any, metadata: "ModelMetadata"):
        self._value = value
        self._metadata = metadata

    def __repr__(self) -> str:
        return repr(self._value)

    def __str__(self) -> str:
        return str(self._value)

    def __int__(self) -> int:
        return int(self._value)

    def __float__(self) -> float:
        return float(self._value)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, MetadataCarrier):
            return self._value == other._value
        return self._value == other

    def __add__(self, other: Any) -> Any:
        if isinstance(other, MetadataCarrier):
            return self._value + other._value
        return self._value + other

    @property
    def metadata(self) -> "ModelMetadata":
        return self._metadata


class CacheEntry(BaseModel, Generic[T]):
    """An entry in the cache, containing both metadata and data."""

    metadata: ModelMetadata
    data: T


class TypeRegistry:
    """Registry for custom type serialization and deserialization."""

    _serializers: Dict[Type, Callable[[Any], Any]] = {}
    _deserializers: Dict[str, Callable[[Any], Any]] = {}

    @classmethod
    def is_registered(cls, type_: Type) -> bool:
        """Check if a type is registered for serialization."""
        return type_ in cls._serializers

    @classmethod
    def register(cls, type_: Type) -> Callable[[Callable[[Any], Any]], Callable[[Any], Any]]:
        """Decorator to register a serializer for a specific type."""

        def decorator(serializer: Callable[[Any], Any]) -> Callable[[Any], Any]:
            cls._serializers[type_] = serializer
            return serializer

        return decorator

    @classmethod
    def register_deserializer(
        cls, type_name: str
    ) -> Callable[[Callable[[Any], Any]], Callable[[Any], Any]]:
        """Decorator to register a deserializer for a specific type name."""

        def decorator(deserializer: Callable[[Any], Any]) -> Callable[[Any], Any]:
            cls._deserializers[type_name] = deserializer
            return deserializer

        return decorator

    @classmethod
    def register_pydantic_model(
        cls, model_class: Type[BaseModel], custom_serializer=None, custom_deserializer=None
    ):
        """Register a Pydantic model for serialization and deserialization."""
        type_name = f"{model_class.__module__}.{model_class.__name__}"

        if custom_serializer:
            cls._serializers[model_class] = custom_serializer
        else:

            @cls.register(model_class)
            def serialize_pydantic(obj: BaseModel):
                return {
                    "__pydantic_model__": type_name,
                    "__data__": obj.model_dump(mode="json"),
                }

        if custom_deserializer:
            cls._deserializers[type_name] = custom_deserializer
        else:

            @cls.register_deserializer(type_name)
            def deserialize_pydantic(data: Dict[str, Any]):
                return model_class(**data["__data__"])


def custom_encoder(obj: Any) -> Any:
    if isinstance(obj, CacheEntry):
        obj_type = type(obj.data)
        if not TypeRegistry.is_registered(obj_type):
            TypeRegistry.register_pydantic_model(obj_type)

        serializer = TypeRegistry._serializers[obj_type]
    if isinstance(obj, datetime):
        return serialize_datetime(obj)
    if isinstance(obj, BaseModel):
        if not TypeRegistry.is_registered(type(obj)):
            TypeRegistry.register_pydantic_model(type(obj))

        serializer = TypeRegistry._serializers[type(obj)]
        return serializer(obj)
    if isinstance(obj, (list, tuple)):
        return [custom_encoder(item) for item in obj]
    if isinstance(obj, dict):
        return {k: custom_encoder(v) for k, v in obj.items()}
    return obj


def custom_decoder(dct: Any) -> Any:
    if isinstance(dct, dict):
        if "__datetime__" in dct:
            return deserialize_datetime(dct["__datetime__"])
        if "__pydantic_model__" in dct and "__data__" in dct:
            type_name = dct["__pydantic_model__"]
            deserializer = TypeRegistry._deserializers.get(type_name)
            if deserializer:
                return deserializer(dct)
            # Fallback to import method if not registered
            module_name, class_name = type_name.rsplit(".", 1)
            module = import_module(module_name)
            model_class = getattr(module, class_name)
            return model_class(**dct["__data__"])
        return {k: custom_decoder(v) for k, v in dct.items()}
    if isinstance(dct, list):
        return [custom_decoder(item) for item in dct]
    return dct


class BaseCache(ABC):
    """Abstract base class for cache implementations."""

    @abstractmethod
    def get(self, key: Hashable) -> Optional[CacheEntry]:
        """Retrieve a cache entry by key."""
        pass

    @abstractmethod
    def set(self, key: Hashable, entry: CacheEntry) -> None:
        """Set a cache entry for a given key."""
        pass

    @abstractmethod
    def exists(self, key: Hashable) -> bool:
        """Check if a key exists in the cache."""
        pass

    def serialize(self, entry: CacheEntry) -> str:
        """Serialize a CacheEntry to a JSON string."""
        return json.dumps(entry, default=custom_encoder)

    def deserialize(self, data: str) -> CacheEntry:
        """Deserialize a JSON string to a CacheEntry."""
        try:
            ce = json.loads(data, object_hook=custom_decoder)
            if not isinstance(ce, CacheEntry):
                raise ValueError("Deserialized object is not a CacheEntry")
            deserialized_data = self._deserialize_data(ce.data, ce.metadata.data_type)
            ce.data = deserialized_data
            return ce
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON data: {e}")

    def _serialize_data(self, data: Any) -> Any:
        """Serialize the data part of a CacheEntry."""
        return custom_encoder(data)

    def _deserialize_data(self, data: Any, data_type: str) -> Any:
        if isinstance(data, dict) and "__pydantic_model__" in data:
            type_name = data["__pydantic_model__"]
            deserializer = TypeRegistry._deserializers.get(type_name)
            if deserializer:
                return deserializer(data)

        # Use the data_type from metadata if available
        if data_type:
            try:
                module_name, class_name = data_type.rsplit(".", 1)
                module = importlib.import_module(module_name)
                class_ = getattr(module, class_name)
                if issubclass(class_, BaseModel):
                    return class_(**data)
                # For non-Pydantic types, you might need to implement custom deserialization logic
            except (ImportError, AttributeError, ValueError):
                pass  # Fall back to returning data as is

        return data

    def _get_model_class(self, model_name: str) -> Type[BaseModel]:
        """Get the Pydantic model class by name."""
        return globals()[model_name]

    @staticmethod
    def _qualified_name(obj_or_type: Union[object, Type[object]]) -> str:
        if not isinstance(obj_or_type, type):
            obj_or_type = type(obj_or_type)
        return f"{obj_or_type.__module__}.{obj_or_type.__name__}"


def generate_cache_key(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    key_parameters: Optional[list[str]] = None,
) -> Hashable:
    """Generate a cache key based on function name, arguments, and specified key parameters."""
    if key_parameters:
        filtered_args = []
        filtered_kwargs = {}
        arg_names = func.__code__.co_varnames[: func.__code__.co_argcount]
        for i, arg_name in enumerate(arg_names):
            if arg_name in key_parameters:
                if i < len(args):
                    filtered_args.append(args[i])
                elif arg_name in kwargs:
                    filtered_kwargs[arg_name] = kwargs[arg_name]
        for kw, value in kwargs.items():
            if kw in key_parameters:
                filtered_kwargs[kw] = value
        key_content = (func.__name__, tuple(filtered_args), frozenset(filtered_kwargs.items()))
    else:
        key_content = (func.__name__, args, frozenset(kwargs.items()))

    return hash(key_content)


def is_cache_valid(
    metadata: ModelMetadata, current_time: datetime, settings: CacheSettings
) -> bool:
    """Check if a cache entry is still valid based on the provided settings."""
    if settings.expiration is None:
        return True  # Cache is always valid if no expiration is set

    if settings.time_check == TimeCheck.CREATION:
        if metadata.creation_timestamp is None:
            return True  # Assume indefinite cache life if no creation timestamp
        expiration_time = parse_expiration(settings.expiration, metadata.creation_timestamp)
    elif settings.time_check == TimeCheck.LAST_UPDATE:
        if metadata.last_update_timestamp is None:
            return True  # Assume indefinite cache life if no last update timestamp
        expiration_time = parse_expiration(settings.expiration, metadata.last_update_timestamp)
    elif settings.time_check == TimeCheck.EXPIRES_AT:
        expiration_time = metadata.expires_at
    else:
        raise ValueError(f"Invalid time_check option: {settings.time_check}")

    return expiration_time is None or current_time < expiration_time


def calculate_expiration(
    reference_time: datetime, expiration: Optional[Union[str, int]]
) -> Optional[datetime]:
    """Calculate the expiration time based on the reference time and expiration setting."""
    return parse_expiration(expiration, reference_time)


def parse_expiration(
    expiration: Optional[Union[str, int]], reference_time: datetime
) -> Optional[datetime]:
    """Parse the expiration setting and return the actual expiration datetime."""
    if expiration is None:
        return None
    if isinstance(expiration, int):
        return reference_time + timedelta(seconds=expiration)
    try:
        return parse_date_string(expiration, reference_time=reference_time)
    except:
        raise ValueError(f"Invalid expiration format: {expiration}")


def _return_obj(cache_entry: CacheEntry[T], settings: CacheSettings[T]) -> MetadataWrapper[T]:
    if not settings.return_metadata_as_member:
        return cache_entry.data
    if "builtins" in cache_entry.metadata.data_type:
        if not settings.return_metadata_on_primitives:
            return cache_entry.data
        return MetadataCarrier(cache_entry.data, cache_entry.metadata)
    return MetadataWrapper(cache_entry.data, cache_entry.metadata)

# @overload
# def cache_decorator(
#     cache_instance: BaseCache, settings: CacheSettings[Any]
# ) -> Callable[[Callable[..., T]], Callable[..., T]]: ...


# @overload
# def cache_decorator(
#     cache_instance: BaseCache,
# ) -> Callable[[Callable[..., T]], Callable[..., T]]: ...


def cache_decorator(cache_instance: BaseCache, settings: Optional[CacheSettings[Any]] = None):
    """Decorator for caching function results."""

    def decorator(func: Callable[..., T]) -> Callable[..., MetadataWrapper[T]]:
        nonlocal settings
        if settings is None:
            settings = CacheSettings()  # Use default settings if not provided

        # Cast settings to the correct type based on the function's return type
        typed_settings = cast(CacheSettings[T], settings)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> MetadataWrapper[T]:
            key = generate_cache_key(func, args, kwargs, typed_settings.key_parameters)

            if cache_instance.exists(key):
                cache_entry = cache_instance.get(key)
                if cache_entry is not None and is_cache_valid(
                    cache_entry.metadata, datetime.now(UTC), typed_settings
                ):
                    cache_entry.metadata.from_cache = True
                    return _return_obj(cache_entry, typed_settings)

            result = func(*args, **kwargs)

            current_time = datetime.now(UTC)
            metadata = ModelMetadata(
                creation_timestamp=current_time,
                last_update_timestamp=current_time,
                expires_at=calculate_expiration(current_time, typed_settings.expiration),
                args=args,
                kwargs=kwargs,
                from_cache=False,
                data_type=BaseCache._qualified_name(result),
            )
            cache_entry = CacheEntry(metadata=metadata, data=result)
            cache_instance.set(key, cache_entry)
            return _return_obj(cache_entry, typed_settings)

        return wrapper

    return decorator


@TypeRegistry.register(datetime)
def serialize_datetime(dt: datetime) -> dict:
    """Serialize a datetime object."""
    return {"__datetime__": dt.isoformat()}


@TypeRegistry.register_deserializer("__datetime__")
def deserialize_datetime(data: str) -> datetime:
    """Deserialize a datetime object."""
    return datetime.fromisoformat(data)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that can handle datetime objects."""

    def default(self, o):
        if isinstance(o, datetime):
            return serialize_datetime(o)
        return super().default(o)


def datetime_decoder(dct):
    """Custom JSON decoder that can handle serialized datetime objects."""
    if "__datetime__" in dct:
        return deserialize_datetime(dct["__datetime__"])
    return dct
