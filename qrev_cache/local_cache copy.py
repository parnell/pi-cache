import functools
import json
import os
from datetime import datetime, UTC, timedelta
from typing import Optional, Any, Dict, Generic, TypeVar, List, Union, Literal
from pydantic import BaseModel, Field, PrivateAttr
from pydantic_settings import BaseSettings
from qrev_cache.utils.time_utils import parse_date_string

class LocalCacheSettings(BaseSettings):
    cache_dir: str = "cache"
    expiration: Optional[Union[str, int]] = None
    key_parameters: Optional[List[str]] = None
    time_check: Literal["creation", "last_update", "expires_at"] = "creation"

T = TypeVar('T')

class ModelMetadata(BaseModel):
    creation_timestamp: Optional[datetime] = None
    last_update_timestamp: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    args: tuple
    kwargs: Dict[str, Any]
    from_cache: bool

class CacheEntry(BaseModel, Generic[T]):
    metadata: ModelMetadata
    data: T

class MetadataCarrier:
    def __init__(self, value, metadata):
        self._value = value
        self._metadata = metadata

    def __repr__(self):
        return repr(self._value)

    def __str__(self):
        return str(self._value)

    def __int__(self):
        return int(self._value)

    def __float__(self):
        return float(self._value)

    def __eq__(self, other):
        if isinstance(other, MetadataCarrier):
            return self._value == other._value
        return self._value == other

    def __add__(self, other):
        if isinstance(other, MetadataCarrier):
            return self._value + other._value
        return self._value + other

    @property
    def metadata(self):
        return self._metadata

class LocalCache:
    def __init__(self, settings: Optional[LocalCacheSettings] = None):
        self.settings = settings or LocalCacheSettings()
        os.makedirs(self.settings.cache_dir, exist_ok=True)

    def _parse_expiration(self, expiration: Optional[Union[str, int]], reference_time: datetime) -> Optional[datetime]:
        if expiration is None:
            return None
        if isinstance(expiration, int):
            return reference_time + timedelta(seconds=expiration)
        try:
            return parse_date_string(expiration, reference_time=reference_time)
        except:
            raise ValueError(f"Invalid expiration format: {expiration}")

    def __call__(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = self._generate_cache_key(func, args, kwargs)
            cache_file = os.path.join(self.settings.cache_dir, f'cache_{key}.json')

            current_time = datetime.now(UTC)

            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    cache_entry = CacheEntry.model_validate_json(f.read())
                
                if self._is_cache_valid(cache_entry.metadata, current_time):
                    cache_entry.metadata.from_cache = True
                    return self._attach_metadata(cache_entry.data, cache_entry.metadata)

            # If not in cache or expired, call the original function
            result = func(*args, **kwargs)

            # Create cache entry
            metadata = ModelMetadata(
                creation_timestamp=current_time,
                last_update_timestamp=current_time,
                expires_at=self._calculate_expiration(current_time),
                args=args,
                kwargs=kwargs,
                from_cache=False
            )
            cache_entry = CacheEntry(metadata=metadata, data=result)

            # Save the cache entry
            with open(cache_file, 'w') as f:
                f.write(cache_entry.model_dump_json())

            return self._attach_metadata(result, metadata)

        return wrapper

    def _calculate_expiration(self, reference_time: datetime) -> Optional[datetime]:
        return self._parse_expiration(self.settings.expiration, reference_time)

    def _is_cache_valid(self, metadata: ModelMetadata, current_time: datetime) -> bool:
        if self.settings.expiration is None:
            return True  # Cache is always valid if no expiration is set

        if self.settings.time_check == "creation":
            if metadata.creation_timestamp is None:
                return True  # Assume indefinite cache life if no creation timestamp
            expiration_time = self._parse_expiration(self.settings.expiration, metadata.creation_timestamp)
        elif self.settings.time_check == "last_update":
            if metadata.last_update_timestamp is None:
                return True  # Assume indefinite cache life if no last update timestamp
            expiration_time = self._parse_expiration(self.settings.expiration, metadata.last_update_timestamp)
        elif self.settings.time_check == "expires_at":
            expiration_time = metadata.expires_at
        else:
            raise ValueError(f"Invalid time_check option: {self.settings.time_check}")

        return expiration_time is None or current_time < expiration_time

    def _generate_cache_key(self, func, args, kwargs):
        if self.settings.key_parameters:
            filtered_args = []
            filtered_kwargs = {}
            arg_names = func.__code__.co_varnames[:func.__code__.co_argcount]
            for i, arg_name in enumerate(arg_names):
                if arg_name in self.settings.key_parameters:
                    if i < len(args):
                        filtered_args.append(args[i])
                    elif arg_name in kwargs:
                        filtered_kwargs[arg_name] = kwargs[arg_name]
            for kw, value in kwargs.items():
                if kw in self.settings.key_parameters:
                    filtered_kwargs[kw] = value
            key_content = (func.__name__, tuple(filtered_args), frozenset(filtered_kwargs.items()))
        else:
            key_content = (func.__name__, args, frozenset(kwargs.items()))
        
        return hash(key_content)

    def _attach_metadata(self, data: Any, metadata: ModelMetadata) -> Any:
        if isinstance(data, BaseModel):
            data._metadata = metadata
            return data
        else:
            return MetadataCarrier(data, metadata)
