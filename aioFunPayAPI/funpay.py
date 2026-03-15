from datetime import datetime, timedelta
from asyncio import get_running_loop
from typing import Optional, Dict, Literal, Any, Union
from httpx import AsyncClient, Response, Proxy

from .types import Category, Subcategory
from .common.config import BASE_URL, USER_AGENT
from .common.parser import parse_category, parser_executor

class FunPay:
    def __init__(self, proxy: Optional[str] = None):
        self.proxy: Optional[str] = proxy
        self._client: Optional[AsyncClient] = None

        self._categories: Optional[list[Category]] = None
        self._categories_by_id: Optional[dict[int, Category]] = None
        self._categories_by_title: Optional[dict[str, Category]] = None
        self._last_categories_update: Optional[datetime] = None
        self._categories_update_interval: timedelta = timedelta(hours=3)

        self._subcategories: Optional[list[Subcategory]] = None
        self._subcategories_by_id: Optional[dict[int, Subcategory]] = None
        self._last_subcategories_update: Optional[datetime] = None
        self._subcategories_update_interval: timedelta = timedelta(hours=3)

    async def _get_client(self) -> AsyncClient:
        proxy = Proxy(self.proxy) if self.proxy else None
        
        if self._client is None:
            self._client = AsyncClient(
                base_url=BASE_URL,
                headers={"User-Agent": USER_AGENT},
                proxy=proxy,
            )
        return self._client

    async def _method(self, method: Literal["get", "post"], url: str, headers: Optional[Dict[str, str]] = None, 
                     data: Optional[Dict[str, Any]] = None) -> Response:

        client = await self._get_client()
        response = await client.request(method, url, headers=headers, data=data)
        return response

    async def get_all_categories(self, update_cache: bool = False) -> list[Category]:   
        if not update_cache and self._categories and self._last_categories_update and \
            datetime.now() - self._last_categories_update < self._categories_update_interval:
            return self._categories
        
        response = await self._method("get", "/")        
        loop = get_running_loop()
        categories = await loop.run_in_executor(parser_executor, parse_category, response.text)
        self._categories = categories
        self._categories_by_id = {cat.id: cat for cat in categories}
        self._categories_by_title = {cat.game_title: cat for cat in categories}
        self._last_categories_update = datetime.now()
        return categories

    async def get_category(self, category: Union[str, int]) -> Optional[Category]:
        await self.get_all_categories()

        if isinstance(category, int):
            return self._categories_by_id.get(category) if self._categories_by_id else None

        return self._categories_by_title.get(category) if self._categories_by_title else None

    async def get_all_subcategories(self, update_cache: bool = False) -> list[Subcategory]:
        if not update_cache and self._subcategories and self._last_subcategories_update and \
            datetime.now() - self._last_subcategories_update < self._subcategories_update_interval:
            return self._subcategories
        
        categories = await self.get_all_categories()
        subcategories: list[Subcategory] = []
        for category in categories:
            subcategories.extend(category.subcategories)
        self._subcategories = subcategories
        self._subcategories_by_id = {subcat.id: subcat for subcat in subcategories}
        self._last_subcategories_update = datetime.now()
        return subcategories

    async def get_subcategory(self, id: int) -> Optional[Subcategory]:
        await self.get_all_subcategories()
        if self._subcategories_by_id is None:
            return None
        return self._subcategories_by_id.get(id)
