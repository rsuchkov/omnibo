from typing import List, Dict, Any, Protocol
from .schema import Repository


class DataSourceRegistry:
    _sources: Dict[str, Repository] = {}

    @classmethod
    def register_source(cls, name: str, source: Repository):
        cls._sources[name] = source

    @classmethod
    async def get_source(cls, name: str) -> Repository:
        if name not in cls._sources:
            raise ValueError(f"Data source '{name}' not found.")
        return cls._sources[name]
