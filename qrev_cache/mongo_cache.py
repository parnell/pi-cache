import functools
import json
import os
from datetime import datetime, timedelta
from typing import Optional

import requests
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from pymongo import MongoClient

class MongoCacheSettings(BaseSettings):
    uri: str = "mongodb://localhost:27017"
    database: str = "cache_db"
    collection: str = "api_cache"
    expiration: int = 3600