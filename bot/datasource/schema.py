from typing import List, Dict, Any
from abc import ABC, abstractmethod


class Repository(ABC):
    @abstractmethod
    async def fetch(
        self, filters: Dict[str, Any] | None = None, **kwargs: Any
    ) -> List[Dict[str, Any]]: ...
