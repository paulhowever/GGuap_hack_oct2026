from functools import lru_cache

from app.f0.base import F0Engine


@lru_cache
def get_engine(name: str) -> F0Engine:
    if name == "swiftf0":
        from app.f0.swiftf0 import SwiftF0Engine

        return SwiftF0Engine()
    raise ValueError(f"unknown f0 engine: {name}")
