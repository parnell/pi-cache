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
    TYPE_CHECKING,
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

from qrev_cache.utils.time_utils import parse_date_string

if TYPE_CHECKING:
    from qrev_cache.base_cache import FuncCall

T = TypeVar("T")

class ModelMetadata(BaseModel):
    """Metadata associated with a cached item."""

    creation_timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the cache entry was created.",
    )
    last_update_timestamp: Optional[datetime] = Field(
        default=None, description="Timestamp when the cache entry was last updated."
    )
    expires_at: Optional[datetime] = Field(
        default=None, description="Timestamp when the cache entry expires."
    )
    args: tuple = Field(
        default_factory=tuple, description="Arguments used to call the cached function."
    )
    kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Keyword arguments used to call the cached function."
    )
    from_cache: bool = Field(
        default=False, description="Indicates if the result was retrieved from cache."
    )
    data_type: Optional[str] = Field(default=None, description="Type of data stored in the cache.")
    is_flat_data: bool = Field(
        default=False, description="Indicates if the data is stored in flat format."
    )

    def to_flat_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_flat_dict(cls, data: dict[str, Any]) -> "ModelMetadata":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelMetadata":
        return cls(**data)


class CacheEntry(BaseModel, Generic[T]):
    """An entry in the cache, containing both metadata and data."""

    metadata: ModelMetadata = Field(alias="_metadata")
    data: T


class CacheMissError(Exception):
    """Exception raised when a cache miss occurs."""

    def __init__(self, func_call: "FuncCall", message: str):
        self.func_call = func_call
        super().__init__(message)


class TimeCheck(StrEnum):
    """Enum for specifying which timestamp to use for cache validation."""

    CREATION = "creation"
    LAST_UPDATE = "last_update"
    EXPIRES_AT = "expires_at"

class MetaMixin:
    """Mixin class to add metadata to a class. primarily for errors"""

    _metadata: ModelMetadata

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args)  # type: ignore
        self._metadata = kwargs.get("_metadata", {})
    
    @classmethod
    def cast(cls, obj: T) -> "MetaMixin":
        return cast(MetaMixin, obj)

class MetadataCarrier:
    """A wrapper class that carries metadata along with a value."""

    def __init__(self, value: Any, metadata: ModelMetadata):
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
    def metadata(self) -> ModelMetadata:
        return self._metadata
