# Pi Cache

A flexible file-based caching system for Python functions with support for complex data types and configurable caching behavior.

## Installation

```bash
pip install pi-cache
```

## Features

- File-based persistent caching
- Support for complex Python objects and Pydantic models
- Configurable cache expiration
- Parameter-based cache key generation
- Metadata tracking for cached entries
- Thread-safe operations

## Quick Start

```python
from pi_cache import local_cache
from datetime import datetime

@local_cache(expiration="1d")  # Cache for 1 day
def get_user_data(user_id: int):
    # Expensive database query or API call
    return {"id": user_id, "last_fetch": datetime.now()}

# First call: executes function
result = get_user_data(123)

# Second call: returns cached result
cached_result = get_user_data(123)
```

## Advanced Usage

### Custom Cache Settings

```python
from pi_cache import local_cache, FileCacheSettings, TimeCheck
from pathlib import Path

settings = FileCacheSettings(
    cache_dir=Path("./my_cache"),
    expiration="12h",
    time_check=TimeCheck.LAST_UPDATE,
    return_metadata_as_member=True
)

@local_cache(settings=settings)
def expensive_computation(x: int, y: int):
    return x * y
```

### Cache Only Specific Parameters

```python
@local_cache(
    key_parameters=['user_id'],  # Only cache based on user_id
    expiration="30m"
)
def get_user_posts(user_id: int, include_drafts: bool = False):
    # API call
    return [{"post_id": 1, "content": "Hello"}]
```

### Working with Pydantic Models

```python
from pydantic import BaseModel

class UserData(BaseModel):
    id: int
    name: str
    email: str

@local_cache(expiration="1h")
def fetch_user(user_id: int) -> UserData:
    # Database query
    return UserData(id=user_id, name="John", email="john@example.com")
```

### Accessing Cache Metadata

```python
@local_cache(return_metadata_as_member=True)
def compute_stats(data: list[int]):
    result = sum(data)
    return {"sum": result}

stats = compute_stats([1, 2, 3])
print(f"Cached at: {stats._metadata.creation_timestamp}")
```

### Cache Only Mode

```python
@local_cache(cache_only=True)
def api_call(endpoint: str):
    # Will raise CacheMissError if not in cache
    pass

try:
    result = api_call("/users")
except CacheMissError:
    # Handle cache miss
    pass
```

## API Reference

### Decorators

- `@local_cache()`: Main decorator for caching functions

### Settings

`FileCacheSettings` parameters:
- `cache_dir: str | Path` - Cache directory location
- `expiration: Optional[str | int]` - Cache expiration time
- `key_parameters: Optional[list[str]]` - Parameters to use for cache key
- `time_check: TimeCheck` - Validation time check method
- `return_metadata_as_member: bool` - Attach metadata to returned objects
- `return_metadata_on_primitives: bool` - Include metadata with primitive returns
- `cache_only: bool` - Only use cache, don't execute function

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](https://choosealicense.com/licenses/mit/)