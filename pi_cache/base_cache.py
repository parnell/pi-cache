import functools
import hashlib
import importlib
import inspect
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Hashable,
    Optional,
    ParamSpec,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from pi_cache.models import (
    CacheEntry,
    CacheMissError,
    MetaMixin,
    ModelMetadata,
    TimeCheck,
)
from pi_cache.utils.time_utils import parse_date_string

T = TypeVar("T")
P = ParamSpec("P")
E = TypeVar("E", bound=Exception)
SettingsT = TypeVar("SettingsT", bound="CacheSettings")


class CacheSettings(BaseSettings, Generic[T]):
    """Configuration settings for cache behavior."""

    expiration: Optional[Union[str, int]] = None
    key_parameters: Optional[list[str]] = None
    time_check: TimeCheck = TimeCheck.CREATION
    return_metadata_as_member: bool = True
    return_metadata_on_primitives: bool = False
    is_flat_data: bool = False
    force_data_type: Optional[str] = Field(
        default=None,
        description="Force a specific data type. Useful when the data type cannot be inferred, or putting the cache on an already existing cache that doesn't implement data_type",
    )
    cache_only: bool = Field(
        default=False, description="Only use the cache, do not call the function."
    )
    ignore_self: bool = Field(
        default=False, description="Ignore self parameter when generating cache key for class methods"
    )


@dataclass
class FuncCall(Generic[SettingsT]):
    """Represents a function call with all necessary information to generate a cache key."""

    cache_instance: "BaseCache"
    settings: SettingsT
    func: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    key_parameters: Optional[list[str]] = None
    ignore_self: bool = False
    bound_entity: Optional[type | object] = None
    is_instance: bool = False
    
    def __post_init__(self):
        # ignore_self from decorator takes precedence over settings
        if not self.ignore_self:
            self.ignore_self = self.settings.ignore_self


class TypeRegistry:
    """Registry for custom type serialization and deserialization."""

    _serializers: Dict[Type, Callable[[Any], Any]] = {}
    _deserializers: Dict[str, Callable[[Any], Any]] = {}

    @classmethod
    def is_registered(cls, type_: Type) -> bool:
        return type_ in cls._serializers

    @classmethod
    def register(cls, type_: Type) -> Callable[[Callable[[Any], Any]], Callable[[Any], Any]]:
        def decorator(serializer: Callable[[Any], Any]) -> Callable[[Any], Any]:
            cls._serializers[type_] = serializer
            return serializer

        return decorator

    @classmethod
    def register_deserializer(
        cls, type_name: str
    ) -> Callable[[Callable[[Any], Any]], Callable[[Any], Any]]:
        def decorator(deserializer: Callable[[Any], Any]) -> Callable[[Any], Any]:
            cls._deserializers[type_name] = deserializer
            return deserializer

        return decorator

    @classmethod
    def register_pydantic_model(
        cls, model_class: Type[BaseModel], custom_serializer=None, custom_deserializer=None
    ):
        type_name = f"{model_class.__module__}.{model_class.__name__}"

        if custom_serializer:
            cls._serializers[model_class] = custom_serializer
        else:

            @cls.register(model_class)
            def serialize_pydantic(obj: BaseModel):
                return {
                    "__pydantic_model__": type_name,
                    "__data__": obj.model_dump(),
                }

        if custom_deserializer:
            cls._deserializers[type_name] = custom_deserializer
        else:

            @cls.register_deserializer(type_name)
            def deserialize_pydantic(data: Dict[str, Any]):
                return model_class.model_validate(data["__data__"])


def custom_encoder(obj: Any, only_pydantic_data: bool = False) -> Any:
    if isinstance(obj, datetime):
        return serialize_datetime(obj)
    if isinstance(obj, ModelMetadata):
        return obj.model_dump()
    if isinstance(obj, CacheEntry):
        return obj.model_dump()
    if isinstance(obj, BaseModel):
        if not TypeRegistry.is_registered(type(obj)):
            TypeRegistry.register_pydantic_model(type(obj))
        serializer = TypeRegistry._serializers[type(obj)]
        o = serializer(obj)
        if only_pydantic_data:
            return o["__data__"]
        return o
    if isinstance(obj, (list, tuple)):
        return [custom_encoder(item) for item in obj]
    if isinstance(obj, dict):
        return {k: custom_encoder(v) for k, v in obj.items()}
    return obj


def custom_decoder(dct: Any) -> Any:
    if isinstance(dct, dict):
        if "__model_metadata__" in dct:
            return ModelMetadata.model_validate(dct["data"])
        if "__datetime__" in dct:
            return datetime.fromisoformat(dct["__datetime__"])
        if "__pydantic_model__" in dct and "__data__" in dct:
            type_name = dct["__pydantic_model__"]
            deserializer = TypeRegistry._deserializers.get(type_name)
            if deserializer:
                return deserializer(dct)
            # Fallback to import method if not registered
            module_name, class_name = type_name.rsplit(".", 1)
            module = importlib.import_module(module_name)
            model_class = getattr(module, class_name)
            return model_class.model_validate(dct["__data__"])
        return {k: custom_decoder(v) for k, v in dct.items()}
    if isinstance(dct, list):
        return [custom_decoder(item) for item in dct]
    return dct


class BaseCache(ABC):
    def __init__(self, settings: Optional[CacheSettings] = None):
        self.settings = settings or CacheSettings()

    @abstractmethod
    def get(self, func_call: FuncCall) -> Optional[CacheEntry]:
        pass

    @abstractmethod
    def set(self, func_call: FuncCall, entry: CacheEntry) -> None:
        pass

    @abstractmethod
    def exists(self, func_call: FuncCall) -> bool:
        pass

    def serialize(self, entry: CacheEntry) -> str:
        return json.dumps(entry, cls=DateTimeEncoder, default=custom_encoder)

    @classmethod
    def _dump_cache_entry(cls, entry: CacheEntry, settings: CacheSettings) -> Dict[str, Any]:
        if settings.is_flat_data:
            d = custom_encoder(entry.data, only_pydantic_data=True)
            d["_metadata"] = entry.metadata.model_dump()
            return d

        return entry.model_dump()

    def deserialize(self, data: str | dict) -> CacheEntry:
        if isinstance(data, dict):
            if self.settings.is_flat_data:
                meta = data.pop("_metadata", None)
                if meta:
                    metadata = ModelMetadata.model_validate(meta)
                else:
                    metadata = ModelMetadata(creation_timestamp=None)
                if self.settings.force_data_type:
                    metadata.data_type = self.settings.force_data_type
                if self.settings.is_flat_data:
                    metadata.is_flat_data = True
                deserialized_data = self._deserialize_data(data, metadata.data_type)
                return CacheEntry(_metadata=metadata, data=deserialized_data)

            # Convert old format to new format if needed
            if "metadata" in data and "_metadata" not in data:
                data = {
                    "_metadata": data["metadata"],
                    "data": data["data"]
                }
            return CacheEntry.model_validate(data)

        try:
            decoded = json.loads(data, object_hook=custom_decoder)
            if not isinstance(decoded, CacheEntry):
                # Convert old format to new format if needed
                if "metadata" in decoded and "_metadata" not in decoded:
                    decoded = {
                        "_metadata": decoded["metadata"],
                        "data": decoded["data"]
                    }
                ce = CacheEntry.model_validate(decoded)
            else:
                ce = decoded
            deserialized_data = self._deserialize_data(ce.data, ce.metadata.data_type)
            ce.data = deserialized_data
            return ce
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON data: {e}")

    def _deserialize_data(self, data: Any, data_type: Optional[str] = None) -> Any:
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
                # TODO: For non-Pydantic types, implement custom deserialization logic
            except (ImportError, AttributeError, ValueError):
                raise

        return data

    @staticmethod
    def _qualified_name(obj_or_type: Union[object, Type[object]]) -> str:
        if not isinstance(obj_or_type, type):
            obj_or_type = type(obj_or_type)
        return f"{obj_or_type.__module__}.{obj_or_type.__name__}"

    @classmethod
    def _generate_cache_key(cls, func_call: FuncCall) -> str:
        key_content = cls._generate_key_content(func_call)
        key_hash = hashlib.sha256(str(key_content).encode()).hexdigest()
        return f"{key_content['func_name']}_{key_hash[:10]}"

    @classmethod
    def _generate_key_content(cls, func_call: FuncCall) -> Dict[str, Any]:
        func: Callable[..., Any] = func_call.func
        args: tuple[Any, ...] = func_call.args
        kwargs: dict[str, Any] = func_call.kwargs
        key_parameters: Optional[list[str]] = func_call.key_parameters
        bound_entity = func_call.bound_entity
        ignore_self = func_call.ignore_self

        # Base key content with function's qualified name
        key_content = {
            "func_name": func.__qualname__,
        }

        # If this is an instance method and ignore_self is True,
        # we should skip the first argument (self) in all cases
        start_index = 1 if (bound_entity is not None and ignore_self) else 0

        # Handle parameters
        if key_parameters:
            filtered_args = []
            filtered_kwargs = {}
            arg_spec = inspect.getfullargspec(func)
            # Always skip 'self' for instance methods when ignore_self is True
            arg_names = arg_spec.args[start_index:]

            # Process only the arguments that should be part of the key
            for i, arg_name in enumerate(arg_names):
                if arg_name in key_parameters:
                    if i < len(args[start_index:]):
                        filtered_args.append(make_hashable(args[i + start_index], not ignore_self))
                    elif arg_name in kwargs:
                        filtered_kwargs[arg_name] = make_hashable(kwargs[arg_name], not ignore_self)

            key_content["args"] = str(tuple(filtered_args))
            key_content["kwargs"] = str(filtered_kwargs)
        else:
            # For all other cases, include all arguments except self when ignore_self is True
            key_content["args"] = str(tuple(make_hashable(arg, not ignore_self) for arg in args[start_index:]))
            key_content["kwargs"] = str({k: make_hashable(v, not ignore_self) for k, v in kwargs.items()})

        return key_content

    @staticmethod
    def _create_func_call(
        cache_instance,
        settings: CacheSettings,
        func: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> FuncCall:
        bound_entity, is_instance = _find_bound_entity(func, *args)
        return FuncCall(
            cache_instance=cache_instance,
            settings=settings,
            func=func,
            args=args,
            kwargs=kwargs,
            key_parameters=settings.key_parameters,
            bound_entity=bound_entity,
            is_instance=is_instance,
        )


@overload
def cast_exception(e: E) -> Union[E, MetaMixin]: ...


@overload
def cast_exception(e: E, exception_type: Type[E]) -> Union[E, MetaMixin]: ...


def cast_exception(e: E, exception_type: Type[E] | None = None) -> Union[E, MetaMixin]:
    if exception_type is None:
        exception_type = type(e)
    return cast(Union[exception_type, MetaMixin], e)  # type: ignore


def make_hashable(obj: Any, include_id: bool = True) -> Hashable:
    """
    Convert an object into a hashable type for cache key generation.
    
    Args:
        obj: The object to make hashable
        include_id: If True, includes object id for class instances
    """
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, (list, tuple)):
        return tuple(make_hashable(x, include_id) for x in obj)
    if isinstance(obj, dict):
        return tuple(sorted((k, make_hashable(v, include_id)) for k, v in obj.items()))
    if isinstance(obj, type):
        # For class types, use the qualified name
        return f"{obj.__module__}.{obj.__qualname__}"
    if hasattr(obj, "__class__"):
        # For class instances, include id when needed
        class_name = f"{obj.__class__.__module__}.{obj.__class__.__qualname__}"
        return f"{class_name}#{id(obj)}" if include_id else class_name
    return str(obj)


def is_cache_valid(
    metadata: ModelMetadata, current_time: datetime, settings: CacheSettings
) -> bool:
    if settings.expiration is None:
        return True

    if settings.time_check == TimeCheck.CREATION:
        reference_time = metadata.creation_timestamp
    elif settings.time_check == TimeCheck.LAST_UPDATE:
        reference_time = metadata.last_update_timestamp or metadata.creation_timestamp
    elif settings.time_check == TimeCheck.EXPIRES_AT:
        return metadata.expires_at is None or current_time < metadata.expires_at
    else:
        raise ValueError(f"Invalid time_check option: {settings.time_check}")

    if reference_time is None:
        return True

    expiration_time = (
        parse_date_string(settings.expiration, reference_time)
        if isinstance(settings.expiration, str)
        else reference_time + timedelta(seconds=settings.expiration)
    )
    return current_time < expiration_time


def _return_obj(cache_entry: CacheEntry[T], settings: CacheSettings[T]) -> T:
    if not settings.return_metadata_as_member:
        return cache_entry.data
    if cache_entry.metadata.data_type and "builtins" in cache_entry.metadata.data_type:
        if settings.return_metadata_on_primitives:
            if isinstance(cache_entry.data, dict):
                cache_entry.data["_metadata"] = cache_entry.metadata
            return cache_entry.data # type: ignore
        return cache_entry.data
    if isinstance(cache_entry.data, dict):
        cache_entry.data["_metadata"] = cache_entry.metadata
    else:
        setattr(cache_entry.data, "_metadata", cache_entry.metadata)
    return cache_entry.data  # type: ignore


def _find_bound_entity(func: Callable, *args) -> tuple[type | object | None, bool]:
    signature = inspect.signature(func)
    parameters = list(signature.parameters.values())
    if parameters and len(args) > 0:
        first_param_name = parameters[0].name
        if first_param_name == "self":
            return args[0], True
        elif first_param_name == "cls" and isinstance(args[0], type):
            return args[0], False
    return None, False


def cache_decorator(cache_instance: BaseCache, ignore_self: bool = False):
    """
    Decorator that caches function results.
    
    Args:
        cache_instance: The cache instance to use
        ignore_self: If True, ignores the self parameter when generating cache key for class methods
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            bound_entity, is_instance = _find_bound_entity(func, *args)
            
            # If ignore_self is True and this is an instance method,
            # we should skip self in both the cache key and metadata
            start_index = 1 if (bound_entity is not None and ignore_self) else 0
            metadata_args = args[start_index:]  # Skip self in metadata if needed
            
            func_call = FuncCall(
                cache_instance=cache_instance,
                settings=cache_instance.settings,
                func=func,
                args=args,  # Keep original args for function call
                kwargs=kwargs,
                key_parameters=cache_instance.settings.key_parameters,
                ignore_self=ignore_self,
                bound_entity=bound_entity,
                is_instance=is_instance,
            )
            
            cache_entry = cache_instance.get(func_call)
            if cache_entry is not None and is_cache_valid(
                cache_entry.metadata, datetime.now(UTC), cache_instance.settings
            ):
                cache_entry.metadata.from_cache = True
                return _return_obj(cache_entry, cache_instance.settings)
            if cache_instance.settings.cache_only:
                raise CacheMissError(
                    func_call,
                    f"Cache miss for {func.__qualname__} args: {args}, kwargs: {kwargs}",
                )

            exception: Optional[Exception] = None

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                if hasattr(e, "save_var"):
                    result = getattr(e, "save_var")
                    exception = e
                else:
                    raise e

            current_time = datetime.now(UTC)
            metadata = ModelMetadata(
                creation_timestamp=current_time,
                last_update_timestamp=current_time,
                expires_at=(
                    parse_date_string(cache_instance.settings.expiration, current_time)
                    if isinstance(cache_instance.settings.expiration, str)
                    else (
                        current_time + timedelta(seconds=cache_instance.settings.expiration)
                        if cache_instance.settings.expiration
                        else None
                    )
                ),
                args=metadata_args,  # Use filtered args for metadata
                kwargs=kwargs,
                from_cache=False,
                data_type=BaseCache._qualified_name(result),
                is_flat_data=cache_instance.settings.is_flat_data,
            )
            cache_entry = CacheEntry(_metadata=metadata, data=result)
            cache_instance.set(func_call, cache_entry)

            if exception:
                setattr(result, "_metadata", metadata)
                raise exception
            return _return_obj(cache_entry, cache_instance.settings)

        return wrapper
    return decorator


@TypeRegistry.register(datetime)
def serialize_datetime(dt: datetime) -> str:
    """Serialize a datetime object."""
    return dt.isoformat()


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


TypeRegistry.register_pydantic_model(ModelMetadata)
TypeRegistry.register_pydantic_model(CacheEntry)