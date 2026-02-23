# db.py
import copy
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ServerSelectionTimeoutError

load_dotenv()

DEFAULT_MONGODB_URI = "mongodb://localhost:27017"
MONGODB_URI = os.getenv("MONGODB_URI", DEFAULT_MONGODB_URI)
MONGODB_DB = os.getenv("MONGODB_DB") or os.getenv("DB_NAME", "imdb")


@dataclass
class _UpdateResult:
    matched_count: int


@dataclass
class _DeleteResult:
    deleted_count: int


class InMemoryCollection:
    """Lightweight Mongo-like collection used when MongoDB is unavailable."""

    def __init__(self):
        self._docs = {}

    def find(self, _filter=None, _projection=None):
        return [copy.deepcopy(doc) for doc in self._docs.values()]

    def find_one(self, query, _projection=None):
        key = str(query.get("id"))
        doc = self._docs.get(key)
        return copy.deepcopy(doc) if doc else None

    def insert_one(self, doc):
        self._docs[str(doc["id"])] = copy.deepcopy(doc)

    def update_one(self, query, update):
        key = str(query.get("id"))
        if key not in self._docs:
            return _UpdateResult(matched_count=0)
        self._docs[key].update(copy.deepcopy(update.get("$set", {})))
        return _UpdateResult(matched_count=1)

    def delete_one(self, query):
        key = str(query.get("id"))
        if key in self._docs:
            del self._docs[key]
            return _DeleteResult(deleted_count=1)
        return _DeleteResult(deleted_count=0)


def _build_client() -> MongoClient:
    """Create a Mongo client, falling back to localhost for invalid SRV URIs."""
    try:
        return MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    except ConfigurationError:
        if MONGODB_URI != DEFAULT_MONGODB_URI:
            return MongoClient(DEFAULT_MONGODB_URI, serverSelectionTimeoutMS=5000)
        raise


def _build_collections():
    """Return real Mongo collections, or in-memory collections if unavailable."""
    try:
        mongo_client = _build_client()
        mongo_client.admin.command("ping")
        mongo_db = mongo_client[MONGODB_DB]
        return mongo_client, mongo_db["movies"], mongo_db["actors"]
    except (ConfigurationError, ServerSelectionTimeoutError):
        return None, InMemoryCollection(), InMemoryCollection()


client, movies_col, actors_col = _build_collections()
