from ..schema import Repository
from bot_config import settings
import aiohttp
from typing import Dict, Any


class JiraRepository(Repository):
    def __init__(self, api_base_url: str, api_token: str):
        self.api_base_url = api_base_url
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }

    async def fetch(self, filters: Dict[str, str] | None, **kwargs: Any): ...


class JiraIssuesRepository(JiraRepository):
    async def fetch(self, filters: Dict[str, str] | None, **kwargs: Any):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_base_url}/search",
                headers=self.headers,
                params=filters,
            ) as response:
                return (await response.json())["issues"]
