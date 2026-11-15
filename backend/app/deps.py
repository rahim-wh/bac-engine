"""Dataset singleton, loaded once at application startup."""
from .services.data_store import DataStore

_store: DataStore | None = None


def load_store() -> DataStore:
    global _store
    _store = DataStore()
    return _store


def get_store() -> DataStore:
    if _store is None:  # e.g. TestClient without lifespan
        return load_store()
    return _store
